# JaneConverter Consumer Release-Readiness Roadmap

**Baseline:** v1.0.0 plus current working-tree changes  
**Created:** 2026-09-09  
**Companion review:** [BACKEND_AUDIT.md](BACKEND_AUDIT.md)

## Mission

Make JaneConverter predictable, installable, recoverable, and pleasant for a normal consumer who should not need to understand Python, Git, FFmpeg internals, or threading.

Release-ready means a clean-machine user can install the application, convert common local and online media without freezing the interface, recover from normal failures, find output files, update safely, and get useful support information.

## Current decision

**Not ready for an official consumer release.**

The implementation passes are now present in the working tree. They materially reduce the original lag risk, add the native Rust frontend, bound large playlist rendering, add restart-time update staging, provide diagnostics/uninstall tooling, harden account access, and produce a Windows ZIP/checksum artifact. Clean-machine installation, full GUI acceptance, long-running conversion/abort validation, signing, and final legal/dependency review still require release-candidate validation.

The conversion core is a strong beta foundation. The remaining work is release validation and trust hardening rather than another broad UI rewrite.

## Priorities

| Priority | Meaning | Release treatment |
|---|---|---|
| P0 | Blocks normal use or risks data/process loss | Must fix before release candidate |
| P1 | High-probability consumer failure or serious trust issue | Must fix before official release |
| P2 | Important quality, maintenance, or support issue | Fix or explicitly risk-accept |
| P3 | Valuable enhancement after the foundation is stable | Post-release backlog |

## Phase 0 — Baseline and scope control

### 0.1 Establish the canonical source

- Use one canonical repository location and remove stale developer checkouts.
- Define Windows 10/11 x64 as the first-class release target.
- Keep generated folders out of release validation: `converted/`, `temp/`, `__pycache__/`, and `.pytest_cache/`.
- Decide whether the project is open source or source-available/proprietary.
- Add a license file that matches the actual permissions described by the README and repository.

**Acceptance:** A clean clone builds and tests without machine-specific paths, stale artifacts, or ownership configuration.

### 0.2 Capture performance baselines

Measure on a representative Windows machine:

- input latency during download and FFmpeg conversion;
- input latency during heavy console output;
- abort latency;
- library load time with 10, 100, and 1,000 files;
- playlist open/search time with 30, 100, and 1,000 entries;
- peak UI-queue depth and retained log size;
- memory growth during a long conversion.

**Acceptance:** Baseline measurements and regression thresholds are recorded before optimization.

## Phase 1 — Remove lag and event-loop starvation

### 1.1 Separate progress events from log events — P0

Create a small event model:

- `ProgressEvent(job_id, fraction, message)`: latest value wins;
- `LogEvent(level, message)`: batch and cap;
- `JobStateEvent(state, error, result)`: never drop terminal events.

Do not use `print()` as the worker-to-Tk transport.

### 1.2 Coalesce and throttle progress — P0

- Limit extraction/download progress to roughly 5–10 updates per second.
- Keep one latest progress value per active job.
- Preserve completed, failed, and aborted events even when intermediate progress is dropped.
- Clamp progress to `[0, 1]`.
- Do not send the same progress through both stdout and the UI queue.

**Acceptance:** A synthetic producer can emit 100,000 progress events without unbounded memory growth or UI starvation.

### 1.3 Bound the UI pump — P0

- Process a bounded number of UI tasks or a bounded time slice per Tk `after()` callback.
- Schedule the next callback before processing a long batch.
- Discard stale progress when a newer update for the same job exists.
- Never drain an unbounded queue in one UI callback.
- Keep terminal state events ahead of stale progress.

### 1.4 Batch and cap console output — P0

- Insert accumulated text once every 100–250 ms.
- Scroll once per batch, not once per fragment.
- Cap visible history to a configurable size such as 5–10 MB.
- Use a rotating log file if complete diagnostics are needed.
- Replace global stdout/stderr replacement with Python `logging` and a bounded queue handler.

**Acceptance:** The Console tab remains responsive during a long download and transcode.

### 1.5 Move library discovery off the UI thread — P1

- Run recursive file discovery/stat calls in a worker.
- Return a library snapshot to the UI.
- Render rows in batches.
- Show a refreshing state and supersede stale refresh jobs.
- Avoid repeated full-tree walks and repeated path-containment scans.

### 1.6 Bound large playlist lists — P1

- Use a bounded first page and explicit pagination instead of one Tk widget tree per entry.
- Debounce search by approximately 150–250 ms.
- Store selection in data, not thousands of Tk variables.
- Add a clear maximum or paging behavior for unsupported playlist sizes.

The current implementation renders 80 rows initially, keeps selection state separately, debounces filtering, and lets users load additional pages on demand. A fixed-row virtualized pool remains a future optimization if playlist sizes make pagination insufficient.

## Phase 2 — Job lifecycle, output correctness, and recovery

### 2.1 Introduce a job controller — P1

Create a backend controller independent of Tkinter that owns:

- job identity and state transitions;
- cancellation;
- subprocess handles;
- progress throttling;
- output paths;
- cleanup;
- structured results and errors.

The GUI should subscribe to job events instead of managing low-level worker details.

### 2.2 Make cancellation and shutdown graceful — P1

- Remove `os._exit(0)` from normal window shutdown.
- Signal cancellation and wait a bounded time for downloader/FFmpeg work.
- Terminate or kill child processes that do not stop.
- Add stop events to telemetry and updater threads.
- Prevent duplicate close/conversion actions during shutdown.

**Acceptance:** Closing during download, FFmpeg work, thumbnail fetch, and playlist processing leaves no orphan process or partial media output.

### 2.3 Centralize output policy — P1

Use one tested output-policy function for GUI and CLI:

```text
Music/<Source>/media.ext
Videos/<Source>/media.ext
Miscellaneous/Audio/media.ext
Miscellaneous/Videos/media.ext
```

The explicit category option must not accidentally flatten Spotify, YouTube, and SoundCloud if source separation remains a product requirement.

### 2.4 Make metadata collision-safe — P1

- Keep media separate from metadata.
- Use a per-source/per-item metadata directory, or apply collision-safe naming to cover art and text files.
- Never overwrite metadata because two titles sanitize to the same name.
- Add a manifest linking media, source URL, category, platform, and metadata paths.

### 2.5 Strengthen the library model — P1

- Represent media, playlists, metadata, and sources as explicit records.
- Keep file deletion and playlist-folder deletion visibly distinct.
- Report deletion/refresh failures instead of silently hiding them.
- Cache library snapshots and refresh only after relevant changes.

### 2.6 Add resume and retry — P2

- Persist playlist job manifests.
- Add “Retry failed tracks.”
- Skip completed tracks during resume.
- Preserve original ordering and source metadata.

## Phase 3 — Consumer installation and runtime isolation

### 3.1 Use a private runtime — P1

- Create a local `.venv` during setup.
- Install dependencies into that environment, not global Python.
- Use a tested constraints/lock file and hashes where practical.
- Make the native launcher resolve the private interpreter first.
- Report the exact missing dependency when launch fails.

### 3.2 Move writable data to user storage — P1

Use writable paths such as:

```text
JaneConverter\
├── config.json
├── logs\
├── temp\
└── converted\
```

If the application is placed in a protected directory, fall back to a
writable per-user directory. Let users choose another export folder at any
time, and migrate the previous `%LOCALAPPDATA%\JaneConverter` store without
overwriting conflicts.

### 3.3 Harden setup — P1

- Verify Python, FFmpeg, FFprobe, and optional Node.js versions.
- Handle winget unavailable, cancelled, blocked, and partially successful installs.
- Resolve absolute executable paths after installation.
- Make setup idempotent.
- Explain the Node.js recommendation.
- Verify dependencies after setup and before launch.

### 3.4 Choose a clear distribution model — P1

Choose one primary path:

1. Portable bundle with private runtime and legally distributable FFmpeg;
2. Installer with private runtime and dependencies;
3. Source setup with honest prerequisite requirements.

Do not present a developer Git clone and self-patching workflow as the normal consumer experience unless that is intentional.

## Phase 4 — Trustworthy updates, errors, and privacy

### 4.1 Replace live self-patching with staged releases — P1

- Make startup update checks read-only.
- Do not run `pip install` or `git pull` automatically in a consumer install.
- Use versioned release artifacts with checksums and, ideally, signing.
- Stage downloads and validate them before replacement.
- Apply updates on restart with rollback on failed launch.
- Keep “Check” separate from “Install.”

### 4.2 Test every update failure path — P1

Cover offline use, timeouts, missing Git metadata, local changes, divergence, failed fast-forward, pip failure, compiler failure, insufficient permissions, interruption, and restart after update.

Every failure must leave the previous installation runnable and show an actionable message.

### 4.3 Add friendly error categories — P1

Map common failures to clear guidance:

- FFmpeg/FFprobe missing;
- unsupported or private source;
- removed/region-locked media;
- timeout/rate limit;
- disk full or destination not writable;
- GPU encoder failure;
- artwork failure;
- cancellation.

Keep technical details in the Console/log file, not the primary dialog.

### 4.4 Document privacy and network behavior — P2

- Document every network request and when it occurs.
- Make startup checks configurable and throttled.
- Redact tokens, credentials, and sensitive query values from logs.
- Do not claim local conversion is network-free if startup update checks still run.
- Keep legal and platform terms visible and accurate.

## Phase 5 — Test and quality gates

### 5.1 Make the full suite deterministic — P0

- A clean checkout must pass without Git safe-directory configuration.
- Tests must not depend on repository temp permissions or stale generated files.
- Inject temporary directories using pytest fixtures.
- Keep online tests opt-in.
- Remove cache and ownership warnings from CI.

### 5.2 Add performance regression tests — P0

Test 100,000 synthetic progress events, 100,000 log events, bounded UI-pump behavior, a 1,000-file library scan, long paths/titles, and abort latency under download and FFmpeg work.

### 5.3 Add GUI smoke coverage — P1

On Windows CI or a dedicated smoke job:

- instantiate the main window;
- navigate all sidebar views;
- collapse/expand repeatedly;
- render a 100+ track playlist;
- render long-title library rows;
- verify open-folder and deletion confirmation;
- close during a mock active job.

### 5.4 Add backend contract tests — P1

Cover output paths, category/source rules, metadata placement, collision handling, source hostname classification, playlist schemas, job states, cancellation cleanup, GPU fallback, and updater staging.

### 5.5 Automate quality checks — P2

- Keep pyflakes clean.
- Add formatting/import checks.
- Publish coverage and enforce a modest floor after a baseline.
- Scan dependencies for vulnerabilities and license issues.
- Smoke-test the assembled Windows artifact.

## Phase 6 — Documentation and supportability

### 6.1 Synchronize the README — P1

Correct stale claims about Play versus Folder actions, sidebar versus header updates, playlist cover placement, metadata layout, `--no-cover-art` versus `--no-art`, `--output` versus `--output-dir`, displayed duration/timestamps, supported formats, and current source behavior.

### 6.2 Add consumer documentation — P1

Include a quick start, screenshots, supported versions, hardware/disk guidance, category definitions, output locations, logs, retry behavior, uninstall/data removal, troubleshooting, legal terms, and licensing.

### 6.3 Add support diagnostics — P2

Provide a copyable diagnostic summary containing app/OS/runtime/FFmpeg/engine versions and hardware mode, with sensitive paths and URLs redacted. Add stable error codes and a bug-report template.

## Phase 7 — Release engineering

### 7.1 Build a reproducible Windows artifact — P1

Create a tag-triggered workflow that builds the launcher, assembles the runtime, runs artifact smoke tests, produces ZIP/installer output, generates SHA-256 checksums, records dependency versions, and publishes user-facing release notes.

### 7.2 Establish trust signals — P1

- Sign the executable/installer if distribution scale justifies it.
- If unsigned, document SmartScreen behavior and checksum verification.
- Never ask users to disable security tools globally.

### 7.3 Define version and migration policy — P2

- Use semantic versioning consistently.
- Define config/output migration.
- Preserve user files during upgrades.
- Explain downgrade behavior.
- Write changelogs for users as well as developers.

## Release-candidate acceptance matrix

| Scenario | Pass condition |
|---|---|
| Fresh install on clean Windows account | Setup succeeds without global Python contamination. |
| Missing prerequisite | User receives clear remediation and setup exits cleanly. |
| Local audio conversion | Correct, tagged, organized, discoverable output. |
| Local video conversion | Correct output with CPU fallback when GPU is unavailable. |
| Online source | Clear handling for network, source, and platform failures. |
| Long conversion | UI remains responsive and progress is current. |
| Large playlist | Catalog remains usable without unbounded widgets. |
| Abort | Prompt stop with no orphan process or partial output. |
| Close during conversion | Graceful confirmation, cancellation, cleanup, and exit. |
| Large library | Worker-backed discovery and progressive rendering. |
| Long title/path | Controls remain visible and target the correct path. |
| Duplicate title | Media and metadata never overwrite one another. |
| Offline startup | Opens promptly with a clear/quiet offline state. |
| Update available | Read-only check is safe; install is explicit and recoverable. |
| Update failure | Existing install remains runnable. |
| Non-Git install | App works without Git metadata. |
| Upgrade | User files and settings are preserved or migrated. |

## Milestone sequence

### Milestone A — Performance emergency

Ship progress coalescing, bounded UI work, batched/capped logs, and off-thread library discovery. Do not add more visual features until the lag benchmark passes.

### Milestone B — Safe beta

Ship the job controller, graceful shutdown, output-policy tests, metadata collision protection, friendly errors, and deterministic tests.

### Milestone C — Consumer preview

Ship private runtime/data paths, idempotent setup, release artifacts, documented prerequisites, and read-only update checks. Test on clean machines.

### Milestone D — Release candidate

Freeze features. Fix only blockers, packaging failures, documentation mismatches, and verified regressions. Run the complete acceptance matrix.

### Milestone E — Official release

Publish the artifact, checksums/signature status, known limitations, legal terms, support instructions, uninstall guidance, and rollback procedure.

## Definition of done

JaneConverter is officially consumer-release-ready when:

- all P0/P1 work is complete or formally risk-accepted;
- the performance benchmark shows no event-loop starvation;
- full CI and artifact smoke tests pass;
- setup does not depend on global Python state;
- common failures are recoverable without reading a traceback;
- updater behavior is explicit, staged, and reversible;
- output and metadata behavior matches the documentation;
- license and platform claims are consistent;
- a clean-machine pilot passes the acceptance matrix;
- a tagged release can be reproduced and rolled back.

## Post-release backlog

Consider queued conversions, pause/resume, retry-failed tracks, subtitles/chapters, richer library filtering, persistent settings, optional offline FFmpeg, accessibility/keyboard navigation, localization, and additional platform packaging after the core release is stable.
