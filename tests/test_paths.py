"""Tests for portable storage paths and legacy data migration."""

import json
import os
from pathlib import Path

from janeconverter.paths import APP_DATA_DIR, BASE_DIR, DEFAULT_CONVERTED_DIR, _writable_directory, migrate_legacy_app_data


def test_portable_default_converted_folder_is_next_to_application():
    assert (Path(BASE_DIR) / "pyproject.toml").is_file()
    assert os.path.normcase(DEFAULT_CONVERTED_DIR) == os.path.normcase(
        os.path.join(APP_DATA_DIR, "converted")
    )
    # Normal portable installs use BASE_DIR; protected installs use the
    # documented writable fallback instead.
    assert os.path.normcase(APP_DATA_DIR) in {
        os.path.normcase(BASE_DIR),
        os.path.normcase(os.path.join(os.environ.get("TEMP", ""), "JaneConverter")),
    } or os.path.normcase(APP_DATA_DIR).startswith(
        os.path.normcase(os.path.join(os.environ.get("LOCALAPPDATA", ""), "JaneConverter"))
    ) or os.path.normcase(APP_DATA_DIR).startswith(
        os.path.normcase(os.path.join(os.environ.get("APPDATA", ""), "JaneConverter"))
    )


def test_migrate_legacy_app_data_merges_without_overwriting(tmp_path):
    legacy = tmp_path / "legacy"
    current = tmp_path / "current"
    legacy_converted = legacy / "converted" / "Music" / "YouTube"
    current_converted = current / "converted" / "Music" / "YouTube"
    legacy_converted.mkdir(parents=True)
    current_converted.mkdir(parents=True)
    (legacy_converted / "old.mp3").write_text("legacy", encoding="utf-8")
    (current_converted / "old.mp3").write_text("current", encoding="utf-8")
    (legacy_converted / "new.mp3").write_text("new", encoding="utf-8")
    (legacy / "config.json").write_text(
        json.dumps({"destination": str(legacy / "converted")}), encoding="utf-8"
    )

    assert migrate_legacy_app_data(str(legacy), str(current)) is True
    assert not legacy.exists()
    assert (current_converted / "old.mp3").read_text(encoding="utf-8") == "current"
    assert (current_converted / "old (migrated 1).mp3").read_text(encoding="utf-8") == "legacy"
    assert (current_converted / "new.mp3").read_text(encoding="utf-8") == "new"
    settings = json.loads((current / "config.json").read_text(encoding="utf-8"))
    assert os.path.normcase(settings["destination"]) == os.path.normcase(str(current / "converted"))


def test_migrate_legacy_app_data_preserves_program_binaries(tmp_path):
    legacy = tmp_path / "legacy"
    current = tmp_path / "current"
    legacy.mkdir(parents=True)
    current.mkdir(parents=True)
    (legacy / "JaneConverter.exe").write_text("binary", encoding="utf-8")
    (legacy / "resources").mkdir()
    (legacy / "resources" / "runtime.txt").write_text("runtime", encoding="utf-8")
    (legacy / "config.json").write_text(json.dumps({"theme": "dark"}), encoding="utf-8")

    assert migrate_legacy_app_data(str(legacy), str(current)) is True
    assert legacy.exists()
    assert (legacy / "JaneConverter.exe").exists()
    assert (legacy / "resources" / "runtime.txt").exists()
    assert (current / "config.json").exists()
    assert not (current / "JaneConverter.exe").exists()


def test_migrate_legacy_app_data_is_idempotent_when_source_is_missing(tmp_path):
    assert migrate_legacy_app_data(str(tmp_path / "missing"), str(tmp_path / "current")) is False


def test_writable_probe_never_overwrites_a_user_named_write_test(tmp_path):
    probe = tmp_path / ".write-test"
    probe.write_text("keep me", encoding="utf-8")
    assert _writable_directory(str(tmp_path)) is True
    assert probe.read_text(encoding="utf-8") == "keep me"


def test_cleanup_update_cache_removes_old_update_folders(tmp_path, monkeypatch):
    from janeconverter.updater import cleanup_update_cache
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

    old1 = tmp_path / "janeconverter-update-12345"
    old2 = tmp_path / "janecoverter-update-67890"
    other = tmp_path / "other-file-to-keep"
    old1.mkdir()
    old2.mkdir()
    other.mkdir()

    cleanup_update_cache()

    assert not old1.exists()
    assert not old2.exists()
    assert other.exists()
