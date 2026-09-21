"""Release-package contract tests for the single production desktop UI."""

import json
from pathlib import Path
import zipfile

from janeconverter.version import __version__


REPO_ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_manifest_defines_one_ui_engine_and_toolset():
    manifest = json.loads(read("packaging/consumer-manifest.json"))

    assert manifest["schema"] == 2
    assert manifest["ui"] == {
        "windows": "JaneConverter.exe",
        "linux": "JaneConverter",
    }
    assert manifest["private_runtime"] == "resources/runtime"
    assert manifest["documents"] == ["LICENSE"]
    assert manifest["engine"]["pyinstaller_mode"] == "onedir"
    assert manifest["engine"]["support_directory"] == "_internal"
    assert manifest["tools"]["windows"] == [
        "ffmpeg.exe",
        "ffprobe.exe",
        "node.exe",
    ]
    assert manifest["tools"]["linux"] == ["ffmpeg", "ffprobe", "node"]
    assert len(manifest["artifacts"]) == 3


def test_windows_build_stages_one_private_runtime_for_both_outputs():
    script = read("packaging/build_consumer.ps1")

    assert "--onedir" in script
    assert "--onefile" not in script
    assert '"resources\\runtime"' in script
    assert '"engine"' in script and '"bin"' in script
    assert "$SkipInstaller" in script and "$SkipPortable" in script
    assert "windows-x64-setup.exe" in script
    assert "windows-x64-portable.zip" in script
    assert "installMode = \"currentUser\"" in script
    assert '"Frozen engine smoke test"' in script
    assert "installerHooks" not in script
    for obsolete in ("Program.cs", "JaneConverterPython.exe", "JaneConverterNative.exe"):
        assert script.count(obsolete) == 1  # rejection list only


def test_linux_build_is_x86_64_tarball_without_appimage():
    script = read("packaging/build_linux.sh")

    assert script.startswith("#!/usr/bin/env bash")
    assert "x86_64" in script and "Unsupported architecture" in script
    assert "--ffmpeg" in script and "--ffprobe" in script and "--node" in script
    assert "--onedir" in script
    assert "linux-x86_64.tar.gz" in script
    assert "install -m 0755" in script
    assert '"$RUNTIME_ENGINE/JaneConverterEngine" --version' in script
    assert "AppImage" not in script


def test_tauri_runtime_paths_support_frozen_windows_and_linux_engines():
    paths = read("desktop-ui/src-tauri/src/paths.rs")
    process = read("desktop-ui/src-tauri/src/process.rs")

    assert 'join("resources").join("runtime")' in paths
    assert 'join("engine")' in paths
    assert '"JaneConverterEngine.exe"' in paths
    assert '"JaneConverterEngine"' in paths
    assert 'join("bin")' in paths
    assert 'command.env("PATH"' in paths
    assert 'command.env("JANECONVERTER_DATA_DIR"' in paths
    assert 'var_os("XDG_DATA_HOME")' in paths
    assert 'var_os("LOCALAPPDATA")' in paths
    assert 'join("pyproject.toml")' in paths
    assert 'join("uv.lock")' in paths
    assert '"run", "--locked", "janeconverter"' in process
    assert "!packaged_engine(&engine)" in process


def test_tauri_relaunch_starts_the_current_desktop_executable():
    library = read("desktop-ui/src-tauri/src/lib.rs")
    relaunch = library.split("fn relaunch", 1)[1].split("fn format_update_summary", 1)[0]

    assert "std::env::current_exe()" in relaunch
    assert "JaneConverter.exe" not in relaunch
    assert "run_converter.sh" not in relaunch


def test_release_workflow_builds_and_publishes_only_agreed_platforms():
    workflow = read(".github/workflows/release.yml")

    assert "workflow_dispatch:" in workflow
    assert 'tags:\n      - "v*"' in workflow
    assert "windows-latest" in workflow
    assert "ubuntu-22.04" in workflow
    assert "checksums.sha256" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "actions/download-artifact@v4" in workflow
    assert "gh release create" in workflow
    assert "github.token" in workflow
    assert "AppImage" not in workflow
    assert "macos" not in workflow.lower()


def test_frozen_engine_entrypoint_calls_installed_package_cli():
    entrypoint = read("packaging/engine_entry.py")

    assert "from janeconverter.cli import main" in entrypoint
    assert "run_converter.py" not in entrypoint


def test_browser_bridge_archive_matches_the_source_extension():
    manifest = json.loads(read("browser-extension/manifest.json"))
    source_popup = (REPO_ROOT / "browser-extension" / "popup.js").read_text(encoding="utf-8")
    archives = sorted((REPO_ROOT / "browser-extension" / "releases").glob("JaneConverter-Browser-Bridge-*.zip"))
    assert archives
    assert archives[-1].stem.endswith(manifest["version"])
    assert "allFrames: true" in source_popup
    assert "blob:" in source_popup
    assert "captureStream" in source_popup
    assert "MAX_RENDERED_CAPTURE_BYTES" in source_popup

    with zipfile.ZipFile(archives[-1]) as archive:
        names = set(archive.namelist())
        assert names == {"manifest.json", "media-utils.js", "popup.html", "popup.js", "README.md", "collect.js", "service-worker.js", "network-capture.js", "extension-worker.js"}
        packaged_manifest = json.loads(archive.read("manifest.json"))

    assert packaged_manifest == manifest
    assert packaged_manifest["host_permissions"] == [
        "http://127.0.0.1/*",
        "http://localhost/*",
    ]
    assert packaged_manifest["optional_host_permissions"] == manifest["optional_host_permissions"]
    assert "*://*/*" not in json.dumps(packaged_manifest["optional_host_permissions"])
    assert "https://facebook.com/*" in packaged_manifest["optional_host_permissions"]
    assert "debugger" in packaged_manifest["permissions"]


def test_engine_has_a_packaged_update_check_mode():
    assert "--check-updates" in read("src/janeconverter/cli.py")


def test_python_project_exposes_the_supported_console_command():
    project = read("pyproject.toml")

    assert 'janeconverter = "janeconverter.cli:main"' in project
    assert 'path = "src/janeconverter/version.py"' in project
    assert (REPO_ROOT / "src" / "janeconverter" / "__init__.py").is_file()


def test_application_versions_are_aligned():
    package = json.loads(read("desktop-ui/package.json"))
    tauri = json.loads(read("desktop-ui/src-tauri/tauri.conf.json"))
    browser_bridge = json.loads(read("browser-extension/manifest.json"))
    cargo = read("desktop-ui/src-tauri/Cargo.toml")
    cargo_lock = read("desktop-ui/src-tauri/Cargo.lock")

    assert __version__ == "2.0.0"
    assert package["version"] == __version__
    assert tauri["version"] == __version__
    assert browser_bridge["version"] == __version__
    assert f'version = "{__version__}"' in cargo
    assert f'name = "janeconverter-desktop"\nversion = "{__version__}"' in cargo_lock
