"""Ephemeral localhost account-access handoff for JaneConverter.

This module deliberately does not implement credential capture, cookie export,
or token collection. It provides a short-lived local page that lets a user open
the source in a chosen browser, sign in there, and confirm the handoff. An
optional unpacked browser extension can then pass a source-scoped session to
the extractor in memory while the browser remains open.
"""

from html import escape
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional
from urllib.parse import urlparse
import secrets

from engine.auth import BrowserDetection, detect_browser_from_headers


MAX_BRIDGE_PAYLOAD_BYTES = 256 * 1024


class AccountAccessServer:
    """Short-lived loopback server used to coordinate browser access."""

    def __init__(self, source_url: str, on_ready: Optional[Callable[[BrowserDetection], None]] = None):
        self.source_url = source_url.strip()
        parsed_source = urlparse(self.source_url)
        if parsed_source.scheme not in {"http", "https"} or not parsed_source.netloc:
            raise ValueError("Account access requires a valid HTTP or HTTPS source URL.")
        self.on_ready = on_ready
        self._token = secrets.token_urlsafe(32)
        self._server = None
        self._thread = None
        self._lock = threading.Lock()
        self._consumed = False
        self._confirmed = False
        self._detected_browser = None
        self._bridge_payload = None

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
        with self._lock:
            return self._bridge_payload is not None

    @property
    def bridge_payload(self) -> Optional[str]:
        with self._lock:
            return self._bridge_payload

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
                        owner._send_json(self, {"ok": True})
                    else:
                        owner._send_response(self, "", 404)

                def do_POST(self):  # noqa: N802 - required by BaseHTTPRequestHandler
                    parsed = urlparse(self.path)
                    base_path = f"/access/{owner._token}"
                    if parsed.path != f"{base_path}/bridge":
                        owner._send_json(self, {"error": "This access link is not valid."}, status=404)
                        return
                    try:
                        content_length = int(self.headers.get("Content-Length", "0"))
                    except ValueError:
                        content_length = 0
                    if content_length <= 0 or content_length > MAX_BRIDGE_PAYLOAD_BYTES:
                        owner._send_json(self, {"error": "The browser bridge payload is too large or empty."}, status=413)
                        return
                    body = self.rfile.read(content_length)
                    owner._receive_bridge_payload(self, body)

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
                # A UI callback must never break the local HTTP response.
                pass

    def _send_bridge_challenge(self, handler):
        with self._lock:
            confirmed = self._confirmed and not self._consumed and self._server is not None
        if not confirmed:
            self._send_json(handler, {"error": "Confirm account access in the browser first."}, status=409)
            return
        self._send_json(handler, {"sourceUrl": self.source_url, "confirmed": True})

    def _receive_bridge_payload(self, handler, body: bytes):
        with self._lock:
            confirmed = self._confirmed and not self._consumed and self._server is not None
        if not confirmed:
            self._send_json(handler, {"error": "Confirm account access in the browser first."}, status=409)
            return
        try:
            from engine.browser_bridge import cookie_jar_from_payload

            cookie_jar_from_payload(body, self.source_url)
            parsed = json.loads(body.decode("utf-8"))
            if not isinstance(parsed, dict) or not isinstance(parsed.get("cookies"), list):
                raise ValueError("The browser bridge payload has an invalid shape.")
        except Exception as error:
            self._send_json(handler, {"error": str(error)}, status=400)
            return
        with self._lock:
            self._bridge_payload = body.decode("utf-8")
        self._send_json(handler, {"ok": True})

    def _record_browser(self, headers):
        detection = detect_browser_from_headers(headers)
        with self._lock:
            if not self._consumed:
                self._detected_browser = detection

    def _landing_page(self, detected_browser: Optional[BrowserDetection]) -> str:
        safe_source = escape(self.source_url, quote=True)
        browser_note = ""
        if detected_browser:
            browser_note = f'<p class="note">Browser detected: <strong>{escape(detected_browser.label)}</strong>.</p>'
        return self._page(
            "Account access",
            f"""
            <h1>JaneConverter account access</h1>
            <p>Use this temporary page in the browser whose session you want to use.
            The link only identifies that browser; JaneConverter does not receive
            your password or copy or upload your cookies.</p>
            <ol>
              <li>Open the source link below.</li>
              <li>Sign in normally if the service asks you to.</li>
              <li>Return to this page and confirm access.</li>
            </ol>
            <p><a class="primary" href="{safe_source}" target="_blank"
               rel="noreferrer" referrerpolicy="no-referrer">Open source link</a></p>
            <p><a class="confirm" href="/access/{self._token}/ready">I’m signed in — confirm access</a></p>
            {browser_note}
            <p class="note">This link expires when you confirm access or close JaneConverter.</p>
            """,
        )

    def _ready_page(self, detected_browser: BrowserDetection) -> str:
        return self._page(
            "Access ready",
            f"""
            <h1>Access confirmed</h1>
            <p>Browser detected: <strong>{escape(detected_browser.label)}</strong>.</p>
            <p>Return to JaneConverter. If the JaneConverter Browser Bridge extension
            is installed, click its toolbar button and choose <strong>Connect</strong>.
            This lets the browser stay open while the current app session uses the
            source-scoped session. No cookie file is created or uploaded.</p>
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
    def _send_json(handler, payload: dict, status: int = 200):
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.send_header("Access-Control-Allow-Headers", "content-type")
        handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("Connection", "close")
        handler.end_headers()
        if status != 204:
            handler.wfile.write(body)
