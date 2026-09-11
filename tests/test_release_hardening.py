"""Regression tests for bounded events, source routing, and safe update defaults."""

import os

from engine.events import BoundedLogQueue, CoalescingCallbackQueue
from engine.extractor import identify_source_type, is_playlist_url
from engine.updater import check_and_apply_all_updates, update_engine
from run_converter import media_library_folder, _metadata_folder


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


def test_single_item_metadata_isolated_by_source(tmp_path):
    first = _metadata_folder(str(tmp_path), "https://youtube.com/watch?v=one", "Same Title")
    second = _metadata_folder(str(tmp_path), "https://soundcloud.com/artist/same", "Same Title")
    assert first != second
    assert first.endswith(os.path.join("metadata", "Same Title_" + first.rsplit("_", 1)[-1]))


def test_updates_are_read_only_by_default(monkeypatch):
    monkeypatch.setattr("engine.updater.check_for_engine_updates", lambda: {
        "has_update": False, "online": True, "current_version": "1", "latest_version": "1"
    })
    monkeypatch.setattr("engine.updater.check_for_repo_updates", lambda: {
        "has_update": False, "is_git": False, "current_commit": "unknown", "commits_behind": 0
    })
    result = check_and_apply_all_updates()
    assert result["already_up_to_date"] is True
    assert result["repo_updated"] is False
    assert result["engine_updated"] is False


def test_engine_install_requires_explicit_permission(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("pip must not run during a read-only update check")

    monkeypatch.setattr("engine.updater.subprocess.run", fail_if_called)
    result = update_engine(info={
        "has_update": True,
        "online": True,
        "current_version": "2026.1",
        "latest_version": "2026.2",
    })
    assert result is False
