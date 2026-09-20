"""Tests for the consent-based local browser bridge payload."""

import io
import json

import pytest

from engine.browser_bridge import CookieBridgeError, cookie_jar_from_payload, read_cookie_jar_from_stdin


def _payload(*cookies):
    return json.dumps({"cookies": list(cookies)})


def _cookie(**overrides):
    value = {
        "name": "c_user",
        "value": "123",
        "domain": ".facebook.com",
        "path": "/",
        "secure": True,
        "httpOnly": True,
        "hostOnly": False,
    }
    value.update(overrides)
    return value


def test_cookie_jar_from_payload_keeps_only_source_scoped_cookies():
    jar = cookie_jar_from_payload(
        _payload(
            _cookie(),
            _cookie(name="not_for_source", domain=".example.com"),
            _cookie(name="wrong_path", path="/other"),
        ),
        "https://www.facebook.com/reel/123",
    )

    assert [(cookie.domain, cookie.name, cookie.value) for cookie in jar] == [
        (".facebook.com", "c_user", "123"),
    ]


def test_read_cookie_jar_from_stdin_enforces_the_source_url():
    jar = read_cookie_jar_from_stdin(
        io.BytesIO(_payload(_cookie()).encode("utf-8")),
        "https://www.facebook.com/reel/123",
    )

    assert [(cookie.name, cookie.value) for cookie in jar] == [("c_user", "123")]


@pytest.mark.parametrize(
    ("payload", "source_url"),
    [
        ("{}", "https://www.facebook.com/reel/123"),
        (_payload(_cookie(value="bad\nvalue")), "https://www.facebook.com/reel/123"),
        (_payload(_cookie(domain=".example.com")), "https://www.facebook.com/reel/123"),
        (_payload(_cookie(secure=True)), "http://www.facebook.com/reel/123"),
    ],
)
def test_cookie_bridge_rejects_invalid_or_unusable_payloads(payload, source_url):
    with pytest.raises(CookieBridgeError):
        cookie_jar_from_payload(payload, source_url)


def test_cookie_bridge_rejects_an_oversized_payload():
    oversized = _payload(_cookie(value="x" * 9000))

    with pytest.raises(CookieBridgeError, match="too large"):
        cookie_jar_from_payload(oversized, "https://www.facebook.com/reel/123")
