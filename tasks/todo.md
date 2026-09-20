# JaneConverter dual distribution checklist

- [x] Define the shared runtime layout and consumer bundle manifest.
- [x] Add packaging contract tests.
- [x] Build frozen conversion and Legacy Python executables.
- [x] Add packaged-runtime fallback resolution to the launchers.
- [x] Configure Tauri resources and NSIS output.
- [x] Build and verify `JaneConverter-Setup.exe`.
- [x] Verify the existing portable/developer release remains available.
- [x] Update README and release notes with both paths.
- [x] Run the full verification suite.

## Product hardening follow-up

- [x] Narrow browser-extension permissions and harden the local bridge.
- [x] Add browser bridge lifecycle regression tests.
- [ ] Add persistent conversion-job state and resumable retry UX.
- [ ] Measure startup, library scan, and large-playlist performance.
- [x] Add Python/Rust dependency advisory checks to CI.
- [x] Enforce Rust formatting and production build checks.
- [ ] Validate the complete consumer flow on a clean Windows machine.
