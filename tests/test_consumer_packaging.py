"""Contract tests for the dual JaneConverter distribution paths."""

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_consumer_build_contract_keeps_the_portable_safety_net():
    script = (REPO_ROOT / "packaging" / "build_consumer.ps1").read_text(encoding="utf-8")

    assert "build_release.ps1" in script
    assert "JaneConverterEngine.exe" in script
    assert "JaneConverterPython.exe" in script
    assert "ffmpeg.exe" in script
    assert "ffprobe.exe" in script
    assert "tauriCli" in script
    assert "build --config" in script
    assert "JaneConverter-Setup.exe" in script


def test_consumer_runtime_manifest_declares_the_private_runtime_files():
    manifest = json.loads(
        (REPO_ROOT / "packaging" / "consumer-manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["engine"] == "JaneConverterEngine.exe"
    assert manifest["legacy_python"] == "JaneConverterPython.exe"
    assert manifest["ffmpeg"] == ["ffmpeg.exe", "ffprobe.exe"]
    assert manifest["portable_fallback"] == "build_release.ps1"


def test_consumer_installer_preserves_explicit_extension_consent():
    hook = (REPO_ROOT / "packaging" / "windows" / "installer-hooks.nsh").read_text(
        encoding="utf-8"
    )

    assert "JaneConverter.exe" in hook
    assert "browser-extension" in hook
    assert "CreateShortCut" in hook
    assert "NSIS_HOOK_POSTINSTALL" in hook


def test_frozen_engine_entrypoint_keeps_source_cli_compatibility():
    entrypoint = (REPO_ROOT / "packaging" / "engine_entry.py").read_text(encoding="utf-8")

    assert "run_converter.py" in entrypoint
    assert "from run_converter import main" in entrypoint
    assert "sys.argv" in entrypoint


def test_engine_has_a_packaged_update_check_mode():
    runner = (REPO_ROOT / "run_converter.py").read_text(encoding="utf-8")

    assert "--check-updates" in runner


def test_all_launchers_can_find_packaged_runtime_binaries():
    launcher = (REPO_ROOT / "Program.cs").read_text(encoding="utf-8")
    tauri_paths = (REPO_ROOT / "desktop-ui" / "src-tauri" / "src" / "paths.rs").read_text(
        encoding="utf-8"
    )
    native = (REPO_ROOT / "native_ui" / "src" / "main.rs").read_text(encoding="utf-8")

    for source in (launcher, tauri_paths, native):
        assert "JaneConverterEngine.exe" in source
        assert "resources" in source
    assert "JaneConverterPython.exe" in launcher
    assert "janeconverter-desktop.exe" in launcher
    assert "--check-updates" in native
