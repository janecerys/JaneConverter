"""Tests for the temporary localhost browser-media handoff."""

from threading import Event
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from janeconverter.account_access import AccountAccessServer


EXTENSION_ORIGIN = "chrome-extension://test-extension"


def _request(url, *, data=None, headers=None, method=None):
    request = Request(url, data=data, headers=headers or {}, method=method)
    return urlopen(request, timeout=2)


def test_account_access_link_confirms_without_accepting_browser_secrets():
    ready = Event()
    server = AccountAccessServer(
        "https://example.com/private-media",
        on_ready=lambda _detection: ready.set(),
    )
    link = server.start()

    landing = urlopen(link, timeout=2).read().decode("utf-8")
    assert "https://example.com/private-media" in landing
    assert "password" in landing
    assert "cookies" in landing
    assert "cache" in landing

    confirmation = urlopen(f"{link}/ready", timeout=2).read().decode("utf-8")
    assert "Access confirmed" in confirmation
    assert ready.wait(2)

    server.stop()


def test_account_access_confirms_the_browser_that_opened_the_link():
    ready = Event()
    detected = []
    server = AccountAccessServer(
        "https://example.com/private-media",
        on_ready=lambda browser: (detected.append(browser), ready.set()),
    )
    link = server.start()
    vivaldi_request = Request(
        f"{link}/ready",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "Chrome/138.0.0.0 Safari/537.36 Vivaldi/7.0.3495.6"
            ),
        },
    )
    page = urlopen(vivaldi_request, timeout=2).read().decode("utf-8")

    assert "Browser detected: <strong>Vivaldi</strong>" in page
    assert ready.wait(2)
    assert detected[0].label == "Vivaldi"
    assert detected[0].session_browser == "vivaldi"
    server.stop()


def test_account_access_can_bind_a_source_on_first_capture():
    server = AccountAccessServer("")
    link = server.start()

    landing = urlopen(link, timeout=2).read().decode("utf-8")
    assert "No source URL was provided" in landing
    urlopen(f"{link}/ready", timeout=2).read()

    challenge = json.loads(
        _request(
            f"{link}/bridge/challenge",
            headers={"Origin": EXTENSION_ORIGIN},
        ).read().decode("utf-8")
    )
    assert challenge["sourceUrl"] == ""

    metadata = json.dumps(
        {
            "fileName": "capture.webm",
            "mediaKind": "video",
            "mimeType": "video/webm",
            "captureMode": "current",
            "pageUrl": "https://example.com/private-media",
            "expectedBytes": 1,
        }
    ).encode("utf-8")
    start = json.loads(
        _request(
            f"{link}/bridge/capture/start",
            data=metadata,
            headers={
                "Content-Type": "application/json",
                "Origin": EXTENSION_ORIGIN,
                "X-JaneConverter-Bridge": challenge["bridgeToken"],
            },
            method="POST",
        ).read().decode("utf-8")
    )
    assert start["captureId"]

    rebound = json.loads(
        _request(
            f"{link}/bridge/challenge",
            headers={"Origin": EXTENSION_ORIGIN},
        ).read().decode("utf-8")
    )
    assert rebound["sourceUrl"] == "https://example.com/private-media"
    server.stop()


def test_account_access_bridge_transfers_media_bytes_not_cookies():
    server = AccountAccessServer("https://example.com/private-media")
    link = server.start()
    urlopen(f"{link}/ready", timeout=2).read()

    challenge = json.loads(
        _request(
            f"{link}/bridge/challenge",
            headers={"Origin": EXTENSION_ORIGIN},
        ).read().decode("utf-8")
    )
    assert challenge["sourceUrl"] == "https://example.com/private-media"
    assert challenge["confirmed"] is True
    assert challenge["connected"] is False
    assert challenge["bridgeToken"]

    metadata = json.dumps(
        {
            "fileName": "capture.mp4",
            "mediaKind": "video",
            "mimeType": "video/mp4",
            "captureMode": "current",
            "pageUrl": "https://example.com/private-media",
            "expectedBytes": 6,
        }
    ).encode("utf-8")
    start = json.loads(
        _request(
            f"{link}/bridge/capture/start",
            data=metadata,
            headers={
                "Content-Type": "application/json",
                "Origin": EXTENSION_ORIGIN,
                "X-JaneConverter-Bridge": challenge["bridgeToken"],
            },
            method="POST",
        ).read().decode("utf-8")
    )
    capture_id = start["captureId"]

    _request(
        f"{link}/bridge/capture/chunk",
        data=b"abc",
        headers={
            "Content-Type": "application/octet-stream",
            "Origin": EXTENSION_ORIGIN,
            "X-JaneConverter-Bridge": challenge["bridgeToken"],
            "X-JaneConverter-Capture-Id": capture_id,
            "X-JaneConverter-Capture-Offset": "0",
        },
        method="POST",
    ).read()
    _request(
        f"{link}/bridge/capture/chunk",
        data=b"def",
        headers={
            "Content-Type": "application/octet-stream",
            "Origin": EXTENSION_ORIGIN,
            "X-JaneConverter-Bridge": challenge["bridgeToken"],
            "X-JaneConverter-Capture-Id": capture_id,
            "X-JaneConverter-Capture-Offset": "3",
        },
        method="POST",
    ).read()
    finish = json.loads(
        _request(
            f"{link}/bridge/capture/finish",
            data=json.dumps({"captureId": capture_id}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Origin": EXTENSION_ORIGIN,
                "X-JaneConverter-Bridge": challenge["bridgeToken"],
                "X-JaneConverter-Capture-Id": capture_id,
            },
            method="POST",
        ).read().decode("utf-8")
    )

    assert finish["ok"] is True
    assert server.bridge_connected
    assert server.captured_media_path.read_bytes() == b"abcdef"
    server.stop()


def test_account_access_bridge_rejects_webpage_origins():
    server = AccountAccessServer("https://example.com/private-media")
    link = server.start()
    urlopen(f"{link}/ready", timeout=2).read()

    with pytest.raises(HTTPError) as rejected:
        _request(
            f"{link}/bridge/challenge",
            headers={"Origin": "https://untrusted.example"},
        )
    assert rejected.value.code == 403
    server.stop()


def test_bridge_challenge_keeps_cors_for_unconfirmed_extension():
    server = AccountAccessServer("https://example.com/private-media")
    link = server.start()

    with pytest.raises(HTTPError) as unconfirmed:
        _request(
            f"{link}/bridge/challenge",
            headers={"Origin": EXTENSION_ORIGIN},
        )

    assert unconfirmed.value.code == 409
    assert unconfirmed.value.headers["Access-Control-Allow-Origin"] == EXTENSION_ORIGIN
    server.stop()
