import hashlib
import os
import zipfile

from engine import staged_update


def test_release_archive_is_staged_and_applied_with_checksum(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "gui.py").write_text("old", encoding="utf-8")
    package_root = tmp_path / "package"
    package_root.mkdir()
    (package_root / "gui.py").write_text("new", encoding="utf-8")
    archive = tmp_path / "release.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.write(package_root / "gui.py", "gui.py")
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    monkeypatch.setattr(staged_update, "UPDATE_ROOT", str(tmp_path / "updates"))
    monkeypatch.setattr(staged_update, "PENDING_MANIFEST", str(tmp_path / "updates" / "pending.json"))

    staged_update.stage_release_archive(str(archive), "1.1.0", checksum)
    assert staged_update.apply_pending_update(str(app_dir))
    assert (app_dir / "gui.py").read_text(encoding="utf-8") == "new"
    assert not os.path.exists(staged_update.PENDING_MANIFEST)


def test_release_archive_rejects_bad_checksum(tmp_path, monkeypatch):
    archive = tmp_path / "release.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("gui.py", "new")
    monkeypatch.setattr(staged_update, "UPDATE_ROOT", str(tmp_path / "updates"))
    monkeypatch.setattr(staged_update, "PENDING_MANIFEST", str(tmp_path / "updates" / "pending.json"))
    try:
        staged_update.stage_release_archive(str(archive), "1.1.0", "bad")
    except ValueError as error:
        assert "checksum" in str(error).lower()
    else:
        raise AssertionError("bad checksum was accepted")


def test_release_archive_rejects_traversal_and_windows_special_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(staged_update, "UPDATE_ROOT", str(tmp_path / "updates"))
    monkeypatch.setattr(staged_update, "PENDING_MANIFEST", str(tmp_path / "updates" / "pending.json"))
    for member_name in ("../escape.txt", r"C:\escape.txt", "folder/../../escape.txt", "config.json:stream"):
        archive = tmp_path / (member_name.replace("/", "_").replace("\\", "_").replace(":", "_") + ".zip")
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr(member_name, "unsafe")
        try:
            staged_update.stage_release_archive(str(archive), "1.1.0")
        except ValueError as error:
            assert "unsafe" in str(error).lower()
        else:
            raise AssertionError(f"unsafe archive member was accepted: {member_name}")
