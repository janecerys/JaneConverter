"""Collect local hardware and process telemetry for the desktop dashboard."""

from __future__ import annotations

import csv
import math
import os
import platform
import shutil
import subprocess
from typing import Any


def _cpu_name() -> str:
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            ) as key:
                name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
                return " ".join(str(name).split()) or "Host processor"
        except (ImportError, OSError, AttributeError):
            pass
    elif platform.system().lower() == "linux":
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="replace") as cpuinfo:
                for line in cpuinfo:
                    if line.lower().startswith(("model name", "hardware")):
                        _, value = line.split(":", 1)
                        if value.strip():
                            return " ".join(value.split())
        except OSError:
            pass
    elif platform.system().lower() == "darwin":
        try:
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=1.0,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return " ".join(result.stdout.split())
        except (OSError, subprocess.SubprocessError):
            pass
    return " ".join((platform.processor() or platform.machine() or "Host processor").split())


def _number(value: str, default: float = 0.0) -> float:
    try:
        number = float(value.strip())
    except (AttributeError, TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _nvidia_snapshot(target_pids: set[int]) -> dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {}
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            [
                executable,
                "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1.5,
            creationflags=creation_flags,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {}
        fields = next(csv.reader([result.stdout.splitlines()[0]], skipinitialspace=True))
        if len(fields) < 5:
            return {}

        app_vram = 0
        process_result = subprocess.run(
            [
                executable,
                "--query-compute-apps=pid,used_memory",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1.5,
            creationflags=creation_flags,
            check=False,
        )
        for row in csv.reader(process_result.stdout.splitlines(), skipinitialspace=True):
            if len(row) >= 2 and row[0].strip().isdigit() and int(row[0]) in target_pids:
                app_vram += int(_number(row[1]))

        return {
            "gpuName": fields[0].strip() or "NVIDIA GPU",
            "gpuSystemPct": _number(fields[1]),
            "gpuVramUsedMb": int(_number(fields[2])),
            "gpuVramTotalMb": int(_number(fields[3])),
            "gpuAppVramMb": app_vram,
            "gpuTempC": int(_number(fields[4])) if _number(fields[4], -1.0) >= 0 else None,
            "telemetrySource": "nvidia-smi",
        }
    except (OSError, StopIteration, subprocess.SubprocessError):
        return {}


def get_hardware_snapshot(target_pid: int) -> dict[str, Any]:
    """Return one local-only system and JaneConverter process sample."""
    try:
        import psutil
    except ImportError as error:  # pragma: no cover - psutil is a declared runtime dependency
        raise RuntimeError("Hardware telemetry requires the local psutil runtime.") from error

    logical_cores = psutil.cpu_count(logical=True) or os.cpu_count() or 1
    processes = []
    try:
        root = psutil.Process(int(target_pid))
        processes = [root, *root.children(recursive=True)]
    except (OSError, ValueError, psutil.Error):
        root = None

    # The telemetry helper is itself a temporary child of the app. Exclude it
    # so starting this sample does not inflate JaneConverter's reported usage.
    processes = [process for process in processes if process.pid != os.getpid()]
    process_ids = {process.pid for process in processes}
    for process in processes:
        try:
            process.cpu_percent(interval=None)
        except (OSError, psutil.Error):
            continue

    cpu_system_pct = psutil.cpu_percent(interval=0.25)
    cpu_app_pct = 0.0
    ram_app_bytes = 0
    for process in processes:
        try:
            cpu_app_pct += process.cpu_percent(interval=None)
            ram_app_bytes += process.memory_info().rss
        except (OSError, psutil.Error):
            continue

    memory = psutil.virtual_memory()
    gpu = _nvidia_snapshot(process_ids)
    return {
        "cpuName": _cpu_name(),
        "logicalCores": logical_cores,
        "cpuSystemPct": round(min(100.0, max(0.0, cpu_system_pct)), 1),
        "cpuAppPct": round(min(100.0, max(0.0, cpu_app_pct / logical_cores)), 1),
        "ramSystemPct": round(float(memory.percent), 1),
        "ramUsedGb": round((memory.total - memory.available) / (1024 ** 3), 1),
        "ramTotalGb": round(memory.total / (1024 ** 3), 1),
        "ramAppMb": round(ram_app_bytes / (1024 ** 2), 1),
        "gpuSystemPct": gpu.get("gpuSystemPct", 0.0),
        "gpuVramUsedMb": gpu.get("gpuVramUsedMb", 0),
        "gpuVramTotalMb": gpu.get("gpuVramTotalMb", 0),
        "gpuAppVramMb": gpu.get("gpuAppVramMb", 0),
        "gpuTempC": gpu.get("gpuTempC"),
        "gpuName": gpu.get("gpuName", "Not available"),
        "telemetrySource": gpu.get("telemetrySource", "Unavailable"),
    }
