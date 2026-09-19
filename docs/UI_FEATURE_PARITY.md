# JaneConverter UI Feature Parity

The Main UI (Tauri) desktop surface is intended to replace the default launch surface without removing the legacy Python launcher or the existing Rust/egui fallback.

| Legacy Python capability | Main UI surface | Status |
| --- | --- | --- |
| URL or local path source field | Converter > Source media | Implemented |
| Paste from clipboard | Paste button and browser clipboard API | Implemented |
| Browse local media | Rust native file dialog | Implemented |
| Source detection/status | Source state and engine status | Implemented |
| Playlist/album track loading | Playlist tracks button | Implemented |
| Playlist filtering | Track selector search field | Implemented |
| Select all / deselect / invert | Track selector actions | Implemented |
| Convert selected playlist items | Track selector confirmation | Implemented |
| Account access temporary link | Create/open/copy/clear access actions | Implemented |
| Browser-session detection | Local Rust access server status | Implemented |
| Apple Music notes and common failures | Expandable source notes | Implemented |
| Spotify notes and common failures | Expandable source notes | Implemented |
| Other-source and local-file warnings | Expandable source notes | Implemented |
| Music category | Category selector | Implemented |
| Video category | Category selector | Implemented |
| Miscellaneous category | Category selector | Implemented |
| MP3 / FLAC / WAV / AAC / OGG | Container format selector | Implemented |
| MP4 / MKV / WEBM / MOV / GIF | Container format selector | Implemented |
| Audio bitrate choices | Quality selector | Implemented |
| WAV / FLAC bit depth | Quality selector | Implemented |
| OGG quality | Quality selector | Implemented |
| Video quality choices | Quality selector | Implemented |
| Audio sample rate | Sample-rate selector | Implemented |
| Video resolution | Resolution selector | Implemented |
| EBU R128 normalization | Toggle | Implemented |
| GPU/hardware acceleration | Toggle with runtime GPU label | Implemented |
| Cover art / thumbnail | Toggle | Implemented |
| Credits and metadata export | Toggle | Implemented |
| Destination folder | Project-local default plus Rust folder dialog | Implemented |
| Convert media | Primary action | Implemented |
| Abort conversion | Abort action with process-tree termination on Windows | Implemented |
| Progress bar and status text | Animated progress/status area | Implemented |
| Open output folder | Native folder opener | Implemented |
| Converted library scan | Library view | Implemented |
| Library folder navigation | Open/back actions | Implemented |
| Open containing folder/file | Native opener | Implemented |
| Delete with confirmation | Safe in-library delete action | Implemented |
| Live conversion console | In-app Console view | Implemented |
| Copy logs | Console action | Implemented |
| Clear logs | Console action | Implemented |
| Check for updates | Settings action | Implemented |
| Use Rust UI next launch | Settings > Legacy Rust | Implemented |
| Keep Python UI available | Settings > Legacy Python and --legacy-python | Implemented |
| Hide external console during normal use | Tauri process bridge with no-window flags on Windows | Implemented |
| Project-local data paths | Runtime/settings display and default paths | Implemented |

## Deliberate behavior notes

- The Python engine remains the source of truth for extraction, Apple Music/Spotify resolution, FFmpeg conversion, metadata, retries, and provider diagnostics.
- The new UI does not store browser passwords or cookies. The account-access link is local, temporary, and session-only.
- User-selected export folders are never silently moved.
- A live external media conversion was not used as an automated test fixture; the engine's existing Python test suite remains the conversion behavior gate.
- The release build must contain JaneConverterDesktop.exe, JaneConverterNative.exe, and the legacy Python files before the Main UI launcher is considered complete.
