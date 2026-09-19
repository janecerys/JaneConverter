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

def test_windows_installer_uses_non_interactive_dependency_installers():
    """Automatic setup must not pause for source agreements or hide all progress."""
    installer = (REPO_ROOT / "install.ps1").read_text(encoding="utf-8")

    assert "--source winget" in installer
    assert "--silent" in installer
    assert "--disable-interactivity" in installer
    assert "pip install --upgrade pip --quiet" not in installer
    assert "pip install -r requirements.txt --quiet" not in installer

def test_setup_batch_does_not_require_manual_enter_after_failure():
    """Double-click setup must close automatically instead of waiting on PAUSE."""
    setup = (REPO_ROOT / "setup.bat").read_text(encoding="utf-8")

    assert "pause" not in setup.lower()
    assert "timeout /t" in setup.lower()
    assert "set \"setup_exit=%errorlevel%\"" in setup.lower()
