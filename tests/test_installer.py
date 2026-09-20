"""Regression coverage for the Windows installer prerequisites."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_windows_installer_does_not_trust_the_store_python_alias():
    """The installer must validate Python by executing it, not only finding a command name."""
    installer = (REPO_ROOT / "install.ps1").read_text(encoding="utf-8")

    assert "function Get-UsablePythonRuntime" in installer
    assert "$pythonRuntime = Get-UsablePythonRuntime" in installer
    assert "if (-not $pythonRuntime)" in installer
    assert "& $pythonRuntime.Command @venvArguments" in installer
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

def test_windows_installer_discovers_python_outside_the_first_path_entry():
    """The installer must try the Python launcher and alternate executable paths."""
    installer = (REPO_ROOT / "install.ps1").read_text(encoding="utf-8")

    assert "python3.exe" in installer
    assert "py.exe" in installer
    assert "Get-Command $commandName -All" in installer
    assert "sys.executable" in installer


def test_windows_installer_stops_when_private_environment_creation_did_not_work():
    """A missing venv interpreter must fail with a useful error before pip runs."""
    installer = (REPO_ROOT / "install.ps1").read_text(encoding="utf-8")

    assert "--clear" in installer
    assert "Test-Path -LiteralPath $venvPython" in installer
    assert "Private Python environment" in installer


def test_windows_installer_builds_and_places_the_main_tauri_ui():
    """Setup must make the default Main UI available to the universal launcher."""
    installer = (REPO_ROOT / "install.ps1").read_text(encoding="utf-8")

    assert '$desktopUiDir = Join-Path $scriptDir "desktop-ui"' in installer
    assert 'src-tauri\\Cargo.toml' in installer
    assert "tauri:build" in installer
    assert "JaneConverterDesktop.exe" in installer
    assert "CARGO_TARGET_DIR" in installer
    assert 'Set-Content -LiteralPath (Join-Path $scriptDir "frontend.preference") -Value "tauri"' in installer


def test_windows_installer_guides_default_browser_extension_install():
    """Setup must open the default Chromium browser's extension manager."""
    installer = (REPO_ROOT / "install.ps1").read_text(encoding="utf-8")

    assert "Get-DefaultBrowser" in installer
    assert 'Join-Path $ExtensionPath "manifest.json"' in installer
    assert "chrome://extensions" in installer
    assert "Load unpacked" in installer
    assert "Read-Host" in installer
    assert "Manual Browser Bridge installation" in installer
