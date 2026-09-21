"""Ephemeral localhost handoff for direct browser-media capture.

The access page confirms the user's browser context. The optional extension
then sends only explicitly selected media bytes to this loopback server. No
cookie database, cookie value, password, cache, or reusable session token is
accepted by the bridge.
"""

from html import escape
from hmac import compare_digest
import json
from pathlib import Path
import secrets
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional
from urllib.parse import urlparse

from engine.auth import BrowserDetection, detect_browser_from_headers
from engine.browser_bridge import (
    BrowserCaptureStore,
    CaptureBridgeError,
    MAX_CHUNK_BYTES,
    MAX_METADATA_BYTES,
    parse_capture_metadata,
)
from engine.paths import DEFAULT_TEMP_DIR


BRIDGE_HEADER = "X-JaneConverter-Bridge"
CAPTURE_ID_HEADER = "X-JaneConverter-Capture-Id"
CAPTURE_OFFSET_HEADER = "X-JaneConverter-Capture-Offset"
ALLOWED_BRIDGE_ORIGIN_SCHEMES = {
    "chrome-extension",
    "edge-extension",
    "moz-extension",
    "safari-web-extension",
}


class AccountAccessServer:
    """Short-lived loopback server used to coordinate browser capture."""

    def __init__(self, source_url: str, on_ready: Optional[Callable[[BrowserDetection], None]] = None):
        self.source_url = source_url.strip()
        parsed_source = urlparse(self.source_url) if self.source_url else None
        if parsed_source is not None and (parsed_source.scheme not in {"http", "https"} or not parsed_source.netloc):
            raise ValueError("Account access requires a valid HTTP or HTTPS source URL.")
        self.on_ready = on_ready
        self._token = secrets.token_urlsafe(32)
        self._server = None
        self._thread = None
        self._lock = threading.Lock()
        self._consumed = False
        self._confirmed = False
        self._detected_browser = None
        Path(DEFAULT_TEMP_DIR).mkdir(parents=True, exist_ok=True)
        self._capture_root = Path(tempfile.mkdtemp(prefix="browser-capture-", dir=DEFAULT_TEMP_DIR))
        self._capture_store: Optional[BrowserCaptureStore] = (
            BrowserCaptureStore(self._capture_root, self.source_url) if self.source_url else None
        )
        self._bridge_nonce = secrets.token_urlsafe(24)

    @property
    def access_link(self) -> Optional[str]:
        with self._lock:
            if self._server is None:
                return None
            port = self._server.server_address[1]
        return f"http://127.0.0.1:{port}/access/{self._token}"

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._server is not None and not self._consumed

    @property
    def bridge_connected(self) -> bool:
        return bool(self.captured_media_paths)

    @property
    def captured_media_paths(self) -> list[Path]:
        with self._lock:
            store = self._capture_store
            source_url = self.source_url
        return [capture.path for capture in store.captures_for(source_url)] if store and source_url else []

    @property
    def captured_media_path(self) -> Optional[Path]:
        paths = self.captured_media_paths
        return paths[0] if paths else None

    @property
    def detected_browser(self) -> Optional[BrowserDetection]:
        with self._lock:
            return self._detected_browser

    def start(self) -> str:
        with self._lock:
            if self._server is not None:
                port = self._server.server_address[1]
                return f"http://127.0.0.1:{port}/access/{self._token}"

            owner = self

            class AccessRequestHandler(BaseHTTPRequestHandler):
                def do_GET(self):  # noqa: N802 - required by BaseHTTPRequestHandler
                    owner._record_browser(self.headers)
                    parsed = urlparse(self.path)
                    base_path = f"/access/{owner._token}"
                    if parsed.path == base_path:
                        owner._send_response(self, owner._landing_page(owner.detected_browser))
                        return
                    if parsed.path == f"{base_path}/ready":
                        owner._confirm(self)
                        return
                    if parsed.path == f"{base_path}/bridge/challenge":
                        owner._send_bridge_challenge(self)
                        return
                    owner._send_response(self, owner._error_page("This access link is not valid."), 404)

                def do_OPTIONS(self):  # noqa: N802 - required by BaseHTTPRequestHandler
                    parsed = urlparse(self.path)
                    base_path = f"/access/{owner._token}"
                    if parsed.path.startswith(f"{base_path}/bridge"):
                        origin = owner._bridge_origin(self)
                        if origin == "":
                            owner._send_json(self, {"error": "The browser bridge origin was not allowed."}, status=403)
                        else:
                            owner._send_json(self, {"ok": True}, cors_origin=origin)
                    else:
                        owner._send_response(self, "", 404)

                def do_POST(self):  # noqa: N802 - required by BaseHTTPRequestHandler
                    parsed = urlparse(self.path)
                    base_path = f"/access/{owner._token}"
                    origin = owner._bridge_origin(self)
                    if not parsed.path.startswith(f"{base_path}/bridge/capture/"):
                        owner._send_json(self, {"error": "This access link is not valid."}, status=404)
                        return
                    if origin == "":
                        owner._send_json(self, {"error": "The browser bridge origin was not allowed."}, status=403)
                        return
                    limit = MAX_METADATA_BYTES if parsed.path.endswith("/start") else MAX_CHUNK_BYTES
                    try:
                        content_length = int(self.headers.get("Content-Length", "0"))
                    except ValueError:
                        content_length = 0
                    if content_length < 0 or content_length > limit:
                        owner._send_json(self, {"error": "The browser capture request is too large."}, status=413, cors_origin=origin)
                        return
                    body = self.rfile.read(content_length)
                    if parsed.path.endswith("/start"):
                        owner._receive_capture_start(self, body, origin)
                    elif parsed.path.endswith("/chunk"):
                        owner._receive_capture_chunk(self, body, origin)
                    elif parsed.path.endswith("/finish"):
                        owner._receive_capture_finish(self, body, origin)
                    else:
                        owner._send_json(self, {"error": "This browser capture endpoint is not valid."}, status=404, cors_origin=origin)

                def log_message(self, _format, *_args):
                    # Never log URLs containing the one-time access token.
                    return

            self._server = ThreadingHTTPServer(("127.0.0.1", 0), AccessRequestHandler)
            self._server.daemon_threads = True
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                name="account-access-server",
                daemon=True,
            )
            self._thread.start()

        link = self.access_link
        if not link:
            raise RuntimeError("Unable to start the temporary account-access link.")
        return link

    def stop(self):
        with self._lock:
            server = self._server
            self._server = None
            self._consumed = True
            self._bridge_nonce = ""
        if self._capture_store:
            self._capture_store.close()
        if server is not None:
            server.shutdown()
            server.server_close()

    def _confirm(self, handler):
        with self._lock:
            if self._consumed or self._server is None:
                self._send_response(handler, self._error_page("This access link has expired."), 410)
                return
            detected_browser = self._detected_browser or BrowserDetection("Unrecognized browser", None)
            first_confirmation = not self._confirmed
            self._confirmed = True

        self._send_response(handler, self._ready_page(detected_browser))
        if first_confirmation and self.on_ready:
            try:
                self.on_ready(detected_browser)
            except Exception:
                pass

    def _send_bridge_challenge(self, handler):
        origin = self._bridge_origin(handler)
        if origin == "":
            self._send_json(handler, {"error": "The browser bridge origin was not allowed."}, status=403)
            return
        with self._lock:
            confirmed = self._confirmed and not self._consumed and self._server is not None
            bridge_token = self._bridge_nonce
            source_url = self.source_url
        if not confirmed:
            self._send_json(
                handler,
                {"error": "Confirm account access in the browser first."},
                status=409,
                cors_origin=origin,
            )
            return
        self._send_json(
            handler,
            {
                "sourceUrl": source_url,
                "confirmed": True,
                "connected": self.bridge_connected,
                "captureCount": len(self.captured_media_paths),
                "bridgeToken": bridge_token,
            },
            cors_origin=origin,
        )

    def _receive_capture_start(self, handler, body: bytes, origin: Optional[str]):
        if not self._bridge_request_is_ready(handler, origin):
            return
        try:
            with self._lock:
                source_url = self.source_url
            metadata = parse_capture_metadata(body, source_url)
            with self._lock:
                if self._capture_store is None:
                    self.source_url = metadata.page_url
                    self._capture_store = BrowserCaptureStore(self._capture_root, self.source_url)
                store = self._capture_store
            capture_id = store.start(metadata)
        except (CaptureBridgeError, OSError) as error:
            self._send_json(handler, {"error": str(error)}, status=400, cors_origin=origin)
            return
        self._send_json(handler, {"captureId": capture_id}, cors_origin=origin)

    def _receive_capture_chunk(self, handler, body: bytes, origin: Optional[str]):
        if not self._bridge_request_is_ready(handler, origin):
            return
        capture_id = handler.headers.get(CAPTURE_ID_HEADER, "").strip()
        try:
            offset = int(handler.headers.get(CAPTURE_OFFSET_HEADER, ""))
        except ValueError:
            offset = -1
        try:
            with self._lock:
                store = self._capture_store
            if store is None:
                raise CaptureBridgeError("The browser capture session has not been bound to a media page.")
            store.append(capture_id, offset, body)
        except CaptureBridgeError as error:
            self._send_json(handler, {"error": str(error)}, status=400, cors_origin=origin)
            return
        self._send_json(handler, {"ok": True, "offset": offset + len(body)}, cors_origin=origin)

    def _receive_capture_finish(self, handler, body: bytes, origin: Optional[str]):
        if not self._bridge_request_is_ready(handler, origin):
            return
        capture_id = handler.headers.get(CAPTURE_ID_HEADER, "").strip()
        try:
            if body:
                payload = json.loads(body.decode("utf-8"))
                if isinstance(payload, dict) and payload.get("captureId"):
                    capture_id = str(payload["captureId"]).strip()
            with self._lock:
                store = self._capture_store
            if store is None:
                raise CaptureBridgeError("The browser capture session has not been bound to a media page.")
            captured = store.finish(capture_id)
        except (CaptureBridgeError, UnicodeDecodeError, json.JSONDecodeError) as error:
            self._send_json(handler, {"error": str(error)}, status=400, cors_origin=origin)
            return
        self._send_json(
            handler,
            {
                "ok": True,
                "captureId": capture_id,
                "fileName": captured.file_name,
                "mediaKind": captured.media_kind,
                "captureCount": len(self.captured_media_paths),
            },
            cors_origin=origin,
        )

    def _bridge_request_is_ready(self, handler, origin: Optional[str]) -> bool:
        with self._lock:
            confirmed = self._confirmed and not self._consumed and self._server is not None
            expected_nonce = self._bridge_nonce
        if not confirmed:
            self._send_json(handler, {"error": "Confirm account access in the browser first."}, status=409, cors_origin=origin)
            return False
        if not compare_digest(handler.headers.get(BRIDGE_HEADER, ""), expected_nonce):
            self._send_json(handler, {"error": "The browser bridge challenge was invalid or expired."}, status=403, cors_origin=origin)
            return False
        return True

    @staticmethod
    def _bridge_origin(handler) -> Optional[str]:
        origin = handler.headers.get("Origin", "").strip()
        if not origin:
            return None
        parsed = urlparse(origin)
        if (
            parsed.scheme in ALLOWED_BRIDGE_ORIGIN_SCHEMES
            and parsed.netloc
            and parsed.path in {"", "/"}
            and not parsed.query
            and not parsed.fragment
        ):
            return origin
        return ""

    def _record_browser(self, headers):
        detection = detect_browser_from_headers(headers)
        with self._lock:
            if not self._consumed:
                self._detected_browser = detection

    def _landing_page(self, detected_browser: Optional[BrowserDetection]) -> str:
        browser_note = ""
        if detected_browser:
            browser_note = f'<p class="note">Browser detected: <strong>{escape(detected_browser.label)}</strong>.</p>'
        with self._lock:
            source_url = self.source_url
        source_steps = (
            f"""
            <ol>
              <li>Open the source link below.</li>
              <li>Sign in normally if the service asks you to.</li>
              <li>Return to this page and confirm access.</li>
            </ol>
            <p><a class="primary" href="{escape(source_url, quote=True)}" target="_blank"
               rel="noreferrer" referrerpolicy="no-referrer">Open source link</a></p>
            """
            if source_url
            else """
            <ol>
              <li>Open the media page you want to capture in this browser.</li>
              <li>Sign in normally if the service asks you to.</li>
              <li>Return here and confirm access, then use the Browser Capture extension on the media page.</li>
            </ol>
            <p class="note">No source URL was provided. The first capture binds this temporary session to that media page's site.</p>
            """
        )
        return self._page(
            "Account access",
            f"""
            <h1>JaneConverter account access</h1>
            <p>Use this temporary page in the browser whose session you want to use.
            JaneConverter only receives media you explicitly send from the Browser
            Bridge extension. It never receives your password, cookies, or cache.</p>
            {source_steps}
            <p><a class="confirm" href="/access/{self._token}/ready">I’m signed in — confirm access</a></p>
            {browser_note}
            <p class="note">This link expires when JaneConverter closes or access is cleared.</p>
            """,
        )

    def _ready_page(self, detected_browser: BrowserDetection) -> str:
        return self._page(
            "Access ready",
            f"""
            <h1>Access confirmed</h1>
            <p>Browser detected: <strong>{escape(detected_browser.label)}</strong>.</p>
            <p>Return to JaneConverter, open the Browser Bridge extension, and choose
            <strong>Capture current media</strong>. The extension sends only the
            selected media bytes to this app; no cookie file or browser profile data
            is created or uploaded.</p>
            """,
        )

    @staticmethod
    def _error_page(message: str) -> str:
        return AccountAccessServer._page("Access link unavailable", f"<h1>Access link unavailable</h1><p>{escape(message)}</p>")

    @staticmethod
    def _page(title: str, body: str) -> str:
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="referrer" content="no-referrer">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{escape(title)}</title>
<style>
body {{ background:#0b0a14; color:#ededed; font:16px Segoe UI,Arial,sans-serif; max-width:650px; margin:12vh auto; padding:0 24px; line-height:1.55; }}
h1 {{ color:#f1f5f9; }} a {{ color:#93c5fd; }} .primary,.confirm {{ display:inline-block; padding:11px 16px; border-radius:8px; color:#fff; text-decoration:none; margin:4px 8px 4px 0; }}
.primary {{ background:#2563eb; }} .confirm {{ background:#e82c75; }} .note {{ color:#9ca3af; font-size:13px; }}
</style></head><body>{body}</body></html>"""

    @staticmethod
    def _send_response(handler, body: str, status: int = 200):
        payload = body.encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(payload)))
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline';")
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("X-Frame-Options", "DENY")
        handler.send_header("Referrer-Policy", "no-referrer")
        handler.send_header("Connection", "close")
        handler.end_headers()
        handler.wfile.write(payload)

    @staticmethod
    def _send_json(handler, payload: dict, status: int = 200, cors_origin: Optional[str] = None):
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store")
        if cors_origin:
            handler.send_header("Access-Control-Allow-Origin", cors_origin)
            handler.send_header("Vary", "Origin")
            handler.send_header(
                "Access-Control-Allow-Headers",
                f"content-type, {BRIDGE_HEADER}, {CAPTURE_ID_HEADER}, {CAPTURE_OFFSET_HEADER}",
            )
            handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("Connection", "close")
        handler.end_headers()
        handler.wfile.write(body)
