"""Tests for opt-in browser-session authentication."""

import pytest

import engine.auth as auth
import engine.extractor as extractor
from engine.auth import (
    detect_browser_from_headers,
    browser_session_label,
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
    info = extractor.fetch_media_stream(
        "https://www.facebook.com/watch/?v=123",
        str(tmp_path),
        auth_browser="Chrome",
    )

    assert info["media_path"] == str(downloaded.resolve())
    assert captured["cookiesfrombrowser"] == ("chrome", None, None, None)
    assert "cookiefile" not in captured
