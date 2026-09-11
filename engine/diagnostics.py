"""Safe, copyable diagnostics for consumer support requests."""

import os
import platform
import shutil
import subprocess
from typing import Dict

from engine.paths import APP_DATA_DIR
from engine.version import __version__


def _tool_version(executable: str) -> str:
    path = shutil.which(executable)
    if not path:
        return "not found"
    try:
        result = subprocess.run(
            [path, "-version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=5.0, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        first_line = (result.stdout or "").splitlines()[0:1]
        return first_line[0].strip() if first_line else "available"
    except Exception:
        return "available (version check failed)"


def collect_diagnostics() -> Dict[str, str]:
    try:
        import yt_dlp
        engine_version = getattr(yt_dlp.version, "__version__", "unknown")
    except Exception:
        engine_version = "not available"
    return {
        "JaneConverter": __version__,
        "Operating system": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "Python": platform.python_version(),
        "FFmpeg": _tool_version("ffmpeg"),
        "FFprobe": _tool_version("ffprobe"),
        "yt-dlp": engine_version,
        "Application data": os.path.basename(os.path.normpath(APP_DATA_DIR)),
    }


def format_diagnostics() -> str:
    lines = ["JaneConverter diagnostics", "=" * 28]
    lines.extend(f"{key}: {value}" for key, value in collect_diagnostics().items())
    return "\n".join(lines)
