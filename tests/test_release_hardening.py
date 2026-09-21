"""Regression tests for bounded events, source routing, and safe update defaults."""

import os
from pathlib import Path

from janeconverter.events import BoundedLogQueue, CoalescingCallbackQueue
from janeconverter.extractor import identify_source_type, is_playlist_url
from janeconverter import updater
from janeconverter.updater import check_and_apply_all_updates, update_engine
from janeconverter.cli import CLI_CATEGORIES, media_library_folder, _metadata_folder


def test_source_updater_resolves_repository_root():
    assert (Path(updater.REPO_DIR) / "pyproject.toml").is_file()


def test_progress_queue_coalesces_and_bounds_callbacks():
    events = CoalescingCallbackQueue(max_callbacks=2)
    values = []
    for value in range(100_000):
        events.put(lambda v=value: values.append(v), key="progress")
    callbacks = events.drain(max_items=10)
    for callback in callbacks:
        callback()
    assert values == [99_999]
    assert events.qsize() == 0


def test_log_queue_drops_under_pressure_and_batches():
    logs = BoundedLogQueue(max_items=2)
    assert logs.put("a")
    assert logs.put("b")
    assert not logs.put("c")
    assert logs.dropped == 1
    assert logs.get_batch() == ["a", "b"]


def test_source_matching_does_not_accept_lookalike_domains():
    assert identify_source_type("https://not-spotify.com/track/1") == "generic_url"
    assert identify_source_type("https://cdn.youtube.com/video/1") == "youtube"
    assert is_playlist_url("https://open.spotify.com/album/abc123")


def test_library_folder_keeps_sources_separate_except_miscellaneous(tmp_path):
    root = str(tmp_path)
    assert media_library_folder(root, "mp3", "spotify", "Music").endswith(os.path.join("Music", "Spotify"))
    assert media_library_folder(root, "mp4", "youtube", "Video").endswith(os.path.join("Videos", "YouTube"))
    assert media_library_folder(root, "mp3", "spotify", "Miscellaneous").endswith(os.path.join("Miscellaneous", "Audio"))
    assert media_library_folder(root, "png", "facebook", "Image").endswith(os.path.join("Images", "Facebook"))


def test_cli_categories_include_image_capture_output():
    assert "Image" in CLI_CATEGORIES


def test_single_item_metadata_isolated_by_source(tmp_path):
    first = _metadata_folder(str(tmp_path), "https://youtube.com/watch?v=one", "Same Title")
    second = _metadata_folder(str(tmp_path), "https://soundcloud.com/artist/same", "Same Title")
    assert first != second
    assert first.endswith(os.path.join("metadata", "Same Title_" + first.rsplit("_", 1)[-1]))


def test_updates_are_read_only_by_default(monkeypatch):
    monkeypatch.setattr("janeconverter.updater.check_for_engine_updates", lambda: {
        "has_update": False, "online": True, "current_version": "1", "latest_version": "1"
    })
    monkeypatch.setattr("janeconverter.updater.check_for_repo_updates", lambda: {
        "has_update": False, "is_git": False, "current_commit": "unknown", "commits_behind": 0
    })
    result = check_and_apply_all_updates()
    assert result["already_up_to_date"] is True
    assert result["repo_updated"] is False
    assert result["engine_updated"] is False


def test_engine_install_requires_explicit_permission(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("the package installer must not run during a read-only update check")

    monkeypatch.setattr("janeconverter.updater.subprocess.run", fail_if_called)
    result = update_engine(info={
        "has_update": True,
        "online": True,
        "current_version": "2026.1",
        "latest_version": "2026.2",
    })
    assert result is False


def test_published_release_check_finds_newer_github_version_and_installer(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "tag_name": "v1.3.0",
                "html_url": "https://github.com/janecerys/JaneConverter/releases/tag/v1.3.0",
                "assets": [
                    {
                        "name": "JaneConverter-1.3.0-windows-x64-setup.exe",
                        "browser_download_url": "https://github.com/janecerys/JaneConverter/releases/download/v1.3.0/JaneConverter-1.3.0-windows-x64-setup.exe",
                    },
                    {
                        "name": "JaneConverter-1.3.0-windows-x64-setup.exe.sha256",
                        "browser_download_url": "https://github.com/janecerys/JaneConverter/releases/download/v1.3.0/JaneConverter-1.3.0-windows-x64-setup.exe.sha256",
                    },
                ],
            }

    requested = {}

    def fake_get(url, **kwargs):
        requested.update(url=url, kwargs=kwargs)
        return FakeResponse()

    monkeypatch.setattr(updater.requests, "get", fake_get)
    monkeypatch.setattr(updater, "__version__", "1.2.0")

    result = updater.check_for_release_updates()

    assert result["has_update"] is True
    assert result["current_version"] == "1.2.0"
    assert result["latest_version"] == "1.3.0"
    assert result["installer_available"] is True
    assert result["installer_url"].endswith("JaneConverter-1.3.0-windows-x64-setup.exe")
    assert result["installer_checksum_url"].endswith(
        "JaneConverter-1.3.0-windows-x64-setup.exe.sha256"
    )
    assert result["release_url"].endswith("/v1.3.0")
    assert requested["url"] == updater.GITHUB_LATEST_RELEASE_URL
    assert requested["kwargs"]["headers"]["User-Agent"].startswith("JaneConverter/")


def test_application_update_downloads_and_verifies_the_installer(monkeypatch, tmp_path):
    installer_bytes = b"trusted installer bytes"
    checksum = __import__("hashlib").sha256(installer_bytes).hexdigest()

    class FakeResponse:
        def __init__(self, body):
            self.status_code = 200
            self.body = body

        def iter_content(self, chunk_size=65536):
            del chunk_size
            yield self.body

        @property
        def text(self):
            return self.body.decode("utf-8")

        @property
        def content(self):
            return self.body

    def fake_get(url, **kwargs):
        del kwargs
        if url.endswith(".sha256"):
            return FakeResponse(f"{checksum}  JaneConverter-2.3.0-windows-x64-setup.exe\n".encode())
        return FakeResponse(installer_bytes)

    monkeypatch.setattr(updater.requests, "get", fake_get)
    monkeypatch.setattr(updater.tempfile, "mkdtemp", lambda prefix: str(tmp_path))

    result = updater.download_application_update({
        "has_update": True,
        "latest_version": "2.3.0",
        "installer_url": "https://github.com/janecerys/JaneConverter/releases/download/v2.3.0/JaneConverter-2.3.0-windows-x64-setup.exe",
        "installer_checksum_url": "https://github.com/janecerys/JaneConverter/releases/download/v2.3.0/JaneConverter-2.3.0-windows-x64-setup.exe.sha256",
    })

    assert result["success"] is True
    assert Path(result["installer_path"]).read_bytes() == installer_bytes


def test_non_git_snapshot_uses_published_release_check(monkeypatch):
    monkeypatch.setattr(updater, "is_git_repo", lambda: False)
    monkeypatch.setattr(updater, "check_for_release_updates", lambda **_: {
        "has_update": True,
        "online": True,
        "current_version": "1.2.0",
        "latest_version": "1.3.0",
        "installer_available": True,
        "release_url": "https://github.com/janecerys/JaneConverter/releases/tag/v1.3.0",
        "error": None,
    })

    result = updater.check_for_repo_updates()

    assert result["is_git"] is False
    assert result["has_update"] is True
    assert result["current_version"] == "1.2.0"
    assert result["latest_version"] == "1.3.0"
    assert result["installer_available"] is True
