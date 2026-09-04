"""
Auto-Update Engine for JaneConverter
Checks PyPI for the latest yt-dlp extractor releases on every launch.
Ensures stream extractors for YouTube, TikTok, Twitter, and other platforms stay current.
"""

import sys
import subprocess
from typing import Optional, Dict, Any, Callable
import requests
import yt_dlp

def get_current_engine_version() -> str:
    """Returns the currently installed version of yt-dlp."""
    return getattr(yt_dlp.version, "__version__", "unknown")

def check_for_engine_updates(timeout_seconds: float = 3.0) -> Dict[str, Any]:
    """
    Queries PyPI API to check if a newer yt-dlp release is available.
    Fails gracefully if offline or request times out.
    """
    current_ver = get_current_engine_version()
    try:
        resp = requests.get("https://pypi.org/pypi/yt-dlp/json", timeout=timeout_seconds)
        if resp.status_code == 200:
            data = resp.json()
            latest_ver = data.get("info", {}).get("version", current_ver)
            has_update = False
            try:
                from packaging import version
                has_update = version.parse(latest_ver) > version.parse(current_ver)
            except Exception:
                has_update = latest_ver != current_ver

            return {
                "has_update": has_update,
                "current_version": current_ver,
                "latest_version": latest_ver,
                "online": True
            }
    except Exception:
        pass

    return {
        "has_update": False,
        "current_version": current_ver,
        "latest_version": current_ver,
        "online": False
    }

def update_engine(status_callback: Optional[Callable[[str], None]] = None) -> bool:
    """
    Upgrades yt-dlp to the latest release via pip in the background.
    Returns True if successfully updated.
    """
    def log(msg: str):
        if status_callback:
            status_callback(msg)
        print(f"[AutoUpdate] {msg}")

    log("Checking for real-time extractor engine updates...")
    info = check_for_engine_updates()

    if not info["online"]:
        log(f"Offline or network unreachable. Using installed engine (v{info['current_version']}).")
        return False

    if not info["has_update"]:
        log(f"Extractor engine is already up to date (v{info['current_version']}).")
        return False

    log(f"New engine release detected: v{info['latest_version']}. Upgrading now...")

    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp", "--quiet"]

    try:
        res = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=no_window)
        if res.returncode == 0:
            log(f"Engine successfully updated to v{info['latest_version']}.")
            return True
        log("Engine upgrade command returned non-zero code.")
        return False
    except Exception as e:
        log(f"Notice: Automatic engine upgrade skipped ({e}).")
        return False
