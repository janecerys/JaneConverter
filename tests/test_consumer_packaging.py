"""Release-package contract tests for the single production desktop UI."""

import json
from pathlib import Path
import subprocess
import sys
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
        "macos": "JaneConverter.app",
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
    assert manifest["engine"]["macos"] == "JaneConverterEngine"
    assert manifest["tools"]["macos"] == ["ffmpeg", "ffprobe", "node"]
    assert manifest["artifacts"] == [
        "JaneConverter-<version>-windows-x64-setup.exe",
        "JaneConverter-<version>-windows-x64-portable.zip",
        "JaneConverter-<version>-linux-x86_64.tar.gz",
        "JaneConverter-<version>-macos-arm64.dmg",
        "JaneConverter-<version>-macos-x86_64.dmg",
    ]
    assert len(manifest["artifacts"]) == 5


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


def test_macos_build_is_native_arch_specific_and_ad_hoc_signed():
    script = read("packaging/build_macos.sh")

    assert script.startswith("#!/usr/bin/env bash")
    assert '"$(uname -s)" != "Darwin"' in script
    assert '"arm64"' in script and '"x86_64"' in script
    assert "sysctl.proc_translated" in script
    for option in ("--ffmpeg", "--ffprobe", "--node", "--output-dir", "--keep-staging"):
        assert option in script
    assert "uv run --locked pyinstaller" in script
    assert "--onedir" in script and "--onefile" not in script
    assert 'RUNTIME_ROOT="$STAGING_ROOT/runtime"' in script
    assert "install -m 0755" in script
    assert "assert_macho_arch" in script
    assert "xattr -dr com.apple.quarantine" in script
    assert "codesign --force --sign -" in script
    assert 'config["bundle"]["targets"] = ["dmg"]' in script
    assert 'setdefault("macOS", {})["signingIdentity"] = "-"' in script
    assert "macos-$ARCH.dmg" in script
    assert "shasum -a 256" in script
    assert "uv run --locked python" in script
    assert "python3" not in script and "pip " not in script


def test_tauri_runtime_paths_support_frozen_windows_linux_and_macos_engines():
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
    assert 'join("Library")' in paths
    assert 'join("Application Support")' in paths
    assert 'join("Resources").join("runtime")' in paths
    assert "macos_bundle_runtime(directory)" in paths
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


def test_release_workflow_builds_and_publishes_all_agreed_platforms():
    workflow = read(".github/workflows/release.yml")

    assert "workflow_dispatch:" in workflow
    assert 'tags:\n      - "v*"' in workflow
    assert "windows-latest" in workflow
    assert "ubuntu-22.04" in workflow
    assert "- arch: arm64\n            runner: macos-latest" in workflow
    assert "- arch: x86_64\n            runner: macos-15-intel" in workflow
    assert "arch: arm64" in workflow and "arch: x86_64" in workflow
    assert 'node-version: "22"' in workflow
    assert 'command -v node' in workflow
    assert "eugeneware/ffmpeg-static/releases/download/b6.1.1" in workflow
    assert "ffmpeg-darwin-arm64" in workflow
    assert "ffprobe-darwin-arm64" in workflow
    assert "ffmpeg-darwin-x64" in workflow
    assert "ffprobe-darwin-x64" in workflow
    for checksum in (
        "a90e3db6a3fd35f6074b013f948b1aa45b31c6375489d39e572bea3f18336584",
        "bb2db6f5d8cef919da12fbf592119a987202a8c060a886f3cab091f9cab90b64",
        "ebdddc936f61e14049a2d4b549a412b8a40deeff6540e58a9f2a2da9e6b18894",
        "fa3add0ce901f7241abe0dfc0155d958fc834aca3f8ce61f87cc712ae669c1e0",
    ):
        assert checksum in workflow
    assert "bash packaging/build_macos.sh" in workflow
    assert "macos-${{ matrix.arch }}.dmg.sha256" in workflow
    assert "needs: [windows-x64, linux-x86_64, macos]" in workflow
    assert "checksums.sha256" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "actions/download-artifact@v4" in workflow
    assert "gh release create" in workflow
    assert "github.token" in workflow
    assert workflow.count("uv run --locked python packaging/set_version.py --check") == 3
    assert "AppImage" not in workflow


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
    package_lock = json.loads(read("desktop-ui/package-lock.json"))
    tauri = json.loads(read("desktop-ui/src-tauri/tauri.conf.json"))
    cargo = read("desktop-ui/src-tauri/Cargo.toml")
    cargo_lock = read("desktop-ui/src-tauri/Cargo.lock")

    assert package["version"] == __version__
    assert package_lock["version"] == __version__
    assert package_lock["packages"][""]["version"] == __version__
    assert tauri["version"] == __version__
    assert f'name = "janeconverter-desktop"\nversion = "{__version__}"' in cargo
    assert f'name = "janeconverter-desktop"\nversion = "{__version__}"' in cargo_lock


def test_version_tool_check_mode_reports_aligned_metadata():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "packaging" / "set_version.py"), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"synchronized at {__version__}" in result.stdout
