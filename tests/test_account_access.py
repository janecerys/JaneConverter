"""Tests for the temporary localhost account-access handoff."""

from threading import Event
import json
from urllib.request import Request, urlopen

from engine.account_access import AccountAccessServer


def test_account_access_link_is_local_and_confirms_once():
    ready = Event()
    server = AccountAccessServer(
        "https://example.com/private-media",
        on_ready=lambda _detection: ready.set(),
    )
    link = server.start()

    assert link.startswith("http://127.0.0.1:")
    landing = urlopen(link, timeout=2).read().decode("utf-8")
    assert "https://example.com/private-media" in landing
    assert "does not receive" in landing
    assert "copy or upload your cookies" in landing

    confirmation = urlopen(
        f"{link}/ready",
        timeout=2,
    ).read().decode("utf-8")
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


def test_account_access_bridge_accepts_confirmed_source_scoped_payload():
    server = AccountAccessServer("https://example.com/private-media")
    link = server.start()

    confirmation = urlopen(f"{link}/ready", timeout=2).read().decode("utf-8")
    assert "Browser Bridge" in confirmation

    challenge = json.loads(urlopen(f"{link}/bridge/challenge", timeout=2).read().decode("utf-8"))
    assert challenge == {"sourceUrl": "https://example.com/private-media", "confirmed": True}

    payload = json.dumps(
        {
            "cookies": [
                {
                    "name": "session",
                    "value": "authorized",
                    "domain": ".example.com",
                    "path": "/",
                    "secure": True,
                }
            ]
        }
    ).encode("utf-8")
    response = urlopen(
        Request(
            f"{link}/bridge",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        ),
        timeout=2,
    )
    assert json.loads(response.read().decode("utf-8")) == {"ok": True}
    assert server.bridge_connected
    assert server.bridge_payload == payload.decode("utf-8")
    server.stop()
