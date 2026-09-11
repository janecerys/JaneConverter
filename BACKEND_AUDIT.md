# JaneConverter Backend & Release Audit

**Audit date:** 2026-09-11
**Repository:** JaneConverter  
**Review scope:** GUI/backend boundary, extraction, conversion, updates, filesystem behavior, packaging, tests, documentation, and consumer readiness.

## Executive verdict

JaneConverter has a capable conversion core and a good first release foundation, but it is **not release-ready for broad consumer distribution yet**. It is suitable for an alpha/beta audience that can install Python, FFmpeg, and Node.js and tolerate occasional platform breakage.

## Current implementation status — 2026-09-11

The native Rust frontend, private Python environment, local-data default, bounded UI work, playlist organization, diagnostics, staged updates, and Windows ZIP/checksum workflow are now present in the working tree. The current engineering grade is **B- / 7.0** for a controlled beta. Official consumer release remains blocked by clean-machine installation and GUI acceptance testing, real long-running conversion/abort validation, signed artifacts, FFmpeg redistribution decisions, and final dependency/documentation review.

Issue narratives below retain historical evidence from the original audit. Findings that describe the old Tk-only interface, global dependency installation, or immediate process exit should be read as baseline findings and are not claims about the current native frontend.

## Remediation update

The current working tree implements the first release-hardening pass from this audit: progress and UI callbacks are coalesced and bounded, console rendering is batched and capped, library discovery runs off the Tk thread, shutdown no longer uses a hard process exit, source/category output routing is centralized, metadata has collision-safe folders and manifests, default runtime data is user-writable, setup uses a private `.venv`, source hostname matching is strict, and update checks no longer install or patch automatically. The next pass adds bounded/paginated playlist rendering, validated restart-time update staging, diagnostics, an uninstall script, and a reproducible Windows ZIP/checksum workflow. The remaining release gates are clean-machine validation, Windows GUI smoke coverage, and optional code signing.

The reported extreme lag has a credible, code-level explanation:

```text
yt-dlp / FFmpeg progress events
        ↓
many worker-to-UI queue entries
        ↓
Tk UI pump drains the queue without a time/item limit
        ↓
progress label updates + textbox insert/scroll for every message
        ↓
event-loop starvation and visible lag
```

The highest-value fix is to coalesce progress updates and batch console output before touching further visual polish.

## Scorecard

| Area | Grade | Assessment |
|---|---:|---|
| Conversion engine design | B- / 7.0 | Clear extraction/conversion split, solid FFmpeg argument construction, useful fallback behavior. |
| Performance | B- / 6.8 | Native UI work and bounded queues reduce the original lag risk; stress validation remains. |
| Correctness | B / 7.2 | Core paths, routing, metadata isolation, and Unicode handling are substantially hardened. |
| Reliability | B- / 6.7 | Abort, cleanup, diagnostics, and staged updates exist; long-run validation remains. |
| Security / supply chain | C+ / 6.0 | Temporary local access is constrained, but dependencies and unsigned updates remain trust risks. |
| Consumer friendliness | C+ / 6.2 | Portable defaults and a native launcher help; external prerequisites still add friction. |
| Packaging / distribution | C+ / 6.0 | Reproducible ZIP/checksum workflow exists; signing and clean-machine proof remain. |
| Tests / CI | B- / 7.0 | Python suite is strong; native tests and GUI acceptance coverage are still growing. |
| Documentation accuracy | C+ / 6.0 | README is largely current; historical audit and release claims still need reconciliation. |
| Overall release readiness | **C+ / 6.2** | Strong beta/release-candidate foundation, not an official consumer release yet. |

## Strengths

### Conversion pipeline

- `run_converter.py` provides a coherent orchestration layer between extraction and FFmpeg conversion.
- `engine/converter.py` builds argument lists instead of concatenated shell strings, reducing quoting and injection risk.
- FFmpeg output cleanup is attempted on abort, failure, and retry.
- GPU detection is cached and supports NVENC, AMF, QSV, VideoToolbox, VAAPI, and CPU fallback.
- Hardware encoder failure can retry through a CPU path instead of immediately failing the job.
- Local-file conversion is supported without requiring network access.
- Filename sanitization handles Windows-invalid characters, control characters, trailing spaces/dots, and reserved device names.
- Disk-space checks, stale temporary-job cleanup, consecutive playlist-failure protection, and explicit abort events show good operational awareness.

### User-facing behavior

- Worker threads are used for network and FFmpeg work, so the main operation is not intentionally run inside the Tk callback.
- Playlist rows render progressively rather than constructing every row in one callback.
- The app has a clear conversion/library/console separation and a sidebar navigation model.
- The library now supports nested output folders and asks for confirmation before deletion.
- Cover art is embedded when the target container supports attached pictures, while standalone metadata can be kept separately.

### Engineering process

- The repository has a real test suite, offline-by-default pytest configuration, and GitHub Actions coverage across Windows and Ubuntu.
- Tests cover FFmpeg command construction, metadata writing, Spotify parsing, playlist extraction, sanitization, and immediate abort behavior.
- The existing `POLISHING_PLAN.md` correctly identifies several structural debts, especially GUI decomposition, settings persistence, updater testing, and release artifacts.

## Critical findings

### P0 — UI event storms can starve the application

**Evidence:** `gui.py` `_post_ui()` enqueues every callback; `_start_ui_pump()` drains the queue in an unlimited `while` loop. `engine/extractor.py` reports yt-dlp download progress without throttling. `run_converter.py` prints from every progress report. `gui.py` also inserts and scrolls the console textbox for every queued log fragment.

**Impact:** A busy download or transcode can create thousands of callbacks and textbox operations. The UI spends its time processing stale progress instead of handling input, producing the extreme lag reported by the user. A backlog can also make completion/abort messages wait behind obsolete updates.

**Fix before release:**

1. Throttle extraction progress to a maximum rate, such as 5–10 updates per second.
2. Coalesce progress by job: keep only the latest `(fraction, message)` value.
3. Drain at most a bounded number of UI tasks or a bounded time slice per `after()` tick.
4. Batch console text into one insert every 100–250 ms and cap retained log size, for example 5–10 MB.
5. Do not echo every progress update through both `print()` and the UI queue.

### P1 — Library refresh performs unbounded filesystem work on the UI thread

**Evidence:** `gui.py` `_refresh_library()` performs two recursive `os.walk()` passes, repeated path containment checks, stat calls, and row creation directly from the Tk thread.

**Impact:** A large converted library, network destination, slow disk, or antivirus scan can freeze the window after conversion or when opening the library. The UI has no cancellation or loading state for this work.

**Fix:** Move discovery/stat aggregation to a worker thread, return a snapshot to the UI queue, and render rows in batches. Cache the snapshot and refresh only when the destination changes or a conversion/deletion completes.

### P1 — Large playlists still create too many Tk widgets

**Evidence:** `PlaylistSelectionWindow` progressively creates one frame, checkbox, and several labels per entry. Batch rendering reduces the initial stall but still eventually creates the full widget set.

**Impact:** Large playlists remain memory-heavy and eventually block scrolling/filtering. Filtering loops over every row and repacks widgets on each key event.

**Fix:** Use a virtualized list or a fixed pool of visible rows; debounce search input; keep selection state in data structures rather than one widget tree per item.

### P1 — Global stdout/stderr redirection is a fragile logging architecture

**Evidence:** `StdoutRedirector` replaces process-global `sys.stdout` and `sys.stderr`, and every write is pushed into an unbounded queue. Third-party libraries can write arbitrary fragments, including progress-like output.

**Impact:** The UI log becomes coupled to all library output and can amplify the event-storm problem. It also makes embedding the engine, running multiple app instances, or testing output more difficult.

**Fix:** Use Python `logging` with a bounded queue handler. Emit structured progress separately from human-readable logs. Keep console history bounded and preserve full logs to an optional file only when requested.

## High-priority correctness and reliability findings

### P1 — Category selection currently suppresses source separation

`media_library_folder()` returns `Music` or `Videos` immediately when an explicit category is supplied. The GUI always supplies a category, so Spotify, YouTube, and SoundCloud exports are placed together instead of beneath source folders. This conflicts with the intended organization described in the earlier UI work.

Recommended behavior:

```text
Music/<Source>/media.ext
Videos/<Source>/media.ext
Miscellaneous/Audio/media.ext
Miscellaneous/Videos/media.ext
```

### P1 — Single-item metadata can collide

Single conversions write cover art and info files under one category-level `metadata` folder. Two sources with the same sanitized title can overwrite each other’s metadata even though the media output uses a unique target path.

Use a per-item metadata directory, a source directory, or the same collision-safe naming scheme for metadata assets.

### P1 — Shutdown is not graceful enough

`_on_close()` sets the abort event but then calls `os._exit(0)` immediately. It does not wait for the FFmpeg process, downloader, worker threads, or pending cleanup to finish.

This can leave child processes, temporary files, partial outputs, or locked files. Replace hard exit with a shutdown state, wait for the active worker/process for a bounded period, then close the window. Use a stop event for telemetry and updater threads.

### P1 — Automatic updates modify the live installation

The startup updater can install a newer `yt-dlp` package in the running Python environment. The manual updater can pull application code, install dependencies, and recompile the launcher. This is a substantial trust and recovery surface for a consumer app.

Risks include partial updates, environment permission failures, dependency incompatibility, repository divergence, and code changing on disk while the old process is still running. Make update checks read-only by default, require explicit install consent, stage updates, verify them, and apply them on restart. Prefer signed release artifacts over `git pull` for consumers.

### P1 — Install path is not isolated

`install.ps1` installs Python packages globally, while `Program.cs` only checks a few hard-coded Python locations before falling back to `pythonw.exe` from PATH. A protected install directory or another Python installation can cause permission conflicts or import mismatches.

Create and use a local `.venv`, install pinned dependencies there, and make the launcher resolve that interpreter. The portable default now keeps application data beside JaneConverter to avoid unnecessary C: drive usage, with a writable per-user fallback for protected installations. Existing AppData data is merged without overwriting conflicts.

## Medium-priority findings

### P2 — Source detection relies on substring matching

`identify_source_type()` and `is_playlist_url()` use checks such as `"spotify.com" in url_lower`. A hostname like `not-spotify.com` can be classified as Spotify. Parse the URL hostname and compare exact domains or safe subdomains.

### P2 — Spotify parsing is brittle and mostly silent

The implementation scrapes private-ish page payload structure with regular expressions and catches many failures with `pass`. A page-shape change can silently degrade metadata quality. Add schema validation, a dedicated parse error, clear user messaging, and a test for malformed/partial payloads.

### P2 — Error handling hides operational failures

There are many broad `except Exception: pass` blocks in extraction, metadata, UI, cleanup, and update paths. This keeps the app alive but makes failures invisible and hard to diagnose. Log a concise context-rich warning and expose actionable guidance to the user.

### P2 — No job queue or resume model

Only one conversion is supported in the GUI. A playlist failure produces a summary but there is no retry-failed-tracks workflow, persisted job manifest, resume point, or clean recovery after app restart.

### P2 — Output behavior is not fully centralized

The GUI and CLI share pipeline functions, but category selection exists only in the GUI. The output policy should be a tested domain object used by both interfaces, rather than optional strings interpreted in multiple places.

### P2 — Fixed free-space threshold is blunt

The pipeline requires 1 GB free regardless of input/output size. This can reject a small conversion on a nearly full disk and still cannot guarantee space for a large video. Estimate required temporary/output space where possible and report the reason clearly.

## Consumer-readiness review

### What is consumer-friendly today

- One-click setup attempts to find/install Python, FFmpeg, and Node.js.
- The launcher gives a graphical entry point and hides the console window.
- The app supports common audio/video formats and has GPU fallback.
- Abort, deletion confirmation, and organized library output are good safety/usability decisions.
- The legal notice explains that users are responsible for platform terms and copyright compliance.

### What will frustrate consumers

- Python, FFmpeg, and optionally Node.js are still external prerequisites.
- Global pip installation can fail due to permissions or conflict with existing Python projects.
- The app depends on network services and platform behavior that can change without notice.
- Raw exception text and silent failures make recovery unclear.
- No settings persistence means users repeatedly reselect common options.
- No signed installer or release artifact means SmartScreen and trust concerns remain.
- The README describes behavior that no longer matches the current UI and CLI.

## Documentation drift

The README should be corrected before a public release:

- It says the library has a **Play** action, but the current UI uses a folder/location action.
- It says metadata/cover placement differs from the current single-item and playlist implementation.
- It documents `--no-art`, but the parser exposes `--no-cover-art`.
- It documents `--output-dir`, but the parser exposes `--output` / `-o`.
- It says the update button is in the top header, but it is now in the sidebar.
- It claims duration and creation timestamp display, while the library implementation currently displays file size, format, and location.
- The playlist tree still shows `cover.jpg` in the playlist root even though current code stores it under `metadata`.
- The repository describes itself as open-source in some project context, but the README says “All rights reserved” and prohibits copying, modification, redistribution, and commercial use. That is not an OSI-style open-source license. Choose one clear distribution position and include a license file/terms that match it.

## Test and CI assessment

### Good coverage

- Hermetic tests cover core FFmpeg arguments, sanitization, metadata helpers, Spotify payload parsing, playlist extraction, and abort signals.
- CI runs Windows and Ubuntu across Python 3.10 and 3.12.
- Online tests are separated from the default suite.
- `pyflakes` is part of CI.

### Gaps

- No real GUI smoke test instantiates the app and exercises sidebar, library refresh, long-title rows, or playlist rendering.
- No test asserts that progress callbacks are throttled/coalesced or that the UI queue remains bounded.
- No updater tests cover failed pull, divergence, pip failure, compiler failure, timeout, or non-Git consumer installs.
- No tests cover output category paths, metadata collision handling, or exact library folder discovery.
- End-to-end conversion coverage is environment-sensitive because it requires FFmpeg and writes through the repository temp directory.

During this audit, the focused UI/hermetic set passed **28 tests**. The full local suite reported **56 passed and 2 failed**: one updater test could not recognize the moved repository as a Git worktree without the local safe-directory configuration, and the playlist integration test hit a permissions issue creating a repository `temp` directory. These failures should be made deterministic in CI and meaningful for real consumers.

## Recommended remediation order

### Release blocker sprint

1. Coalesce/throttle progress events and batch/cap console logs.
2. Move library discovery off the UI thread.
3. Add a real GUI smoke test for long titles, 100+ playlist entries, navigation, and sidebar collapse.
4. Correct category/source output policy and metadata collision behavior.
5. Make shutdown wait for active work and stop background loops.

### Consumer hardening

1. Use a local virtual environment and writable per-user data paths.
2. Replace raw self-patching with staged, explicit, release-based updates.
3. Add friendly error categories and preserve technical details in logs.
4. Persist settings and last destination.
5. Make README, CLI help, license, and release behavior agree.

### Structural refactor

Break the 2,152-line `gui.py` into focused modules: app shell, widgets/theme, telemetry, library, playlist window, settings, logging, and job orchestration. Keep `run_converter.py` as a service layer and make it independent of Tkinter.

## Release gate

I would not label the current tree a polished consumer release until all of the following are true:

- A 10-minute download/transcode does not make the UI visibly lag or delay abort.
- Progress/log queues are bounded and tests prove it.
- Full CI is green on a clean checkout without repository-specific permissions.
- GUI smoke tests cover the actual interactive surfaces.
- A clean non-Git installation can run without updater errors.
- Updates are staged, explicit, recoverable, and preferably artifact-based.
- Application data and dependencies are isolated from the source directory.
- README/CLI/license claims match the implementation.
- A release artifact is built and tested on Windows.

## Bottom line

JaneConverter’s core idea is strong and the existing engine work is better than a prototype: it has real format handling, metadata, GPU fallback, abort cleanup, and meaningful tests. The biggest weakness is that the UI architecture treats high-frequency progress and logs as ordinary one-by-one UI events. Fixing that backpressure problem should be the next engineering priority. After performance and packaging hardening, the project can become a credible consumer beta; it is not yet ready to promise a smooth, low-maintenance release to general users.
