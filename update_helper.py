"""Apply a staged JaneConverter update after the launcher has exited.

This helper is intentionally tiny and short-lived. The launcher starts it,
then exits so Windows releases the files that a staged release may replace.
"""

import ctypes
import os
import subprocess
import sys
import time


def wait_for_parent(pid: int) -> None:
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(0x00100000, False, pid)
        if handle:
            kernel32.WaitForSingleObject(handle, 30000)
            kernel32.CloseHandle(handle)
            return
    for _ in range(300):
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.1)


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    application_dir = os.path.abspath(sys.argv[1])
    try:
        parent_pid = int(sys.argv[2])
    except ValueError:
        return 2
    wait_for_parent(parent_pid)
    try:
        from engine.staged_update import apply_pending_update

        apply_pending_update(application_dir)
    except Exception:
        # Leave the manifest in place for a later retry and relaunch the
        # existing installation so a failed update never strands the user.
        pass
    launcher = os.path.join(application_dir, "JaneConverter.exe")
    if os.path.isfile(launcher):
        subprocess.Popen(
            [launcher, "--skip-pending-update"],
            cwd=application_dir,
            close_fds=True,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
