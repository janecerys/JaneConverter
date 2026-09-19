"""Regression coverage for the Windows installer prerequisites."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_windows_installer_does_not_trust_the_store_python_alias():
    """The installer must validate Python by executing it, not only finding a command name."""
    installer = (REPO_ROOT / "install.ps1").read_text(encoding="utf-8")

    assert "function Get-UsablePythonRuntime" in installer
    assert "$pythonRuntime = Get-UsablePythonRuntime" in installer
    assert "if (-not $pythonRuntime)" in installer
    assert "& $pythonRuntime.Command -m venv" in installer
    assert "Get-Command python" not in installer.split("# 1. Check Python", 1)[1].split("# 2. Check FFmpeg", 1)[0]