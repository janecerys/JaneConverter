"""Direct, consent-based browser-media capture for JaneConverter.

The browser extension sends only the media the user explicitly selected in the
active tab. This module validates the metadata at the loopback boundary,
accepts ordered bounded chunks, and keeps the resulting temporary files beside
the current app session. It never reads, receives, or materializes cookies.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import secrets
import shutil
import threading
from typing import Any
from urllib.parse import urlparse


MAX_METADATA_BYTES = 64 * 1024
MAX_CHUNK_BYTES = 8 * 1024 * 1024
MAX_MEDIA_BYTES = 1024 * 1024 * 1024
MAX_CAPTURE_ITEMS = 24
MAX_TOTAL_CAPTURE_BYTES = 2 * 1024 * 1024 * 1024
MAX_TEXT_BYTES = 512
MEDIA_KINDS = frozenset({"video", "audio", "image"})
CAPTURE_MODES = frozenset({"current", "sequence", "network"})
_SAFE_FILENAME = re.compile(r'^[^<>:"/\\|?*\x00-\x1f]+$')


class CaptureBridgeError(ValueError):
    """Raised when a browser capture request is malformed or unsafe."""


@dataclass(frozen=True)
class CaptureMetadata:
    file_name: str
    media_kind: str
    mime_type: str
    capture_mode: str
    page_url: str
    expected_bytes: int | None
    title: str


@dataclass(frozen=True)
class CapturedMedia:
    path: Path
    file_name: str
    media_kind: str
    mime_type: str
    capture_mode: str
    page_url: str
    title: str


@dataclass
class _PendingCapture:
    metadata: CaptureMetadata
    path: Path
    file_handle: Any
    bytes_written: int = 0


def parse_capture_metadata(payload: bytes | str, source_url: str) -> CaptureMetadata:
    """Validate extension metadata against the confirmed source page."""
    raw_payload = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
    if not raw_payload or len(raw_payload) > MAX_METADATA_BYTES:
        raise CaptureBridgeError("The browser capture metadata is empty or too large.")

    try:
        document = json.loads(raw_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CaptureBridgeError("The browser capture metadata was not valid JSON.") from error
    if not isinstance(document, dict):
        raise CaptureBridgeError("The browser capture metadata must be an object.")

    source = _parse_web_url(source_url, "The confirmed source URL") if source_url.strip() else None
    page_url = _bounded_text(document.get("pageUrl") or source_url, "page URL", required=True)
    page = _parse_web_url(page_url, "The captured page URL")
    if source is not None and not _same_site(source.hostname or "", page.hostname or ""):
        raise CaptureBridgeError("The captured page is not part of the confirmed source site.")

    file_name = _bounded_text(document.get("fileName"), "file name", required=True)
    if (
        file_name in {".", ".."}
        or not _SAFE_FILENAME.fullmatch(file_name)
        or Path(file_name).name != file_name
    ):
        raise CaptureBridgeError("The browser capture returned an unsafe file name.")

    media_kind = _bounded_text(document.get("mediaKind"), "media kind", required=True).lower()
    if media_kind not in MEDIA_KINDS:
        raise CaptureBridgeError("The browser capture returned an unsupported media kind.")

    mime_type = _bounded_text(document.get("mimeType"), "MIME type", required=True).lower()
    if not _valid_mime_type(mime_type, media_kind):
        raise CaptureBridgeError("The browser capture returned an invalid MIME type.")

    capture_mode = _bounded_text(document.get("captureMode", "current"), "capture mode", required=True).lower()
    if capture_mode not in CAPTURE_MODES:
        raise CaptureBridgeError("The browser capture returned an unsupported capture mode.")

    expected_value = document.get("expectedBytes")
    expected_bytes = None
    if expected_value is not None:
        if isinstance(expected_value, bool):
            raise CaptureBridgeError("The expected media size was invalid.")
        try:
            expected_bytes = int(expected_value)
        except (TypeError, ValueError, OverflowError) as error:
            raise CaptureBridgeError("The expected media size was invalid.") from error
        if expected_bytes < 1 or expected_bytes > MAX_MEDIA_BYTES:
            raise CaptureBridgeError("The expected media size is outside the allowed range.")

    title = _bounded_text(document.get("title") or Path(file_name).stem, "title", required=True)
    return CaptureMetadata(
        file_name=file_name,
        media_kind=media_kind,
        mime_type=mime_type,
        capture_mode=capture_mode,
        page_url=page_url,
        expected_bytes=expected_bytes,
        title=title,
    )


class BrowserCaptureStore:
    """Own temporary capture files for one confirmed source session."""

    def __init__(self, root: str | Path, source_url: str):
        self.root = Path(root)
        self.source_url = source_url.strip()
        _parse_web_url(self.source_url, "The confirmed source URL")
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._pending: dict[str, _PendingCapture] = {}
        self._captures: list[CapturedMedia] = []
        self._total_bytes = 0
        self._closed = False

    def start(self, metadata: CaptureMetadata) -> str:
        with self._lock:
            self._ensure_open()
            if len(self._captures) + len(self._pending) >= MAX_CAPTURE_ITEMS:
                raise CaptureBridgeError("This access session has reached its capture limit.")
            if self._pending:
                raise CaptureBridgeError("Another browser capture is already being uploaded.")
            capture_id = secrets.token_urlsafe(18)
            suffix = Path(metadata.file_name).suffix.lower() or ".bin"
            path = self.root / f"{capture_id}{suffix}"
            handle = path.open("wb")
            self._pending[capture_id] = _PendingCapture(metadata, path, handle)
            return capture_id

    def append(self, capture_id: str, offset: int, chunk: bytes) -> None:
        data = bytes(chunk)
        with self._lock:
            pending = self._pending.get(capture_id)
            if pending is None:
                raise CaptureBridgeError("The browser capture upload is not active.")
            if offset != pending.bytes_written:
                raise CaptureBridgeError("The browser capture chunk offset was out of order.")
            if not data or len(data) > MAX_CHUNK_BYTES:
                raise CaptureBridgeError("The browser capture chunk is empty or too large.")
            if pending.bytes_written + len(data) > MAX_MEDIA_BYTES:
                raise CaptureBridgeError("The browser capture is too large.")
            if self._total_bytes + pending.bytes_written + len(data) > MAX_TOTAL_CAPTURE_BYTES:
                raise CaptureBridgeError("The access session has reached its capture storage limit.")
            pending.file_handle.write(data)
            pending.file_handle.flush()
            pending.bytes_written += len(data)

    def finish(self, capture_id: str) -> CapturedMedia:
        with self._lock:
            pending = self._pending.pop(capture_id, None)
            if pending is None:
                raise CaptureBridgeError("The browser capture upload is not active.")
            try:
                pending.file_handle.flush()
                pending.file_handle.close()
                expected = pending.metadata.expected_bytes
                if expected is not None and expected != pending.bytes_written:
                    pending.path.unlink(missing_ok=True)
                    raise CaptureBridgeError("The browser capture size did not match its metadata.")
                captured = CapturedMedia(
                    path=pending.path,
                    file_name=pending.metadata.file_name,
                    media_kind=pending.metadata.media_kind,
                    mime_type=pending.metadata.mime_type,
                    capture_mode=pending.metadata.capture_mode,
                    page_url=pending.metadata.page_url,
                    title=pending.metadata.title,
                )
                self._captures.append(captured)
                self._total_bytes += pending.bytes_written
                return captured
            except CaptureBridgeError:
                raise
            except OSError as error:
                pending.path.unlink(missing_ok=True)
                raise CaptureBridgeError(f"The browser capture could not be finalized: {error}") from error

    def captures_for(self, source_url: str) -> list[CapturedMedia]:
        with self._lock:
            if source_url.strip() != self.source_url:
                return []
            return list(self._captures)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for pending in self._pending.values():
                try:
                    pending.file_handle.close()
                except OSError:
                    pass
            self._pending.clear()
            shutil.rmtree(self.root, ignore_errors=True)

    def _ensure_open(self) -> None:
        if self._closed:
            raise CaptureBridgeError("The browser capture session has expired.")


def _bounded_text(value: Any, label: str, *, required: bool) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()):
        raise CaptureBridgeError(f"The browser capture returned an invalid {label}.")
    value = value.strip()
    if len(value.encode("utf-8")) > MAX_TEXT_BYTES:
        raise CaptureBridgeError(f"The browser capture {label} is too large.")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise CaptureBridgeError(f"The browser capture {label} contains control characters.")
    return value


def _parse_web_url(value: str, label: str):
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise CaptureBridgeError(f"{label} must be a valid HTTP or HTTPS URL.")
    return parsed


def _same_site(left: str, right: str) -> bool:
    left = left.lower().rstrip(".")
    right = right.lower().rstrip(".")
    return bool(left and right) and (left == right or left.endswith(f".{right}") or right.endswith(f".{left}"))


def _valid_mime_type(value: str, media_kind: str) -> bool:
    if "/" not in value or ";" in value or any(character.isspace() for character in value):
        return False
    prefix = value.split("/", 1)[0]
    if media_kind == "video":
        return prefix == "video"
    if media_kind == "audio":
        return prefix == "audio"
    return prefix == "image"
