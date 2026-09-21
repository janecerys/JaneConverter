"""Validate and materialize a one-time, source-scoped browser bridge payload.

The browser extension is the consent boundary: it asks the browser for
cookies applicable to the active source URL and sends the result to the
loopback launcher. This module validates that untrusted JSON again before
turning it into an in-memory yt-dlp cookie jar. It never writes a cookie file,
logs cookie values, or retains the payload after the Python process exits.
"""

from __future__ import annotations

import http.cookiejar
import json
import time
from typing import Any, BinaryIO
from urllib.parse import urlparse

import yt_dlp.cookies as ytdlp_cookies


MAX_PAYLOAD_BYTES = 256 * 1024
MAX_COOKIE_COUNT = 500
MAX_COOKIE_FIELD_BYTES = 8192
_active_cookie_jar = None


class CookieBridgeError(ValueError):
    """Raised when a browser bridge payload is malformed or unsafe to use."""


def set_active_browser_cookie_jar(cookie_jar) -> None:
    """Keep one validated jar in the current Python process only."""
    global _active_cookie_jar
    _active_cookie_jar = cookie_jar


def get_active_browser_cookie_jar():
    """Return the current-process bridge jar, if one was provided."""
    return _active_cookie_jar


def clear_active_browser_cookie_jar() -> None:
    """Release the bridge jar reference after a job or failed startup."""
    global _active_cookie_jar
    _active_cookie_jar = None


def read_cookie_jar_from_stdin(stream: BinaryIO, source_url: str):
    """Read one bounded JSON payload from stdin and return an in-memory jar."""
    payload = stream.read(MAX_PAYLOAD_BYTES + 1)
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise CookieBridgeError("The browser bridge payload is too large.")
    return cookie_jar_from_payload(payload, source_url)


def cookie_jar_from_payload(payload: bytes | str, source_url: str):
    """Validate a source-scoped extension payload and build a cookie jar."""
    raw_payload = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
    if len(raw_payload) > MAX_PAYLOAD_BYTES:
        raise CookieBridgeError("The browser bridge payload is too large.")

    parsed_source = urlparse(str(source_url or "").strip())
    source_host = (parsed_source.hostname or "").lower().rstrip(".")
    if parsed_source.scheme not in {"http", "https"} or not source_host:
        raise CookieBridgeError("The browser bridge requires a valid HTTP or HTTPS source URL.")

    try:
        document = json.loads(raw_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CookieBridgeError("The browser bridge payload was not valid JSON.") from error
    if not isinstance(document, dict) or not isinstance(document.get("cookies"), list):
        raise CookieBridgeError("The browser bridge payload did not contain a cookie list.")
    if len(document["cookies"]) > MAX_COOKIE_COUNT:
        raise CookieBridgeError("The browser bridge returned too many cookies.")

    source_path = parsed_source.path or "/"
    jar = ytdlp_cookies.YoutubeDLCookieJar()
    for raw_cookie in document["cookies"]:
        cookie = _cookie_from_extension_value(raw_cookie, source_host, source_path, parsed_source.scheme)
        if cookie is not None:
            jar.set_cookie(cookie)
    if not len(jar):
        raise CookieBridgeError("The browser bridge returned no usable cookies for this source.")
    return jar


def _cookie_from_extension_value(
    raw_cookie: Any,
    source_host: str,
    source_path: str,
    source_scheme: str,
):
    if not isinstance(raw_cookie, dict):
        raise CookieBridgeError("The browser bridge returned an invalid cookie entry.")

    name = _bounded_text(raw_cookie.get("name"), "cookie name", required=True)
    value = _bounded_text(raw_cookie.get("value"), "cookie value", required=False)
    domain = _bounded_text(raw_cookie.get("domain"), "cookie domain", required=True).lower().rstrip(".")
    path = _bounded_text(raw_cookie.get("path"), "cookie path", required=True)
    if any(_has_control_characters(item) for item in (name, value, domain, path)):
        raise CookieBridgeError("The browser bridge returned a cookie with control characters.")
    if not path.startswith("/"):
        raise CookieBridgeError("The browser bridge returned an invalid cookie path.")

    if not _domain_matches(domain, source_host) or not _path_matches(path, source_path):
        return None
    secure = bool(raw_cookie.get("secure", False))
    if secure and source_scheme != "https":
        return None

    expiration = raw_cookie.get("expirationDate")
    expires = None
    if expiration is not None:
        try:
            expires = int(float(expiration))
        except (TypeError, ValueError, OverflowError) as error:
            raise CookieBridgeError("The browser bridge returned an invalid cookie expiry.") from error
        if expires <= int(time.time()):
            return None

    host_only = bool(raw_cookie.get("hostOnly", False))
    initial_dot = domain.startswith(".")
    return http.cookiejar.Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain=domain if initial_dot or host_only else f".{domain}",
        domain_specified=not host_only,
        domain_initial_dot=initial_dot,
        path=path,
        path_specified=True,
        secure=secure,
        expires=expires,
        discard=expires is None,
        comment=None,
        comment_url=None,
        rest={"HttpOnly": None} if raw_cookie.get("httpOnly") else {},
        rfc2109=False,
    )


def _bounded_text(value: Any, label: str, *, required: bool) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value):
        raise CookieBridgeError(f"The browser bridge returned an invalid {label}.")
    if len(value.encode("utf-8")) > MAX_COOKIE_FIELD_BYTES:
        raise CookieBridgeError(f"The browser bridge returned a {label} that is too large.")
    return value


def _domain_matches(cookie_domain: str, source_host: str) -> bool:
    normalized = cookie_domain.lstrip(".")
    return bool(normalized) and (source_host == normalized or source_host.endswith(f".{normalized}"))


def _path_matches(cookie_path: str, source_path: str) -> bool:
    if source_path == cookie_path:
        return True
    prefix = cookie_path.rstrip("/")
    return cookie_path == "/" or (bool(prefix) and source_path.startswith(f"{prefix}/"))


def _has_control_characters(value: str) -> bool:
    return any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
