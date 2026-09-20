"""Read authorized Chromium cookies without creating a cookie file.

The normal yt-dlp Chromium path copies the browser database before opening it.
When a live browser keeps that file locked, SQLite can still provide a safe
read-only view in some environments. This module uses that view only for the
requested source domain, decrypts through yt-dlp's existing OS-bound decryptor,
and returns an in-memory cookie jar. It never writes to the browser profile,
disables browser security, or stores a cookie export.
"""

from __future__ import annotations

import http.cookiejar
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import yt_dlp.cookies as ytdlp_cookies


_CHROMIUM_BROWSERS = frozenset({"brave", "chrome", "chromium", "edge", "opera", "vivaldi", "whale"})
_CHROMIUM_EPOCH_OFFSET = 11_644_473_600


class _CookieLogger:
    """Quiet logger compatible with yt-dlp's cookie decryptors."""

    def debug(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    info = debug
    warning = debug
    error = debug


def load_browser_cookies_read_only(
    browser_name: str,
    source_url: str,
    *,
    attempts: int = 4,
    retry_delay: float = 0.75,
):
    """Load source-scoped Chromium cookies from a live browser profile.

    ``None`` means the read-only path was unavailable or yielded no matching
    cookies. The caller should then use yt-dlp's regular browser-cookie path.

    A live browser may briefly be rotating or flushing its cookie database.
    Retry only this read-only path for a short, bounded interval so users do
    not have to close the browser or press Convert repeatedly. No browser
    process is stopped and no profile data is modified.
    """
    browser = str(browser_name or "").strip().lower()
    parsed_source = urlparse(str(source_url or "").strip())
    if browser not in _CHROMIUM_BROWSERS or parsed_source.scheme not in {"http", "https"}:
        return None

    total_attempts = max(1, int(attempts))
    delay = max(0.0, float(retry_delay))
    for attempt in range(total_attempts):
        jar = _load_browser_cookies_once(browser, parsed_source)
        if jar is not None:
            return jar
        if attempt + 1 < total_attempts and delay:
            time.sleep(delay)
    return None


def _load_browser_cookies_once(browser: str, parsed_source):
    """Try one read-only cookie-database snapshot."""
    logger = _CookieLogger()
    try:
        config = ytdlp_cookies._get_chromium_based_browser_settings(browser)
        browser_root = config["browser_dir"]
        database_path = ytdlp_cookies._newest(
            ytdlp_cookies._find_files(browser_root, "Cookies", logger)
        )
        if not database_path or not os.path.isfile(database_path):
            return None

        connection = _open_read_only_database(database_path)
        try:
            connection.text_factory = bytes
            cursor = connection.cursor()
            meta_row = cursor.execute(
                "SELECT value FROM meta WHERE key = 'version'"
            ).fetchone()
            meta_version = int(meta_row[0]) if meta_row else 0
            decryptor = ytdlp_cookies.get_cookie_decryptor(
                browser_root,
                config["keyring_name"],
                logger,
                meta_version=meta_version,
            )
            columns = ytdlp_cookies._get_column_names(cursor, "cookies")
            secure_column = "is_secure" if "is_secure" in columns else "secure"
            rows = cursor.execute(
                f"SELECT host_key, name, value, encrypted_value, path, expires_utc, {secure_column} FROM cookies"
            ).fetchall()
            jar = ytdlp_cookies.YoutubeDLCookieJar()
            for row in rows:
                if not _cookie_matches_source(row, parsed_source):
                    continue
                try:
                    _is_encrypted, cookie = ytdlp_cookies._process_chrome_cookie(
                        decryptor, *row
                    )
                except Exception:
                    continue
                if cookie:
                    jar.set_cookie(cookie)
            return jar if len(jar) else None
        finally:
            connection.close()
    except Exception:
        return None


def _open_read_only_database(database_path: str):
    """Open the live database without requesting a write or lock handle."""
    database_uri = Path(database_path).resolve().as_uri()
    last_error: Optional[BaseException] = None
    for query in ("mode=ro&cache=private", "mode=ro&immutable=1"):
        connection = None
        try:
            connection = sqlite3.connect(f"{database_uri}?{query}", uri=True)
            connection.execute("PRAGMA query_only = ON")
            connection.execute("SELECT 1")
            return connection
        except (OSError, sqlite3.Error) as error:
            last_error = error
            if connection is not None:
                connection.close()
    if last_error is not None:
        raise last_error
    raise sqlite3.OperationalError("Could not open the browser cookie database read-only")


def _cookie_matches_source(row: tuple[Any, ...], parsed_source) -> bool:
    host_value, _name, _value, _encrypted_value, path_value, expires_utc, is_secure = row
    host = (parsed_source.hostname or "").lower().rstrip(".")
    if not host:
        return False

    cookie_domain = _decode(host_value).lower().lstrip(".").rstrip(".")
    if not cookie_domain or (host != cookie_domain and not host.endswith(f".{cookie_domain}")):
        return False

    cookie_path = _decode(path_value) or "/"
    request_path = parsed_source.path or "/"
    if not _path_matches(cookie_path, request_path):
        return False
    if bool(is_secure) and parsed_source.scheme != "https":
        return False

    try:
        # Chromium stores expiry as microseconds since 1601-01-01 UTC.
        if expires_utc:
            expires_at = (int(expires_utc) / 1_000_000) - _CHROMIUM_EPOCH_OFFSET
            if expires_at <= time.time():
                return False
    except (TypeError, ValueError, OverflowError):
        pass
    return True


def _path_matches(cookie_path: str, request_path: str) -> bool:
    if request_path == cookie_path:
        return True
    if not request_path.startswith(cookie_path.rstrip("/") + "/"):
        return False
    return cookie_path == "/" or request_path.startswith(cookie_path)


def _decode(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")
