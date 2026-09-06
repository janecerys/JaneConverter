# JaneConverter Release-Ready Overhaul

Proprietary under project//aspyr (no LICENSE file; README states ownership clearly). All fixes executed in phases, each verified with the test suite and committed separately so we can stop or adjust between phases.

## Phase 1 — Critical launch & repo blockers
1. **Fix GUI launch crash**: add `Callable` to the typing import in `gui.py:15`; audit `gui.py` + engine for any other undefined names (compile-check all files).
2. **Untrack the binary**: `git rm --cached JaneConverter.exe`; update `.gitignore` (add `*.exe` for root builds, `venv/`, `.venv/`, `ffmpeg.exe`, `build/`, `dist/`, `.vs/`).
3. **README truth-up**: License section → "Proprietary — © 2026 project//aspyr. All rights reserved."; fix test count; add a short "Legal & ToS disclaimer" section (personal-use tool, respect platform ToS).

## Phase 2 — Update-pipeline trust (security)
4. `engine/updater.py`: check `returncode` of the csc.exe recompile and report failure honestly; remove the dead `check=True` branch; make repo self-patch **opt-in** (ask before git pull + pip install); resolve the actual remote/branch instead of hardcoded `origin/main`; pass a version bound to the yt-dlp upgrade (e.g. `yt-dlp>=current` guard instead of blind `--upgrade`); dedupe the double `check_for_engine_updates()` call.
5. `engine/extractor.py`: keep EJS remote components but document them; make the engine-update behavior consistent with the GUI consent toggle.

## Phase 3 — Correctness bugs
6. **Credits file**: pass `source_url`/`platform` keys correctly from `process_conversion` (`run_converter.py`) so single-track credits include Source and Platform lines.
7. **Playlist checkboxes**: key `check_vars` by the entry's identity (id(entry) or a guaranteed per-entry index) instead of `entry.get("index", 1)`.
8. **Orphan partials**: delete the partial output file before each ffmpeg retry and after final failure in `engine/converter.py`.
9. **GUI settings mapping**: fix video mode reading bitrate from the resolution menu; restore the playlist button's highlighted state after a failed catalog fetch; guard `pdata['total_count']` access.
10. **Spotify extractor**: per-track cover art for albums/playlists when available; clear "could not resolve metadata" error instead of feeding Spotify URLs to yt-dlp; guard `upload_date` non-string; keep per-track search behavior.
11. **VAAPI/webm**: add the required `-vaapi_device` + `format=nv12,hwupload` filter chain; include webm in the GPU→CPU fallback; fix webm hwaccel decode handling.
12. **sanitize_filename**: strip control characters, handle Windows reserved device names (CON, NUL, COM1–9, LPT1–9…).
13. **Converter nits**: `-thread_queue_size` on the cover-art input; replace substring bit-depth sniffing with an explicit mapping; map `loudnorm` string to one constant.
14. **Filename discovery**: extend the post-download extension fallback list (`.mov/.avi/.aac/...`) and/or trust yt-dlp's prepared filename.

## Phase 4 — Threading & robustness
15. **Logging**: replace global `sys.stdout` swapping with a `logging.Handler` feeding the existing queue poller in `gui.py`.
16. **Thread-safe UI**: route all worker→UI updates through the queue/`after` mechanism from the main thread only; single persistent hardware-monitor loop (fixes psutil first-call 0.0 and thread respawn).
17. **Shutdown**: on window close, warn if a conversion is running (offer abort-and-exit); set the abort event before exit; per-instance temp subdirectory so two app instances can't delete each other's jobs.
18. **Resilience**: disk-space check before download/transcode; playlist batch aborts early after N consecutive failures (network-dead detection); validate destination folder exists/creatable before starting.

## Phase 5 — UX & performance
19. **Real progress**: parse `ffmpeg -progress pipe:1` for true percentage (duration-aware) instead of the hardcoded 0.8→1.0 jump.
20. **Playlist selector**: cap/virtualize track rows (windowed rendering) so 500+ track playlists don't freeze; O(1) filtering.
21. **Deduplication**: extract shared settings-parsing (`_collect_settings()`), collapse the duplicated GPU encoder ladder, cache `get_best_hardware_encoder` per session.
22. **Polish**: replace per-conversion success dialogs with status/toast + elapsed time (uses the already-tracked `start_conversion_time`); remove dead code (`_play_latest_file`, `--no-nvenc`, unused state); CLI `--version`.

## Phase 6 — CLI & tests & release engineering
23. **CLI**: validate `--format/--bitrate/--sample-rate` values with clear errors; proper exit codes (non-zero when any track fails); refuse `--playlist` on local files; friendly top-level error handling (no raw tracebacks).
24. **Tests**: add `pytest` + `requirements-dev.txt`; make the suite hermetic — mock `requests`/`yt_dlp`/`subprocess` for Spotify, YouTube, and updater tests; delete/replace the live "Today's Top Hits" assertions; keep an opt-in `@pytest.mark.online` marker for the few real-network tests; add tests for the new fixes (credits keys, checkbox keying, partial cleanup, sanitizer reserved names, CLI exit codes).
25. **CI**: add `.github/workflows/ci.yml` running `pytest` on `windows-latest` (matrix ubuntu for cross-platform lint of engine code).
26. **Versioning**: add a `__version__` constant surfaced in GUI header + `--version`; `CHANGELOG.md`; tag `v1.0.0` when done.

Deliverable: a clean `main` with ~6 phase commits, all tests passing hermetically, CI green, and a release-ready v1.0.0 tag.