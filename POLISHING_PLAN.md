# JaneConverter — Post-1.0 Polishing Plan

**Version:** 1.0 (2026-09-07) · **Baseline:** v1.0.0 (`fa5f62b`) · **Owner:** Jane Cerys / project//aspyr

This plan turns the v1.0.0 software assessment into a sequenced, actionable roadmap.
Every item lists its rationale, concrete tasks, and acceptance criteria, so progress
is verifiable rather than vibes-based. Items are grouped into four phases ordered by
(user value ÷ effort ÷ risk). Phases may be executed out of order, but within a phase,
tasks should land in listed order.

---

## Guiding Principles

1. **No regressions.** Every phase keeps the hermetic test suite green (`pytest -q`, 58 tests) and pyflakes clean. CI is the gate, not a suggestion.
2. **Refactor behavior-preserving.** GUI decomposition changes structure, not behavior. Tests are added *before* each move where possible.
3. **Fail loudly, recover gracefully.** Every new code path must surface errors to the user (status bar or console log) — silent `except: pass` is banned in new code.
4. **Small commits, one concern each.** Matches the v1.0.0 overhaul convention (8 focused commits).

---

## Current State Snapshot

| Metric | Value |
|---|---|
| Engine code | ~2,280 LOC (4 modules) |
| GUI | 1,965 LOC, single 1,400-line class |
| Tests | 58 hermetic + 8 opt-in online, ~2.5 s runtime |
| CI | GitHub Actions — Windows + Ubuntu, Python 3.10/3.12 |
| Lint debt | 2 unused imports in `tests/test_converter.py` |
| Release | Tagged v1.0.0, no binary artifacts published |

---

## Phase 1 — Quick Wins *(est. 1–2 days · low risk)*

Small, additive changes with immediate user-visible payoff.

### 1.1 Settings persistence  ★ highest value-per-LOC
- **Rationale:** Every launch resets format, destination, normalization, and GPU toggles. This is the #1 user-visible gap vs. every competitor.
- **Tasks:**
  - New module `engine/config.py`: load/save a JSON file at `%APPDATA%/JaneConverter/config.json` (Windows) or `~/.config/JaneConverter/` (Linux/macOS fallback).
  - Persist: last source URL, destination folder, format, quality, sample rate, normalize/art/metadata/GPU toggles, window geometry.
  - Load in `JaneConverterApp.__init__`; save on change (debounced) and on close.
  - CLI: leave flags authoritative; do **not** let config override explicit flags.
- **Acceptance:** Restart the app → all selections restored. Deleting the config file → clean fallback to defaults. Config corruption → warning logged, defaults used, app still launches.

### 1.2 Error-message hygiene
- **Rationale:** Dialogs currently dump raw exception text (`RuntimeError: FFmpeg transcode error: ...`).
- **Tasks:**
  - Add `FRIENDLY_ERRORS` mapping in `run_converter.py` for the ~10 known failure classes (ffmpeg missing, disk full, network dead, Spotify unresolvable, unsupported URL, abort).
  - Dialog body shows the friendly sentence; full detail stays in the Console tab and a "Show details" expander (or copied-to-clipboard button).
- **Acceptance:** Simulated failures show human sentences; tracebacks remain available in the Console tab.

### 1.3 Repo hygiene specks
- Remove the two unused imports in `tests/test_converter.py` (last pyflakes findings).
- Add CI status badge to the top of `README.md`.
- Add a short "Contributions" note in the README stating the project is proprietary and does not accept outside code, with a link to the issue tracker for bug reports.

**Phase 1 exit criteria:** green CI, restart-persistence works, zero pyflakes findings repo-wide.

---

## Phase 2 — Structural Refactor *(est. 1–2 weeks · medium risk, behavior-preserving)*

### 2.1 Decompose `gui.py` (1,965 LOC → target < 700 LOC main file)
- **Rationale:** A single class mixing chrome, telemetry, library, playlist workflow, and pipeline invocation is the main maintainability drag. Engine layering is already clean; the GUI is the outlier.
- **Target layout:**
  ```
  gui/
  ├── __init__.py        # app entry (main())
  ├── theme.py           # THEME dict, fonts
  ├── widgets.py         # StdoutRedirector, badges, shared components
  ├── telemetry.py       # hardware monitor (pynvml/psutil loop)
  ├── library.py         # Converted Library tab
  ├── playlist_window.py # PlaylistSelectionWindow
  ├── settings.py        # _collect_settings() logic, decoupled from widgets
  └── app.py             # JaneConverterApp (chrome + wiring only)
  ```
- **Order of extraction (each its own commit, tests green between):**
  1. `theme.py` (pure data — zero risk)
  2. `widgets.py` (StdoutRedirector + helpers)
  3. `telemetry.py` (monitor loop; already self-contained)
  4. `playlist_window.py` (already a separate class)
  5. `library.py` (library tab methods)
  6. `settings.py` (make `_collect_settings` read from a plain dict passed in, enabling unit tests without a running window)
- **Acceptance:** `python gui.py` behaves identically; import graph has no cycles; new unit tests cover settings parsing from a plain dict.

### 2.2 Updater failure-path hardening
- **Rationale:** The most security-sensitive module has tests only for its happy surface.
- **Tasks:**
  - Mock `subprocess.run` / `_run_git_cmd` in tests: failed `git pull` (non-ff divergence), failed pip install, failed csc recompile, offline, and timeout paths.
  - Add a "last update check" timestamp to config (Phase 1) so the startup check can be throttled (e.g., skip if checked < 6 h ago) — fewer surprise mid-session swaps.
- **Acceptance:** Every updater failure branch has a test asserting the user-visible message and that no partial state is left behind.

**Phase 2 exit criteria:** `gui.py` decomposed, all behavior identical, updater branches fully mocked-tested, suite ≥ 75 tests.

---

## Phase 3 — Reliability & Reach *(est. 1–2 weeks · medium risk)*

### 3.1 Spotify resilience
- **Rationale:** The metadata path regex-scrapes `__NEXT_DATA__` with no schema validation; when Spotify changes layout, every Spotify download degrades silently.
- **Tasks:**
  - Validate the parsed entity (required keys: title + artists/trackList). On missing keys, raise a *distinct* error class `SpotifyParseError`.
  - Map `SpotifyParseError` to a specific user message: "Spotify's page format changed — engine update required" (and check for a newer yt-dlp/app version in that state).
  - When `total_count` reported by the embed exceeds returned entries (the ~100-track cap), log and show: "Showing first 100 of N tracks (Spotify embed limit)."
- **Acceptance:** A crafted malformed embed payload produces the dedicated message, not a generic failure; a >100-track playlist shows the cap notice.

### 3.2 Coverage measurement
- Add `pytest-cov` to `requirements-dev.txt`; publish coverage in CI output; set an informational floor (do not gate) at current level.
- **Acceptance:** CI prints per-file coverage; no coverage regression goes unnoticed.

### 3.3 GUI smoke test in CI
- Commit the existing ad-hoc smoke script as `tests/test_gui_smoke.py`, marked `@pytest.mark.skipif(not display)` — Windows CI job only.
- **Acceptance:** Windows CI instantiates the app and a 45-entry playlist window; asserts all rows render (regression guard for the batch-30 bug class).

### 3.4 Release artifacts
- Add a `release.yml` GitHub Actions workflow: on tag push (`v*`), build `JaneConverter.exe` via csc, zip the portable app folder (source + launcher + requirements), and attach to a GitHub Release.
- Document the unsigned-binary SmartScreen warning in the release notes template.
- **Acceptance:** Pushing `v1.0.1` produces a downloadable zip on the Releases page automatically.

**Phase 3 exit criteria:** Spotify breakage is detectable and communicable; releases ship artifacts; coverage visible in CI.

---

## Phase 4 — Differentiator Deepening *(est. ongoing · feature work)*

Optional but high-identity features — the things only JaneConverter does.

### 4.1 Playlist limit transparency & partial handling
- UI notice when a Spotify playlist is truncated at ~100 tracks; offer "convert first 100" explicitly.

### 4.2 Resume / re-run failed tracks
- Playlist summaries already list `failed_files`; add a "Retry failed tracks" action that re-processes only those entries into the existing folder (skip existing files via `get_unique_target_path` semantics).

### 4.3 Subtitle support (market parity)
- `--subtitles` flag: fetch/embed `yt-dlp` subtitle tracks for video targets.

### 4.4 Queue management (stretch)
- Allow stacking conversions in a visible queue instead of one active job; the thread-safe UI pump and abort plumbing already support this.

---

## Out of Scope (deliberate)

- **License change** — remains proprietary, property of project//aspyr.
- **ToS-compliant sourcing** — the tool class is what it is; the README disclaimer is the accepted posture.
- **Code signing certificate** — purchase decision, not an engineering task; note it as a future business step.
- **macOS/Linux first-class support** — the launcher and installer are Windows; engine code stays cross-platform-clean but packaging is out of scope.

---

## Success Metrics for "Polished"

| Metric | Baseline (v1.0.0) | Target |
|---|---|---|
| Hermetic tests | 58 | ≥ 85, incl. updater failure paths + GUI smoke |
| CI coverage visibility | none | per-file report every run |
| `gui.py` size | 1,965 LOC, 1 class | < 700 LOC main file, 7 focused modules |
| User-visible error classes w/ friendly text | ~2 | ~10 |
| Settings persistence | none | full restore across restarts |
| Release artifacts | none | automated zip per tag |
| pyflakes findings | 2 | 0 |

---

## Suggested Cadence

- **Week 1:** Phase 1 complete → tag `v1.0.1`.
- **Weeks 2–3:** Phase 2 → tag `v1.1.0`.
- **Weeks 4–5:** Phase 3 → tag `v1.2.0`.
- **Phase 4:** pull-driven, one feature per minor release.

*Estimated total: ~4–6 weeks of part-time effort to reach every "Polished" target.*
