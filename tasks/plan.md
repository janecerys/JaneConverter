# Implementation Plan: JaneConverter dual distribution

## Overview

Add a consumer-facing Windows installer that contains JaneConverter's private
runtime while preserving the existing source/portable distribution as the
developer and recovery safety net.

## Architecture decisions

- Keep `build_release.ps1` as the portable/developer package path. It remains
  source-visible and keeps the legacy launchers and diagnostics available.
- Build the consumer runtime as frozen Python executables so consumers do not
  need a system Python installation or a separate `pip` environment.
- Bundle FFmpeg beside the frozen conversion engine and resolve it before the
  system PATH.
- Use the existing Tauri/Rust application as the consumer desktop shell and
  produce a Windows NSIS installer from it.
- Keep browser-extension installation consent-based; browser security does not
  allow a normal installer to silently install an extension into Vivaldi,
  Chrome, or another Chromium browser.
- Keep user media and mutable settings outside the installer payload when the
  install location is protected; preserve the existing movable library path.

## Task list

### Phase 1: Packaging contract

- [x] Define a shared runtime layout for portable and consumer builds.
- [x] Add tests covering the consumer bundle manifest and developer fallback.

### Phase 2: Self-contained runtime

- [x] Build frozen conversion-engine and Legacy Python binaries.
- [x] Teach the universal launcher and native frontends to prefer packaged
  runtime binaries while retaining source/venv fallback behavior.
- [x] Bundle and resolve local FFmpeg/ffprobe binaries.

### Checkpoint: Runtime

- [x] Python tests pass.
- [x] Rust builds pass as part of both package builds.
- [x] A clean staged runtime can perform `--help` and a version smoke test.

### Phase 3: Consumer installer

- [x] Configure Tauri resources and Windows NSIS packaging.
- [x] Add a consumer build script that stages the runtime and produces one
  `JaneConverter-Setup.exe` artifact.
- [x] Keep a separate portable ZIP artifact for developers and recovery.

### Checkpoint: Distribution

- [x] Consumer installer builds successfully.
- [x] Consumer bundle contains no dependency on system Python, pip, Rust, or npm at launch.
- [x] Legacy Rust and Legacy Python remain selectable recovery paths.

### Phase 4: Documentation and release safety

- [x] Document the two distribution paths and rollback procedure.
- [x] Verify checksums, package contents, and clean-worktree impact.

## Follow-up: Product hardening and consumer readiness

The dual-distribution work is complete. The next improvement pass focuses on
making the Main UI the dependable consumer path while preserving the legacy
interfaces as recovery tools.

### Phase 5: Safe browser access and session lifecycle

- [x] Narrow browser-extension permissions to the explicitly connected source.
- [x] Harden the localhost bridge with origin checks and one-time handoff
  consumption without breaking the Vivaldi workflow.
- [x] Add regression coverage for bridge expiry, reuse, malformed payloads,
  and cookie cleanup after a completed conversion.

### Phase 6: Consumer reliability and performance

- [ ] Add a persistent job record and user-visible retry/resume state for
  interrupted playlist work.
- [ ] Measure and improve startup, library scanning, and large-playlist
  responsiveness.
- [ ] Keep the Main UI package minimal while retaining legacy launchers in a
  clearly documented recovery distribution.

### Phase 7: Release confidence

- [x] Add Python and Rust dependency advisory checks to CI.
- [x] Enforce Rust formatting and frontend production-build checks.
- [ ] Add a clean-machine Windows acceptance checklist for install, launch,
  browser bridge, library relocation, relaunch, and uninstall.

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Frozen Python GUI misses Tcl/Tk or package assets | High | Build and launch-test the Legacy Python binary before packaging |
| Tauri resource paths differ after installation | High | Test resource resolution from a staged install layout |
| FFmpeg redistribution or licensing mismatch | High | Pin the build, include its notices, and keep the developer path available |
| Browser extension cannot be installed silently | Medium | Ask for consent and provide the manual Load unpacked path |
| Consumer package diverges from the portable path | Medium | Build both from the same staged runtime manifest |

## Rollback

The existing `build_release.ps1`, `setup.bat`, `install.ps1`, root launchers,
and source tree remain untouched as the nerd/recovery path. If the consumer
installer fails validation, do not replace those artifacts; use the portable
ZIP until the installer build is corrected.
