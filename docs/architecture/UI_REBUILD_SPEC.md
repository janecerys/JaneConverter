# JaneConverter Desktop UI Rebuild

## Decision

JaneConverter will gain a new `desktop-ui` application built with Tauri 2, React, TypeScript, Tailwind CSS, and Framer Motion. Rust will own native dialogs, process control, event forwarding, local storage paths, library operations, and the bridge to the existing Python conversion engine.

The legacy Python launcher UI remains available as a recovery path. The existing Rust/egui UI remains available as a secondary fallback until the Main UI surface has passed the feature-parity and packaging gates.

## Goals

- Match the quiet, dark, editorial feel of the Jane Cerys portfolio and JaneClipper.
- Use pink as a restrained signal color rather than a large surface fill.
- Keep motion subtle, purposeful, interruptible, and disabled/reduced for users who prefer reduced motion.
- Keep application data, conversion output, temporary files, logs, and caches beside JaneConverter whenever the user has not explicitly selected another location.
- Preserve the existing Python conversion pipeline and its source behavior, including Apple Music diagnostics and fallback handling.
- Make the Main UI usable without exposing a console window during normal conversion while keeping an in-app live console available.

## Feature parity contract

The Main UI launcher must expose all behavior available in the legacy Python UI:

1. Source URL or local path input, clipboard paste, local-file picker, source detection, playlist/album track loading, and playlist track selection.
2. Optional browser-session account access with a temporary localhost link, browser detection, copy/open/clear actions, and no password or cookie storage.
3. Music, video, and miscellaneous categories; MP3, WAV, FLAC, AAC, OGG, MP4, MKV, WEBM, MOV, and GIF output formats.
4. Audio bitrate, WAV/FLAC bit depth, OGG quality, video quality, sample-rate, resolution, EBU R128 normalization, GPU/hardware acceleration, cover art/thumbnail, and metadata/credits export controls.
5. Destination-folder selection, project-local default output, convert, abort, progress/status, open-folder, and the existing bounded retry behavior of the Python engine.
6. Converted Library browsing, refresh, folder navigation, open file/folder, delete with confirmation, item counts, sizes, and playlist grouping.
7. Live console logs, copy logs, clear logs, readable failure messages, source notes/common failures, update check, interface preference, and legacy Python fallback.

## Capability map

- `desktop-shell`: Tauri window, launch mode, local assets, reduced motion, keyboard focus, native dialogs.
- `converter-workspace`: source card, output controls, destination, actions, progress, status.
- `playlist-and-access`: playlist catalog, selection dialog, temporary browser access handoff.
- `library`: project-local or user-selected output browsing and safe file actions.
- `console-and-diagnostics`: bounded event stream, copy/clear, source notes, runtime readiness.
- `settings-and-storage`: persisted preferences, explicit paths, storage transparency.
- `legacy-compatibility`: Python UI, old Rust UI, launcher switches, preference migration.
- `packaging`: Tauri build, release staging, Windows launcher integration, source-checkout fallback.

## Visual contract

- Background: near-black violet, with low-opacity ambient gradients only.
- Surfaces: charcoal/violet panels with thin neutral borders and restrained blur.
- Pink: small indicator, active-nav edge, progress accent, and focused action only.
- Cyan/blue: informational and link state; green: ready/success; red: destructive/error.
- Typography: system/Plus Jakarta Sans style for UI, compact monospace labels for runtime and console metadata.
- Motion: nav indicator transitions, panel reveal, progress state, and ambient background drift only. No perpetual high-contrast pulsing.

## Storage contract

The default data root is the JaneConverter project directory (or the configured `JANECONVERTER_DATA_DIR`). Defaults remain project-local for `converted`, `temp`, settings, logs, and update state. A user-selected output directory is respected exactly. The new UI must display the active paths and must not silently redirect media to AppData or another C: location.

## Verification gates

- React typecheck/build passes.
- Frontend tests cover default settings, source/options mapping, playlist selection, and reduced-motion-safe rendering behavior.
- Rust tests cover CLI argument construction, playlist-output parsing, safe library deletion boundaries, preference read/write, and progress parsing.
- Existing Python test suite remains green.
- A feature matrix shows every legacy control mapped to a new control or a deliberate equivalent.
- Release build produces the Main UI executable while retaining legacy Python and Rust fallback launch paths.
- Manual smoke test covers local media, one online URL, playlist selection, abort, library open/delete, account-access link creation, and console copy/clear.

## Non-goals for the first UI slice

- Rewriting the Python conversion engine.
- Moving user-selected outputs without consent.
- Adding a second media extraction implementation before the existing engine contract is stable.
- Shipping decorative assets that materially increase the installer size.
