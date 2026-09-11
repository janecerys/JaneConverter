"""Validated, restart-time application update staging.

The running application never replaces its own files. A release archive can be
validated and unpacked into the user's update area, then applied before the next
launch with rollback if any file operation fails.
"""

import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from typing import Optional

from engine.paths import APP_DATA_DIR


UPDATE_ROOT = os.path.join(APP_DATA_DIR, "updates")
PENDING_MANIFEST = os.path.join(UPDATE_ROOT, "pending.json")
MAX_UPDATE_MEMBERS = 4096
MAX_UPDATE_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_archive_member(name: str) -> bool:
    """Reject traversal, drive-qualified, and alternate-stream ZIP paths."""
    normalized = str(name or "").replace("\\", "/")
    if not normalized or normalized.startswith("/") or normalized.startswith("\\"):
        return False
    if len(normalized) >= 2 and normalized[1] == ":":
        return False
    if "\x00" in normalized or ":" in normalized:
        return False
    parts = [part for part in normalized.split("/") if part]
    return bool(parts) and all(part not in (".", "..") for part in parts)


def stage_release_archive(archive_path: str, version: str,
                          expected_sha256: Optional[str] = None) -> str:
    """Validate and stage a release ZIP; return the pending manifest path."""
    archive_path = os.path.abspath(archive_path)
    if not os.path.isfile(archive_path) or not zipfile.is_zipfile(archive_path):
        raise ValueError("The update package is missing or is not a valid ZIP archive.")
    archive_hash = _sha256(archive_path)
    if expected_sha256 and archive_hash.lower() != expected_sha256.lower():
        raise ValueError("The update package checksum does not match the expected release checksum.")

    os.makedirs(UPDATE_ROOT, exist_ok=True)
    staging_dir = tempfile.mkdtemp(prefix="pending-", dir=UPDATE_ROOT)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            if len(members) > MAX_UPDATE_MEMBERS:
                raise ValueError("The update package contains too many files.")
            total_size = 0
            for member in members:
                if member.flag_bits & 0x1:
                    raise ValueError("Encrypted update packages are not supported.")
                if not _safe_archive_member(member.filename):
                    raise ValueError("The update package contains an unsafe file path.")
                total_size += max(0, member.file_size)
                if total_size > MAX_UPDATE_UNCOMPRESSED_BYTES:
                    raise ValueError("The update package is too large to stage safely.")
            archive.extractall(staging_dir)

        files = {}
        for root, _, names in os.walk(staging_dir):
            for name in names:
                path = os.path.join(root, name)
                relative = os.path.relpath(path, staging_dir).replace(os.sep, "/")
                files[relative] = _sha256(path)
        manifest = {
            "version": str(version),
            "archive_sha256": archive_hash,
            "staging_dir": os.path.abspath(staging_dir),
            "files": files,
        }
        temporary_manifest = PENDING_MANIFEST + ".tmp"
        with open(temporary_manifest, "w", encoding="utf-8") as target:
            json.dump(manifest, target, indent=2)
        os.replace(temporary_manifest, PENDING_MANIFEST)
        return PENDING_MANIFEST
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise


def apply_pending_update(application_dir: str) -> bool:
    """Apply a validated pending update with rollback; return whether it was applied."""
    if not os.path.isfile(PENDING_MANIFEST):
        return False
    try:
        with open(PENDING_MANIFEST, "r", encoding="utf-8") as source:
            manifest = json.load(source)
        staging_dir = os.path.abspath(manifest["staging_dir"])
        if not os.path.isdir(staging_dir):
            raise FileNotFoundError("The staged update directory is missing.")
        files = manifest.get("files", {})
        app_dir = os.path.abspath(application_dir)
        backup_dir = tempfile.mkdtemp(prefix="rollback-", dir=UPDATE_ROOT)
        copied = []
        try:
            for relative, expected_hash in files.items():
                relative_os = os.path.normpath(relative.replace("/", os.sep))
                if relative_os in (".", "..") or relative_os.startswith(".." + os.sep) or os.path.isabs(relative_os):
                    raise ValueError("The staged update contains an unsafe path.")
                source_path = os.path.join(staging_dir, relative_os)
                target_path = os.path.join(app_dir, relative_os)
                if not os.path.isfile(source_path) or _sha256(source_path) != expected_hash:
                    raise ValueError(f"Staged update file failed validation: {relative}")
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                if os.path.isfile(target_path):
                    backup_path = os.path.join(backup_dir, relative_os)
                    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                    shutil.copy2(target_path, backup_path)
                temporary_target = target_path + ".update-tmp"
                shutil.copy2(source_path, temporary_target)
                os.replace(temporary_target, target_path)
                copied.append((relative_os, os.path.isfile(os.path.join(backup_dir, relative_os))))
        except Exception:
            for relative_os, had_backup in reversed(copied):
                target_path = os.path.join(app_dir, relative_os)
                backup_path = os.path.join(backup_dir, relative_os)
                if had_backup:
                    shutil.copy2(backup_path, target_path)
                elif os.path.exists(target_path):
                    os.remove(target_path)
            raise
        finally:
            shutil.rmtree(backup_dir, ignore_errors=True)
        shutil.rmtree(staging_dir, ignore_errors=True)
        os.remove(PENDING_MANIFEST)
        return True
    except Exception:
        # Leave the manifest in place so the next launch can report/retry it,
        # while never replacing files after a failed validation.
        return False
