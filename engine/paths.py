"""Runtime paths that keep consumer data separate from application code."""

import os
import tempfile


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_app_data_dir() -> str:
    configured = os.environ.get("JANECONVERTER_DATA_DIR", "").strip()
    if configured:
        return os.path.abspath(configured)
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        candidate = os.path.join(local_app_data, "JaneConverter")
        try:
            os.makedirs(candidate, exist_ok=True)
            probe = os.path.join(candidate, ".write-test")
            with open(probe, "w", encoding="utf-8"):
                pass
            os.remove(probe)
            return candidate
        except OSError:
            pass
    # Some locked-down Windows profiles expose LOCALAPPDATA but do not grant
    # applications write access to it. Fall back to the per-user temp folder.
    return os.path.join(tempfile.gettempdir(), "JaneConverter")


APP_DATA_DIR = get_app_data_dir()
DEFAULT_CONVERTED_DIR = os.path.join(APP_DATA_DIR, "converted")
DEFAULT_TEMP_DIR = os.path.join(APP_DATA_DIR, "temp")
LOG_DIR = os.path.join(APP_DATA_DIR, "logs")
CONFIG_PATH = os.path.join(APP_DATA_DIR, "config.json")
