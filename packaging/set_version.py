#!/usr/bin/env python3
"""Synchronize JaneConverter application version metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SEMVER_RE = re.compile(
    r"""
    (?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)
    (?:-(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)
        (?:\.(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*)?
    (?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?
    \Z
    """,
    re.VERBOSE,
)
PROJECT_NAME = "janeconverter-desktop"


class VersionError(Exception):
    """Raised when version metadata cannot be updated safely."""


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def validate_version(version: str) -> None:
    if not SEMVER_RE.fullmatch(version):
        raise VersionError(
            f"{version!r} is not a valid SemVer version accepted by npm, Cargo, and Tauri"
        )


def replace_once(text: str, pattern: str, version: str, label: str) -> str:
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1:
        raise VersionError(f"{label}: expected exactly one version field, found {len(matches)}")
    match = matches[0]
    start, end = match.span("value")
    return text[:start] + version + text[end:]


def canonical_version(path: Path, text: str, target: str | None) -> tuple[str, str]:
    pattern = r'(?m)^__version__[ \t]*=[ \t]*"(?P<value>[^"\r\n]+)"[ \t]*$'
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1:
        raise VersionError(
            f"{relative(path)}: expected exactly one __version__ assignment, found {len(matches)}"
        )
    current = matches[0].group("value")
    return current, text if target is None else replace_once(text, pattern, target, relative(path))


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise VersionError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def load_json(path: Path, text: str) -> dict[str, object]:
    try:
        data = json.loads(text, object_pairs_hook=reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise VersionError(f"{relative(path)}: invalid JSON: {exc}") from exc
    except VersionError as exc:
        raise VersionError(f"{relative(path)}: {exc}") from exc
    if not isinstance(data, dict):
        raise VersionError(f"{relative(path)}: expected a JSON object")
    return data


def require_string(data: dict[str, object], key: str, label: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise VersionError(f"{label}: expected string key {key!r}")
    return value


def json_root_version(
    path: Path, text: str, target: str, *, expected_name: str | None = None
) -> tuple[str, str]:
    label = relative(path)
    data = load_json(path, text)
    if expected_name is not None and data.get("name") != expected_name:
        raise VersionError(f"{label}: expected name {expected_name!r}")
    current = require_string(data, "version", label)
    pattern = (
        r'(?m)^  "version"[ \t]*:[ \t]*"(?P<value>'
        + re.escape(current)
        + r')"[,]?[ \t]*$'
    )
    return current, replace_once(text, pattern, target, label)


def package_lock_versions(path: Path, text: str, target: str) -> tuple[list[tuple[str, str]], str]:
    label = relative(path)
    data = load_json(path, text)
    if data.get("name") != PROJECT_NAME:
        raise VersionError(f"{label}: expected root package name {PROJECT_NAME!r}")
    root_version = require_string(data, "version", f"{label} (root)")
    packages = data.get("packages")
    if not isinstance(packages, dict):
        raise VersionError(f"{label}: expected object key 'packages'")
    root_package = packages.get("")
    if not isinstance(root_package, dict) or root_package.get("name") != PROJECT_NAME:
        raise VersionError(f"{label}: expected packages[''] for {PROJECT_NAME!r}")
    package_version = require_string(root_package, "version", f'{label} (packages[""])')

    root_pattern = (
        r'(?m)^  "version"[ \t]*:[ \t]*"(?P<value>'
        + re.escape(root_version)
        + r')"[,]?[ \t]*$'
    )
    updated = replace_once(text, root_pattern, target, f"{label} (root)")
    package_pattern = (
        r'(?m)^  "packages"[ \t]*:[ \t]*\{[ \t]*\r?\n'
        r'    ""[ \t]*:[ \t]*\{[ \t]*\r?\n'
        r'      "name"[ \t]*:[ \t]*"janeconverter-desktop"[,]?[ \t]*\r?\n'
        r'      "version"[ \t]*:[ \t]*"(?P<value>'
        + re.escape(package_version)
        + r')"[,]?[ \t]*$'
    )
    updated = replace_once(updated, package_pattern, target, f'{label} (packages[""])')
    return [(f"{label} (root)", root_version), (f'{label} (packages[""])', package_version)], updated


def cargo_toml_version(path: Path, text: str, target: str) -> tuple[str, str]:
    label = relative(path)
    sections = list(re.finditer(r"(?ms)^\[package\][ \t]*\r?\n.*?(?=^\[|\Z)", text))
    if len(sections) != 1:
        raise VersionError(f"{label}: expected exactly one [package] section, found {len(sections)}")
    section = sections[0].group(0)
    if len(re.findall(rf'(?m)^name[ \t]*=[ \t]*"{PROJECT_NAME}"[ \t]*$', section)) != 1:
        raise VersionError(f"{label}: [package] does not uniquely name {PROJECT_NAME!r}")
    versions = list(re.finditer(r'(?m)^version[ \t]*=[ \t]*"(?P<value>[^"\r\n]+)"[ \t]*$', section))
    if len(versions) != 1:
        raise VersionError(f"{label}: expected one [package] version, found {len(versions)}")
    current = versions[0].group("value")
    updated_section = replace_once(
        section,
        r'(?m)^version[ \t]*=[ \t]*"(?P<value>' + re.escape(current) + r')"[ \t]*$',
        target,
        label,
    )
    return current, text[: sections[0].start()] + updated_section + text[sections[0].end() :]


def cargo_lock_version(path: Path, text: str, target: str) -> tuple[str, str]:
    label = relative(path)
    blocks = list(re.finditer(r"(?ms)^\[\[package\]\][ \t]*\r?\n.*?(?=^\[\[package\]\]|\Z)", text))
    named = [
        block
        for block in blocks
        if re.search(rf'(?m)^name[ \t]*=[ \t]*"{PROJECT_NAME}"[ \t]*$', block.group(0))
    ]
    if len(named) != 1:
        raise VersionError(f"{label}: expected one {PROJECT_NAME!r} package entry, found {len(named)}")
    block = named[0]
    versions = list(re.finditer(r'(?m)^version[ \t]*=[ \t]*"(?P<value>[^"\r\n]+)"[ \t]*$', block.group(0)))
    if len(versions) != 1:
        raise VersionError(f"{label}: expected one version in {PROJECT_NAME!r} entry")
    current = versions[0].group("value")
    updated_block = replace_once(
        block.group(0),
        r'(?m)^version[ \t]*=[ \t]*"(?P<value>' + re.escape(current) + r')"[ \t]*$',
        target,
        label,
    )
    return current, text[: block.start()] + updated_block + text[block.end() :]


def synchronize(requested: str | None, check: bool) -> int:
    canonical_path = REPO_ROOT / "src/janeconverter/version.py"
    canonical_text = canonical_path.read_text(encoding="utf-8")
    current, _ = canonical_version(canonical_path, canonical_text, None)
    target = requested or current
    validate_version(target)

    updates: dict[Path, str] = {}
    observed: list[tuple[str, str]] = []
    if requested is not None:
        _, updates[canonical_path] = canonical_version(canonical_path, canonical_text, target)

    package_path = REPO_ROOT / "desktop-ui/package.json"
    package_text = package_path.read_text(encoding="utf-8")
    version, updates[package_path] = json_root_version(
        package_path, package_text, target, expected_name=PROJECT_NAME
    )
    observed.append((relative(package_path), version))

    lock_path = REPO_ROOT / "desktop-ui/package-lock.json"
    lock_text = lock_path.read_text(encoding="utf-8")
    lock_versions, updates[lock_path] = package_lock_versions(lock_path, lock_text, target)
    observed.extend(lock_versions)

    tauri_path = REPO_ROOT / "desktop-ui/src-tauri/tauri.conf.json"
    tauri_text = tauri_path.read_text(encoding="utf-8")
    version, updates[tauri_path] = json_root_version(tauri_path, tauri_text, target)
    observed.append((relative(tauri_path), version))

    cargo_path = REPO_ROOT / "desktop-ui/src-tauri/Cargo.toml"
    cargo_text = cargo_path.read_text(encoding="utf-8")
    version, updates[cargo_path] = cargo_toml_version(cargo_path, cargo_text, target)
    observed.append((relative(cargo_path), version))

    cargo_lock_path = REPO_ROOT / "desktop-ui/src-tauri/Cargo.lock"
    cargo_lock_text = cargo_lock_path.read_text(encoding="utf-8")
    version, updates[cargo_lock_path] = cargo_lock_version(cargo_lock_path, cargo_lock_text, target)
    observed.append((f"{relative(cargo_lock_path)} ({PROJECT_NAME})", version))

    stale = [(label, version) for label, version in observed if version != target]
    if check:
        if stale:
            print(f"application version metadata differs from canonical version {target}:", file=sys.stderr)
            for label, version in stale:
                print(f"  {label}: {version}", file=sys.stderr)
            return 1
        print(f"all application versions are synchronized at {target}")
        return 0

    changed = 0
    for path, updated in updates.items():
        original = canonical_text if path == canonical_path else path.read_text(encoding="utf-8")
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed += 1
    print(f"synchronized application version {target} ({changed} file(s) changed)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Set or synchronize JaneConverter application version metadata."
    )
    parser.add_argument("version", nargs="?", help="new SemVer application version")
    parser.add_argument("--check", action="store_true", help="report stale metadata without writing")
    args = parser.parse_args()
    if args.check and args.version is not None:
        parser.error("VERSION cannot be used with --check")
    try:
        return synchronize(args.version, args.check)
    except (OSError, VersionError) as exc:
        print(f"version synchronization failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
