"""Tests for the live-browser, read-only cookie path."""

import sqlite3

import engine.browser_cookies as browser_cookies


def test_load_browser_cookies_reads_only_matching_live_source_cookies(tmp_path, monkeypatch):
    browser_root = tmp_path / "Vivaldi" / "User Data"
    database_path = browser_root / "Default" / "Network" / "Cookies"
    database_path.parent.mkdir(parents=True)

    connection = sqlite3.connect(database_path)
    connection.execute("CREATE TABLE meta (key TEXT, value TEXT)")
    connection.execute("INSERT INTO meta VALUES ('version', '24')")
    connection.execute(
        "CREATE TABLE cookies (host_key TEXT, name TEXT, value TEXT, encrypted_value BLOB, "
        "path TEXT, expires_utc INTEGER, is_secure INTEGER)"
    )
    connection.executemany(
        "INSERT INTO cookies VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (".facebook.com", "c_user", "123", b"", "/", 0, 1),
            (".example.com", "not_for_facebook", "secret", b"", "/", 0, 1),
        ],
    )
    connection.commit()
    connection.close()

    class FakeDecryptor:
        _cookie_counts = {}

    monkeypatch.setattr(
        browser_cookies.ytdlp_cookies,
        "_get_chromium_based_browser_settings",
        lambda _browser: {"browser_dir": str(browser_root), "keyring_name": "Vivaldi"},
    )
    monkeypatch.setattr(
        browser_cookies.ytdlp_cookies,
        "_find_files",
        lambda _root, _filename, _logger: iter([str(database_path)]),
    )
    monkeypatch.setattr(
        browser_cookies.ytdlp_cookies,
        "get_cookie_decryptor",
        lambda *_args, **_kwargs: FakeDecryptor(),
    )

    jar = browser_cookies.load_browser_cookies_read_only(
        "vivaldi",
        "https://www.facebook.com/reel/123",
    )

    assert jar is not None
    assert [(cookie.domain, cookie.name, cookie.value) for cookie in jar] == [
        (".facebook.com", "c_user", "123"),
    ]


def test_load_browser_cookies_does_not_use_the_live_path_for_non_chromium_browsers(monkeypatch):
    find_called = False

    def fail_if_called(*_args, **_kwargs):
        nonlocal find_called
        find_called = True
        raise AssertionError("non-Chromium sessions should not inspect a cookie database")

    monkeypatch.setattr(browser_cookies.ytdlp_cookies, "_find_files", fail_if_called)

    assert browser_cookies.load_browser_cookies_read_only(
        "firefox",
        "https://www.facebook.com/reel/123",
    ) is None
    assert find_called is False


def test_load_browser_cookies_retries_a_transient_live_database_failure(monkeypatch):
    attempts = []
    expected_jar = object()

    def load_once(browser, parsed_source):
        attempts.append((browser, parsed_source.hostname))
        return expected_jar if len(attempts) == 3 else None

    monkeypatch.setattr(browser_cookies, "_load_browser_cookies_once", load_once)
    monkeypatch.setattr(browser_cookies.time, "sleep", lambda _delay: None)

    jar = browser_cookies.load_browser_cookies_read_only(
        "vivaldi",
        "https://www.facebook.com/reel/123",
        attempts=4,
        retry_delay=0.75,
    )

    assert jar is expected_jar
    assert len(attempts) == 3
