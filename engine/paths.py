"""Runtime paths for the portable, project-local JaneConverter layout.

JaneConverter is distributed as a portable folder, so keeping its generated
data beside the application avoids filling the system drive and makes the
whole installation easy to back up or move. A user-supplied data directory
and a safe per-user fallback are still supported for protected locations.
"""

import os
import filecmp
import shutil
import tempfile


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
LEGACY_APP_DATA_DIR = os.path.join(_local_app_data, "JaneConverter") if _local_app_data else ""


def _writable_directory(path: str) -> bool:
    """Return whether *path* can be created and written to."""
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write-test")
        with open(probe, "w", encoding="utf-8"):
            pass
        os.remove(probe)
        return True
    except OSError:
        return False


def _unique_destination(path: str) -> str:
    """Return a non-existing path so a migration never overwrites data."""
    if not os.path.exists(path):
        return path
    stem, extension = os.path.splitext(path)
    counter = 1
    while True:
        candidate = f"{stem} (migrated {counter}){extension}"
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def _merge_entry(source: str, destination: str) -> None:
    """Move an entry, recursively merging directories when both exist."""
    if os.path.isdir(source) and not os.path.islink(source):
        if os.path.isdir(destination) and not os.path.islink(destination):
            for child in os.scandir(source):
                _merge_entry(child.path, os.path.join(destination, child.name))
            os.rmdir(source)
            return
    if os.path.isfile(source) and os.path.isfile(destination):
        # A previous attempt may have copied the file but been unable to remove
        # the source because another process has it open. Do not duplicate it
        # on every subsequent launch.
        if filecmp.cmp(source, destination, shallow=False):
            return
    shutil.move(source, _unique_destination(destination))


def _rewrite_legacy_destination(config_path: str, legacy_root: str, new_root: str) -> None:
    """Update a migrated settings file that still points to AppData."""
    try:
        import json

        with open(config_path, "r", encoding="utf-8") as settings_file:
            settings = json.load(settings_file)
        destination = settings.get("destination")
        old_converted = os.path.normcase(
            os.path.abspath(os.path.join(legacy_root, "converted"))
        )
        if isinstance(destination, str) and os.path.normcase(os.path.abspath(destination)) == old_converted:
            settings["destination"] = os.path.join(new_root, "converted")
            with open(config_path, "w", encoding="utf-8") as settings_file:
                json.dump(settings, settings_file, indent=2)
    except (OSError, ValueError, TypeError):
        # A malformed settings file should not prevent the application from launching.
        return


def migrate_legacy_app_data(legacy_root: str, new_root: str) -> bool:
    """Merge the old AppData store into the project-local store.

    Existing files are retained and conflicts receive a ``(migrated N)``
    suffix. The old root is removed only after every child has been moved.
    Returns ``True`` when anything was migrated.
    """
    if not legacy_root:
        return False
    legacy_root = os.path.abspath(legacy_root)
    new_root = os.path.abspath(new_root)
    if not os.path.isdir(legacy_root):
        return False
    if os.path.normcase(legacy_root) == os.path.normcase(new_root):
        return False
    if not _writable_directory(new_root):
        return False

    migrated = False
    for entry in os.scandir(legacy_root):
        # The current portable settings win when both locations already have
        # a config file. This also avoids generating config (migrated N).json
        # when Windows has temporarily locked the legacy file.
        if entry.name == "config.json" and os.path.exists(os.path.join(new_root, entry.name)):
            continue
        try:
            _merge_entry(entry.path, os.path.join(new_root, entry.name))
            migrated = True
        except OSError:
            # Keep inaccessible legacy data in place and allow the app to use
            # the new default. A later launch can retry after permissions or
            # file locks have been resolved.
            continue

    config_path = os.path.join(new_root, "config.json")
    if os.path.isfile(config_path):
        _rewrite_legacy_destination(config_path, legacy_root, new_root)
    try:
        os.rmdir(legacy_root)
    except OSError:
        pass
    return migrated


def get_app_data_dir() -> str:
    configured = os.environ.get("JANECONVERTER_DATA_DIR", "").strip()
    if configured:
        return os.path.abspath(configured)

    # Portable installs keep exports, settings, logs, and scratch files beside
    # JaneConverter. This is the normal path and avoids silently consuming C:.
    if _writable_directory(BASE_DIR):
        migrate_legacy_app_data(LEGACY_APP_DATA_DIR, BASE_DIR)
        return BASE_DIR

    # Protected install locations (for example Program Files) need a writable
    # per-user fallback. This keeps the application functional for consumers.
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        candidate = os.path.join(local_app_data, "JaneConverter")
        if _writable_directory(candidate):
            return candidate
    return os.path.join(tempfile.gettempdir(), "JaneConverter")


APP_DATA_DIR = get_app_data_dir()
DEFAULT_CONVERTED_DIR = os.path.join(APP_DATA_DIR, "converted")
DEFAULT_TEMP_DIR = os.path.join(APP_DATA_DIR, "temp")
LOG_DIR = os.path.join(APP_DATA_DIR, "logs")
CONFIG_PATH = os.path.join(APP_DATA_DIR, "config.json")
