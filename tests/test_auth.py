"""Tests for opt-in browser-session authentication."""

import http.cookiejar

import pytest

import janeconverter.auth as auth
import janeconverter.extractor as extractor
from janeconverter.auth import (
    describe_authenticated_extraction_failure,
    detect_browser_from_headers,
    browser_session_label,
    normalize_browser_error_message,
    normalize_browser_session,
    yt_dlp_cookie_option,
)


@pytest.mark.parametrize(
    ("selection", "expected"),
    [
        (None, None),
        ("Public only", None),
        ("none", None),
        ("Chrome", "chrome"),
        ("EDGE", "edge"),
        ("Firefox", "firefox"),
        ("Brave", "brave"),
        ("Vivaldi", "vivaldi"),
    ],
)
def test_normalize_browser_session(selection, expected):
    assert normalize_browser_session(selection) == expected


def test_browser_cookie_option_is_in_memory_only():
    assert yt_dlp_cookie_option("Chrome") == ("chrome", None, None, None)
    assert yt_dlp_cookie_option("Public only") is None


def test_browser_error_message_uses_chromium_terminology():
    assert normalize_browser_error_message("Could not copy Chrome cookie database") == (
        "Could not copy Chromium cookie database"
    )


def test_dpapi_failure_explains_browser_session_recovery():
    message = describe_authenticated_extraction_failure(
        "vivaldi",
        RuntimeError("ERROR: Failed to decrypt with DPAPI"),
    )

    assert "Vivaldi" in message
    assert "Windows could not decrypt" in message
    assert "same Windows account" in message
    assert "default browser profile" in message


def test_cookie_database_copy_failure_explains_vivaldi_recovery(monkeypatch):
    monkeypatch.setattr(auth, "browser_process_is_running", lambda _selection: False)
    message = describe_authenticated_extraction_failure(
        "vivaldi",
        RuntimeError("ERROR: Could not copy Chrome cookie database."),
    )

    assert "Vivaldi was detected" in message
    assert "Chromium" in message
    assert "no Vivaldi process" in message
    assert "profile or Windows permission" in message
    assert "retry the conversion" in message
    assert "does not copy or save your cookies" in message


def test_cookie_database_copy_failure_identifies_running_browser(monkeypatch):
    monkeypatch.setattr(auth, "browser_process_is_running", lambda _selection: True)
    message = describe_authenticated_extraction_failure(
        "vivaldi",
        RuntimeError("ERROR: Could not copy Chrome cookie database."),
    )

    assert "Vivaldi is still running" in message
    assert "background process" in message


def test_cookie_database_copy_failure_distinguishes_closed_browser(monkeypatch):
    monkeypatch.setattr(auth, "browser_process_is_running", lambda _selection: False)
    message = describe_authenticated_extraction_failure(
        "vivaldi",
        RuntimeError("ERROR: Could not copy Chrome cookie database."),
    )

    assert "no Vivaldi process" in message
    assert "profile or Windows permission" in message


def test_browser_session_rejects_unknown_values():
    with pytest.raises(ValueError, match="Unsupported browser session"):
        normalize_browser_session("Unknown Browser")


def test_browser_session_label_is_stable():
    assert browser_session_label("firefox") == "Firefox"
    assert browser_session_label(None) == "Public only"


@pytest.mark.parametrize(
    ("signal", "expected"),
    [
        ("VivaldiHTM", "vivaldi"),
        ("VivaldiURL", "vivaldi"),
        (r'"C:\\Program Files\\Vivaldi\\Application\\vivaldi.exe" "%1"', "vivaldi"),
        (r'"C:\\Program Files\\BraveSoftware\\Brave-Browser\\brave.exe" "%1"', "brave"),
        (r'"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" "%1"', "edge"),
        ("unknown-browser", None),
    ],
)
def test_default_browser_signal_detection(signal, expected):
    assert auth._browser_from_signal(signal) == expected


def test_browser_request_headers_detect_vivaldi():
    detection = detect_browser_from_headers({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Vivaldi/7.0.3495.6"
        ),
    })
    assert detection.label == "Vivaldi"
    assert detection.session_browser == "vivaldi"


def test_browser_request_headers_detects_unknown_browser_without_guessing():
    detection = detect_browser_from_headers({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CustomBrowser/1.0",
    })
    assert detection.label == "Unrecognized browser"
    assert detection.session_browser is None


def test_default_browser_detection_uses_association_fallback(monkeypatch):
    monkeypatch.setattr(auth.os, "name", "nt")
    monkeypatch.setattr(auth, "_windows_default_browser_signals", lambda: [
        r'"C:\\Users\\User\\AppData\\Local\\Vivaldi\\Application\\vivaldi.exe" "%1"',
    ])
    assert auth.detect_default_browser_session() == "vivaldi"


def test_default_browser_detection_reads_real_host_association():
    detected = auth.detect_default_browser_session()
    assert detected in {None, "chrome", "edge", "firefox", "brave", "vivaldi", "opera"}


def test_fetch_media_stream_passes_browser_session_without_cookie_file(tmp_path, monkeypatch):
    captured = {}
    progress_messages = []
    downloaded = tmp_path / "authorized_video.mp4"

    class FakeYoutubeDL:
        def __init__(self, options):
            captured.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _source, download=True):
            assert download is True
            downloaded.write_bytes(b"media")
            return {"title": "Authorized video", "id": "abc", "uploader": "Creator"}

        def prepare_filename(self, _info):
            return str(downloaded)

    monkeypatch.setattr(extractor.yt_dlp, "YoutubeDL", FakeYoutubeDL)
    monkeypatch.setattr(extractor, "load_browser_cookies_read_only", lambda *_args: None)
    info = extractor.fetch_media_stream(
        "https://www.facebook.com/watch/?v=123",
        str(tmp_path),
        auth_browser="Chrome",
        progress_callback=lambda _pct, message: progress_messages.append(message),
    )

    assert info["media_path"] == str(downloaded.resolve())
    assert captured["cookiesfrombrowser"] == ("chrome", None, None, None)
    assert "cookiefile" not in captured
    captured["logger"].error("ERROR: Could not copy Chrome cookie database")
    assert progress_messages[-1] == "ERROR: Could not copy Chromium cookie database"


def test_fetch_media_stream_attaches_read_only_browser_jar_in_memory(tmp_path, monkeypatch):
    downloaded = tmp_path / "authorized_video.mp4"
    attached = []
    jar = http.cookiejar.CookieJar()
    jar.set_cookie(http.cookiejar.Cookie(
        version=0,
        name="c_user",
        value="123",
        port=None,
        port_specified=False,
        domain=".facebook.com",
        domain_specified=True,
        domain_initial_dot=True,
        path="/",
        path_specified=True,
        secure=True,
        expires=None,
        discard=True,
        comment=None,
        comment_url=None,
        rest={},
    ))

    class FakeYoutubeDL:
        def __init__(self, options):
            self.cookiejar = http.cookiejar.CookieJar()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _source, download=True):
            assert download is True
            attached.extend(self.cookiejar)
            downloaded.write_bytes(b"media")
            return {"title": "Authorized video", "id": "abc", "uploader": "Creator"}

        def prepare_filename(self, _info):
            return str(downloaded)

    monkeypatch.setattr(extractor.yt_dlp, "YoutubeDL", FakeYoutubeDL)
    monkeypatch.setattr(extractor, "load_browser_cookies_read_only", lambda *_args: jar)
    extractor.fetch_media_stream(
        "https://www.facebook.com/watch/?v=123",
        str(tmp_path),
        auth_browser="Vivaldi",
    )

    assert [(cookie.name, cookie.value) for cookie in attached] == [("c_user", "123")]


def test_fetch_media_stream_prefers_bridge_jar_over_browser_database(tmp_path, monkeypatch):
    downloaded = tmp_path / "bridge_video.mp4"
    attached = []
    jar = http.cookiejar.CookieJar()
    jar.set_cookie(http.cookiejar.Cookie(
        version=0,
        name="c_user",
        value="bridge-value",
        port=None,
        port_specified=False,
        domain=".facebook.com",
        domain_specified=True,
        domain_initial_dot=True,
        path="/",
        path_specified=True,
        secure=True,
        expires=None,
        discard=True,
        comment=None,
        comment_url=None,
        rest={},
    ))

    class FakeYoutubeDL:
        def __init__(self, _options):
            self.cookiejar = http.cookiejar.CookieJar()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _source, download=True):
            assert download is True
            attached.extend(self.cookiejar)
            downloaded.write_bytes(b"media")
            return {"title": "Bridge video", "id": "bridge", "uploader": "Creator"}

        def prepare_filename(self, _info):
            return str(downloaded)

    monkeypatch.setattr(extractor.yt_dlp, "YoutubeDL", FakeYoutubeDL)
    monkeypatch.setattr(extractor, "get_active_browser_cookie_jar", lambda: jar)
    monkeypatch.setattr(
        extractor,
        "load_browser_cookies_read_only",
        lambda *_args: pytest.fail("the locked browser database should not be read when the bridge jar exists"),
    )

    extractor.fetch_media_stream(
        "https://www.facebook.com/watch/?v=bridge",
        str(tmp_path),
        auth_browser="Vivaldi",
    )

    assert [(cookie.name, cookie.value) for cookie in attached] == [("c_user", "bridge-value")]
