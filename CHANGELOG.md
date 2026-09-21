# Changelog

All notable changes to JaneConverter are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [2.2.1] - 2026-09-22

### Added
- Added a controlled in-app update flow that lets users install an available update or dismiss it and decide later.
- Added the Preserve Quality conversion preset for outputs that should retain the source quality as closely as the target format allows.

### Changed
- Updated the Browser Capture access page with clearer, consumer-friendly instructions and confirmation wording.
- Refined the conversion controls and settings presentation for a simpler mass-consumer workflow.
- Published stable releases as the updater's discoverable GitHub latest release.

### Fixed
- Corrected conversion preset dropdown alignment and removed the unnecessary alternate theme switch.

## [2.0.0] - 2026-09-21

### Added
- Self-contained Windows x64 installer, Windows portable ZIP, and Linux x86_64 tarball.
- Bundled frozen conversion engine, FFmpeg, FFprobe, and Node.js runtime.
- Tagged release publishing with SHA-256 checksums through GitHub Actions.

### Changed
- Bumped the Python package, desktop app, and Browser Bridge to 2.0.0 for the consolidated product redesign.
- Made the Tauri application the only supported desktop interface.
- Moved packaged settings, temporary files, and converted media to OS user-data directories.
- Updated release checks for versioned installer filenames.
- Migrated the Python backend to the installable `src/janeconverter/` package, managed and locked by uv.
- Replaced source-script execution with the `janeconverter` console command across Tauri, CI, and release packaging.

### Removed
- Legacy Python and Rust desktop interfaces and the C# launcher.
- Source installer, launcher, uninstall, compatibility-build, and staged-update scripts.
- Root Python launch and requirements files superseded by project metadata and `uv.lock`.

## [1.2.0] - 2026-09-20

### Added
- Added the Main UI release surface built with Tauri 2, React, TypeScript, Tailwind CSS, Framer Motion, and Rust-native process/file-dialog bridging.
- Added a shared converted-library browser with root-safe navigation, Open folder, Move library, media thumbnails, cover-art previews, refresh, and safe delete actions.
- Added immediate Relaunch controls to the Main UI, Legacy Rust, and Legacy Python interfaces so the saved launcher preference can be applied without manual restarts.
- Added Apple Music catalog resolution for public song and album links, album track listing, matching-source search, and source troubleshooting guidance.
- Added stale-download protection and Unix frontend preference handling so older native binaries are not silently reused after installation.
- Added the optional local Browser Bridge extension, allowing all three launchers to use a confirmed source-scoped browser session without closing Vivaldi or another Chromium browser.

### Changed
- Made the universal launcher the single entry point for all three interfaces while preserving the legacy launchers as recovery paths.
- Kept converted-library data project-local and consistent across launchers, with the Main UI using the same configured output directory as the legacy interfaces.

### Fixed
- Windows setup now ignores the Microsoft Store Python execution alias and validates a working Python runtime before creating the private environment.
- Preserved per-track playlist credits files even when a provider has no description.
- Added bounded retries for transient playlist downloads and FFmpeg conversions, with fresh temporary directories for each download attempt.
- Added a Python 3.10+ guard to the macOS/Linux installer and clearer Apple Music no-match errors.
- Windows setup now builds the Rust frontend when Cargo is available and moves stale native binaries aside when it is not.
- Windows setup now uses non-interactive winget installs and visible pip progress, so setup should not require Enter to continue.
- Removed the setup wrapper's hidden PAUSE prompt; failed setup runs now preserve the error code and close automatically after a short message.
- Account access now tries a source-scoped, read-only in-memory Chromium session before yt-dlp's normal cookie-database path, so supported Chromium browsers can remain open during conversion.
- Account access now keeps the confirmed localhost handoff alive until the current session is cleared, so the Browser Bridge can connect after confirmation and pass the session to Python over stdin without creating a cookie file.
- Removed the rejected exported-cookie fallback; browser-session authentication never creates or stores a cookie file.

## [1.1.0] - 2026-09-11

### Fixed
- Bounded native output delivery and frame-by-frame event draining to prevent noisy yt-dlp/FFmpeg output from freezing the interface.
- Moved native converted-library scans off the UI thread.
- Abort and window-close now terminate the complete Python/FFmpeg process tree on Windows.
- Added in-app playlist track selection to the Rust frontend.
- Persisted native converter settings beside the application.
- Prevented the writable-directory probe from touching a user-created `.write-test` file.
- Added a restart handoff helper for staged updates and expanded uninstall cleanup for portable installs.

### Changed
- Updated the native launcher and CLI version to 1.1.0.
- Updated release packaging and documentation for the inline live console, playlist selection, supported formats, and restart-safe updates.

### Added
- Experimental macOS/Linux launch scripts, file-manager integration, and CI coverage.
- Native Rust/egui desktop frontend with a smoothly collapsible workspace sidebar, bounded console rendering, non-blocking conversion controls, library actions, and the temporary account-access handoff.
- Optional browser-session authentication for authorized account-only media. JaneConverter can use an existing Chrome, Edge, Firefox, Brave, or Vivaldi session through yt-dlp without requesting passwords or writing cookie files.
- Clear authentication failure guidance and CLI support via `--browser-session`.
- Temporary localhost account-access handoff in the GUI. Users can create a one-time link, sign in through the host's default browser, and enable the existing browser session for the current app session without storing credentials or cookies.
- Native Rust account-access URL validation and browser-session test coverage.
- Rust frontend unit tests for browser detection, HTML escaping, and account-access URL safety.
- Release-package validation that excludes Python bytecode, logs, caches, and runtime data.
- CI coverage for the Rust frontend and Windows release archive contents.
- Reversible interface preference with direct Rust and legacy Python launcher shortcuts.

### Changed
- Extractor update checks are read-only by default; installation now requires explicit permission and remains within the tested dependency range.
- Staged update archives reject traversal, drive-qualified paths, alternate data streams, encrypted entries, excessive file counts, and oversized uncompressed payloads.

## [1.0.0] - 2026-09-07

### Fixed
- **Launch crash**: `gui.py` failed to import (`Callable` used without being imported) on Python 3.13 and earlier.
- **Broken error dialogs**: exception variables captured in deferred lambdas were deleted before display (`NameError` on every conversion or playlist-fetch failure path).
- **Playlist selector**: checkboxes were keyed by a shared fallback index, so selecting one track could silently control another.
- **Single-track credits files**: Source URL and Platform lines were never written (metadata keys did not match the writer).
- **Orphaned partial files**: failed ffmpeg transcodes left truncated output files behind and retries saved under a different name; partials are now cleaned up before every retry and on final failure.
- **Linux VAAPI**: encoder arguments were missing the required render device and `format=nv12,hwupload` filter chain, so VAAPI never worked; webm was also excluded from the GPU-to-CPU fallback.
- **Silent Spotify failures**: unresolvable Spotify links now produce a clear, actionable error instead of feeding a Spotify URL to yt-dlp.
- **Filename sanitization**: Windows reserved device names (CON, NUL, COM1-9, LPT1-9) and control characters are now handled.
- **Video mode in the GUI** no longer parses the resolution menu as an audio bitrate.
- Playlist button styling is restored correctly after a failed catalog fetch.
- `-thread_queue_size` is now applied per input, and output thread scaling applies to the encoder.

### Changed
- **Update pipeline hardened**: yt-dlp upgrades are pinned to the exact PyPI version; the repository self-patch now requires explicit user consent on the "Check for Updates" button, uses `--ff-only` pulls against the configured upstream branch, and honestly reports pip/compiler failures instead of logging unconditional success.
- Engine update checks run once per application start / CLI invocation instead of before every conversion (`--no-update` now actually exists in the CLI).
- Worker threads no longer swap the global `sys.stdout`/`sys.stderr` — a single process-wide console redirector feeds the UI log.
- All worker-to-UI communication goes through a thread-safe UI queue instead of calling Tkinter from worker threads.
- Hardware telemetry runs in a single persistent loop (no thread respawn every 1.5 s; CPU readings no longer flicker 0%).
- Real transcode progress via `ffmpeg -progress pipe:1` (was a hardcoded 0.8→1.0 jump).
- Playlist track lists render progressively, so very large playlists no longer freeze the selection window.
- Conversion success is reported in the status bar with elapsed time instead of a blocking dialog.
- Closing the window during an active conversion asks before aborting; stale temp jobs (older than 24 h) are cleaned up instead of wiping a concurrently running instance's work.
- Disk-space checks before processing; playlist batches abort early after 5 consecutive failures (network-dead detection).
- CLI validates `--format/--bitrate/--sample-rate/--resolution` with clear errors, refuses `--playlist` on local files, and exits non-zero when tracks fail.
- Dependencies carry upper bounds (`<next-major`) to keep fresh installs working; `requirements-dev.txt` added.

### Added
- `--version` CLI flag and `engine/version.py` version singleton (v1.0.0).
- GitHub Actions CI (Windows + Ubuntu, Python 3.10/3.12, pyflakes lint, hermetic tests, opt-in online tests).
- Hermetic test suite (58 tests, no network required) with an opt-in `@pytest.mark.online` marker for the 8 live-network tests.
- Legal & platform notice in the README.

### Removed
- Compiled `JaneConverter.exe` from version control (rebuilt locally by `install.ps1`).
- Undocumented `--no-nvenc` CLI alias (superseded by `--no-gpu`).
- Dead code: unused `_play_latest_file` handler and unused imports.
