# JaneConverter

<p align="center">
  <img src="assets/icon.png" width="128" height="128" alt="JaneConverter application icon" />
</p>

<p align="center">
  <strong>Universal Media Downloader & High-Fidelity Transcode Studio</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows%2010%2F11%20%7C%20macOS%20%7C%20Linux-blue?style=flat-square" alt="Platform" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-blueviolet?style=flat-square" alt="Python" />
  <img src="https://img.shields.io/badge/Acceleration-Universal%20GPU%20(NVENC%20%2F%20AMF%20%2F%20QSV)-success?style=flat-square" alt="Hardware Acceleration" />
  <img src="https://img.shields.io/badge/Audio-24--bit%20WAV%20%7C%20FLAC%20%7C%20320k%20MP3-orange?style=flat-square" alt="Audio" />
</p>

**Current release: v1.2.0** — The release includes the Main UI, shared library management, cover previews, and one-click relaunch controls across all three interfaces.

JaneConverter downloads media from virtually any online source, matches high-resolution metadata and album cover art, normalizes audio to streaming broadcast standards, and transcodes files into studio-grade audio or hardware-accelerated video formats.

The standard way to use JaneConverter is its modern dark-themed desktop studio application. A complete command-line interface is also available for automated workflows and terminal users.

JaneConverter runs from a private Python environment with an optional native launcher and automated setup scripts for Windows, macOS, and Linux. Update checks are read-only; a verified staged package is applied by a short-lived restart helper before the next launch.

On Windows, launch `JaneConverter.exe`, the universal entry point. It reads the saved launch preference and starts the Main UI (Tauri + React), Legacy Rust, or Legacy Python interface. All three inherit the same project-local data root and therefore share the same `converted` library. On macOS and Linux, use `run_converter.sh`; it uses the selected frontend when available and falls back to the original Python interface.

### Interface preference

JaneConverter.exe opens the Main UI by default. In Settings, choose Main UI, Legacy Rust, or Legacy Python; the choice is saved beside the launcher. Each interface now exposes a **Relaunch** action so the selected interface can be applied immediately without manually closing and reopening the program. The individual child executables remain available for recovery and diagnostics, but the universal launcher is the normal entry point. The development checkout also keeps a top-level `JaneConverter.exe`; it resolves the newest complete package under `dist` so the main launcher is easy to find without duplicating the application files. Unless `JANECONVERTER_DATA_DIR` is set, every interface uses the `converted` folder beside `JaneConverter.exe`.

## Source troubleshooting FAQ

### Why can Apple Music fail even when the link is recognized?

Apple Music links are resolved through Apple's public catalog for metadata, artwork, track IDs, and public album listings. Apple's official APIs do not expose subscription audio as a normal downloadable stream. JaneConverter therefore searches existing supported public sources for a matching full stream. Conversion can still fail when the track is region-restricted, removed, private, a music video, an alternate version, or unavailable from the matched source. Use a direct public song URL containing `?i=TRACK_ID` when possible.

### Why can Spotify fail?

Spotify links provide metadata for identification; JaneConverter does not download protected Spotify audio directly. Private, deleted, region-limited, or ambiguous tracks may not produce a matching public stream. Check the title and artist in the Console output and try the direct track URL.

### Why can YouTube, SoundCloud, TikTok, X/Twitter, or another site fail?

The provider may require login, enforce an age or regional restriction, return a bot check, rate-limit requests, delete the media, or change its page/API format. Open the link in a normal browser first, use Account Access only when needed, and retry with the direct page URL rather than a shortened or embedded link.

### Why can a local file or otherwise valid source fail?

The file may be unreadable, the output folder may not be writable, disk space may be low, or FFmpeg/ffprobe may be missing. The Console contains the detailed reason. A recognized source and an available downloadable stream are separate checks.

## v1.2.0 release highlights

- **Main UI:** Tauri 2 + React + TypeScript desktop surface with Tailwind styling, restrained motion, a low-contrast pink glow, and native Rust process/file-dialog bridging.
- **One universal launcher:** `JaneConverter.exe` opens the selected Main UI, Legacy Rust, or Legacy Python interface while keeping settings and exports in the same project-local data root.
- **Shared converted library:** All three interfaces browse the same export directory. The Main UI can open the root folder, move the library, preview media thumbnails/covers, refresh, and safely delete items without leaving the configured root.
- **Immediate interface switching:** Main UI, Legacy Rust, and Legacy Python each provide a relaunch path that applies the saved interface preference.

## Project documentation

- [UI rebuild architecture and parity contract](docs/architecture/UI_REBUILD_SPEC.md)
- [Backend and release audit](docs/audits/BACKEND_AUDIT.md)
- [Main UI feature parity matrix](docs/audits/UI_FEATURE_PARITY.md)
- [Release-readiness roadmap](docs/planning/RELEASE_READINESS_ROADMAP.md)
- [Post-1.0 polishing plan](docs/planning/POLISHING_PLAN.md)

## What it does

For each media link or local file, JaneConverter:

1. **Analyzes the source**: Identifies whether the input is a single video, audio stream, public Spotify or Apple Music link, playlist, or local disk file.
2. **Extracts public metadata**: For Spotify tracks or albums and public Apple Music song or album links, resolves the title, artist, album, release year, and high-resolution cover art without requiring user logins or API keys.
3. **Retrieves the stream**: Automatically queries the highest-fidelity audio or video stream from YouTube, SoundCloud, TikTok, Twitter/X, Reddit, Vimeo, Facebook, Twitch, or supported adult streaming platforms.
4. **Normalizes loudness**: Optionally applies industry-standard EBU R128 loudness normalization (-14 LUFS integrated, -1.5 dB true peak) to match commercial streaming broadcast loudness without clipping.
5. **Embeds artwork and tags**: Attaches front cover art directly into ID3v2.3 (MP3), FLAC, and M4A containers, and exports formatted production credits files (`_credits.txt`).
6. **Transcodes media**: Converts audio into 320 kbps MP3, 24-bit PCM WAV, FLAC Level 8, AAC/M4A, or OGG, or video into MP4/MKV via universal hardware acceleration (NVIDIA NVENC, AMD AMF, Intel QuickSync, Apple VideoToolbox, Linux VAAPI, or multi-core CPU threading).
7. **Organizes exports**: Saves regular media under `Music/<Source>/` or `Videos/<Source>/`, puts general-purpose material under `Miscellaneous/Audio/` or `Miscellaneous/Videos/`, and keeps metadata in collision-safe `metadata/` subfolders.

## Before you install

Windows is the officially packaged and validated release platform. macOS and Linux are experimental/community validation targets until clean-machine testing and signed distribution packages are available.

For the consumer Windows installer, the private runtime is bundled. The source and
portable paths have the prerequisites below:

- A 64-bit computer running **Windows 10/11**, **macOS 12 or newer**, or a modern 64-bit Linux distribution.
- **Python 3.10 or newer**. Windows setup can install it; macOS/Linux setup expects `python3` to already be installed.
- **FFmpeg** with `ffprobe`. Windows setup can install it; macOS/Linux setup expects it to already be installed.
- Available disk space for downloaded media and high-resolution audio exports.

Hardware acceleration:
- **Universal GPU Support**: Automatically detects NVIDIA (NVENC with p2 high-performance preset), AMD (AMF speed preset), Intel (Quick Sync / QSV), Apple Silicon (VideoToolbox), and Linux (VAAPI).
- **Full Hardware Pipeline**: Automatically offloads both hardware decoding (`-hwaccel auto`) and video encoding to your host GPU silicon.
- **Multi-Core Threading**: Automatically configures FFmpeg (`-threads 0`, `-thread_queue_size 1024`) to utilize all available CPU threads for peak throughput when processing media.
- **Zero Configuration Fallback**: If GPU encoding is unavailable or unsupported on a given system, JaneConverter seamlessly falls back to multi-core CPU encoding (`libx264`) without interrupting your queue.

Node.js is optional but recommended when fetching YouTube media, as it enables the extraction engine to solve current YouTube signature challenges.

## Installation & Setup

### Windows consumer installation (recommended)

Most consumers should use the single-file installer from the latest GitHub release:

1. Open the [latest JaneConverter release](https://github.com/janecerys/JaneConverter/releases/latest).
2. Under **Assets**, download **`JaneConverter-Setup.exe`** to your computer. Do not
   run it from inside a ZIP file.
3. Double-click the downloaded installer. If Windows shows SmartScreen, choose
   **More info** → **Run anyway** only when the file came from the official
   `janecerys/JaneConverter` release page.
4. Accept the default install location, or choose another folder with enough free
   space for the application and converted media.
5. Start JaneConverter from the Desktop or Start Menu shortcut. The **Main UI** is
   selected automatically; the Legacy Rust and Legacy Python interfaces remain
   available in **Settings → Launch preference**.
6. If you want to download media that requires an account session, install the
   optional Browser Bridge using the short instructions in **Authorized browser
   sessions** below. If you skip it, JaneConverter still works for public media.

The consumer installer is self-contained: Python, pip, Rust, Node.js, FFmpeg, and
FFprobe do not need to be installed separately. The installer also includes the
conversion engine, the shared converted-library support, the three launcher modes,
and the JaneConverter Browser Bridge files.

For a quick authenticity check before running the installer, download the matching
`JaneConverter-Setup.exe.sha256` file from the same release and run this in PowerShell
from the download folder:

```powershell
Get-FileHash .\JaneConverter-Setup.exe -Algorithm SHA256
```

The displayed hash must match the value in the `.sha256` file. If it does not, delete
the installer and download it again from the official release page.

The installer does not silently install a browser extension or read browser
passwords. Browser extensions require explicit user consent. JaneConverter ships the
bridge files beside the installed application; install them only if you need
account-only browser sessions, using the manual **Load unpacked** steps below.

### Portable/developer safety net

The `JaneConverter-1.2.0-windows.zip` package is the source-visible recovery path.
It keeps `setup.bat`, the Python engine, the legacy interfaces, diagnostics, and
the project-local data layout available for developers or troubleshooting. Extract
it to a normal folder first, then run `setup.bat` from the extracted folder. This is
not the recommended consumer path because it may need to install prerequisites and
is intended as a recovery/developer path.

### 1-Click Automated Setup (portable path)

Clone this repository or extract the downloaded ZIP folder, open PowerShell or Command Prompt in the `JaneConverter` folder, and run:

```powershell
.\setup.bat
```

What `setup.bat` does automatically:
1. Verifies **Python 3.10+** (installs it via winget if missing).
2. Verifies **FFmpeg** (installs it via winget if missing).
3. Verifies **Node.js** for YouTube bot challenge handling.
4. Creates a private `.venv` and installs all required Python dependencies from `requirements.txt` without changing the user's global Python environment.
5. Compiles the universal Windows launcher with the embedded app icon and builds both `JaneConverterDesktop.exe` and `JaneConverterNative.exe` when Rust/Cargo is available; the Python UI remains bundled as the recovery interface.
6. Creates a **JaneConverter** shortcut directly on your Windows Desktop.
7. Launches the studio window immediately.

### Manual Installation (Alternative)

If you prefer to install dependencies manually:

1. Install FFmpeg:
   ```powershell
   winget install Gyan.FFmpeg
   ```
2. Install Python dependencies:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
3. Launch the studio:
   ```powershell
   .\.venv\Scripts\python.exe gui.py
   ```
   Or double-click `JaneConverter.exe`.

## Use the Desktop Application

Launch JaneConverter from your Desktop shortcut or run `JaneConverter.exe`.

### 1. Converter Tab (Studio)

1. **Source Media Input**:
   - Paste any streaming link (YouTube, Spotify, SoundCloud, TikTok, Twitter/X, Facebook, Reddit, Twitch, Vimeo, adult tube sites).
   - Or click **Browse** to choose a local audio or video file from your computer.
   - Click **Paste** to paste directly from your clipboard.
2. **Transcode Parameters**:
   - **Mode**: Toggle between **Audio Format** and **Video Format**.
   - **Container Format**: Select MP3, WAV, FLAC, AAC/M4A, or OGG (Audio), or MP4, MKV, WEBM, MOV, GIF (Video).
   - **Quality / Bitrate**: Choose from MP3/AAC bitrates (320 kbps down to 128 kbps), WAV bit depths (16-bit, 24-bit, 32-bit Float), or FLAC lossless resolutions (16-bit, 24-bit).
   - **Sample Rate**: Select CD standard (44.1 kHz), Studio Broadcast (48.0 kHz), or Hi-Res Audio (96.0 kHz).
   - **EBU R128 Normalization**: Enable to automatically normalize tracks to -14 LUFS streaming broadcast loudness.
   - **Hardware Acceleration**: Automatically detects your host GPU and displays the active encoder (e.g. NVIDIA NVENC, AMD AMF, Intel Quick Sync, Apple VideoToolbox).
   - **Cover Art & Metadata**: Toggles for embedding cover artwork and exporting formatted production notes.
3. **Destination Folder**: Choose where converted files are saved (defaults to the `converted` folder beside JaneConverter).
4. **Account Access (optional)**: Click **Create Access Link** when you are authorized to view account-only media. Open the temporary link in the browser whose session you want to use, sign in normally if needed, and confirm access. JaneConverter detects the browser that opened the link and reads that browser session for the current app session. It never asks for your password or writes a cookie file.
5. **Convert & Abort**:
   - Click **CONVERT MEDIA** to begin processing.
   - Click **Abort** at any time to immediately kill the FFmpeg process, stop downloads, and remove partial files.
   - Click **Open Folder** to reveal the export folder and select the most recently exported file in Windows Explorer, Finder, or the system file manager.

### macOS and Linux (experimental)

Install Python 3.10+, FFmpeg with `ffprobe`, and optionally Rust/Cargo for the native frontend. From the JaneConverter folder, run:

```bash
chmod +x install.sh run_converter.sh uninstall.sh
./install.sh
./run_converter.sh
```

The Unix launcher uses the selected frontend preference when available and otherwise starts the legacy Python interface. If an older native binary is found during installation without Cargo available, the installer moves it aside instead of launching it against newer source code. Finder or the default Linux file manager is used for **Open Folder** actions. Hardware acceleration depends on the FFmpeg build and graphics drivers available on the host.

### 2. Playlist Track Selector

When pasting a playlist or album URL (YouTube playlist, Spotify album or playlist, Apple Music album, or SoundCloud set):

1. JaneConverter detects the playlist and offers to open the **Playlist Tracks** catalog window.
2. Inspect the playlist title, total track count, and duration.
3. Use the search bar to filter tracks by title or artist in real time.
4. Use **Select All** or **Deselect All**, or check individual tracks to customize your download.
5. Click **Convert Selected Items** to begin the batch pipeline.

### 3. Converted Library Tab

- Browses the same converted library from the Main UI, Legacy Rust, and Legacy Python interfaces.
- Shows file size, format, organized source location, and available thumbnail or cover art.
- Use **Open folder** for the active export directory or an individual item. **Move library** lets you relocate the shared library without moving files manually.
- The root folder has a disabled Back control so navigation cannot escape the library; **Delete** remains available for files and folders inside it.

### 4. Live Console

- The Main UI and Legacy Rust interface keep conversion progress visible without requiring an external terminal; the Legacy Python interface retains its dedicated Console tab.
- Displays real-time streaming output from the extraction and transcode engine.
- Displays automatic update checks for the underlying extractor engine.
- Displays live CPU, RAM, and GPU telemetry in the top header.
- Includes **Copy Logs** and **Clear** tools.
- Includes **Diagnostics** to copy a safe version and dependency summary for support.

### Authorized browser sessions

Some services require an active account session for private playlists, age-restricted media, or other content the signed-in user is allowed to view. In the Converter tab, click **Create Access Link**. JaneConverter starts a temporary localhost page, copies the link, and opens it in the host's default browser. You may paste that link into any other browser, open the source link there, sign in normally if needed, then click **I'm signed in — confirm access**.

After confirmation, the recommended path is the **JaneConverter Browser Bridge** extension in `browser-extension/`. Load that folder as an unpacked extension in Vivaldi or another Chromium browser, click its toolbar button, and choose **Connect**. The extension asks for permission for the current source origin only, reads the already-authorized session through the browser's cookies API, and sends a source-scoped payload to JaneConverter's loopback server. The browser can stay open, and the payload is kept in memory for the current app session only. No password is requested, no cookies file is exported, and no session data is uploaded.

If the extension is not installed or cannot be used, JaneConverter retains the regular read-only in-memory browser fallback and yt-dlp database fallback. For Chromium browsers, it automatically retries the read-only path for a few seconds. If Windows blocks both paths, fully exit the browser—not just the visible window—so the fallback can run. In Vivaldi on Windows, use **File > Exit** or the full quit shortcut; background browser processes can keep the database locked. Browser sessions do not bypass privacy settings, permissions, DRM, or expired content; if the account cannot access the media, JaneConverter will stop and explain the failure.

#### Installing the Browser Bridge extension

1. Open `vivaldi://extensions` (or the equivalent extensions page in your Chromium browser) and enable **Developer mode**.
2. Choose **Load unpacked** and select JaneConverter's `browser-extension` folder.
3. In JaneConverter, create and confirm the access link, then open the extension from the browser toolbar and click **Connect**.
4. Approve the permission for the source site only. Return to JaneConverter; the account-access status will change to **Bridge connected**.

The extension is intentionally local and source-scoped. It does not run continuously, store cookies, or make the browser session available to other sites.

## Updates, releases, and uninstalling

JaneConverter checks for updates without modifying the running installation. Packaged consumer snapshots query the latest published GitHub release because they do not contain a Git checkout; the Main UI performs this check shortly after launch and Settings can retry it manually. Published ZIP packages include a SHA-256 checksum and can be staged for application on the next restart. A short-lived helper waits for the launcher to exit before applying staged files, so the application never replaces files that it still has open.

To remove JaneConverter's private environment and user data, close the app and run `uninstall.ps1` on Windows or `./uninstall.sh` on macOS/Linux. Exported media is included in the removal, so copy anything you want to keep first.

## Playlist Folder Organization

When exporting playlists or albums, JaneConverter keeps media players and file explorers clean and uncluttered:

```text
JaneConverter\converted\Music\<Source>\<Playlist_Name>\
├── 1. First Track.mp3
├── 2. Second Track.mp3
├── 3. Third Track.mp3
└── metadata/
    ├── 1. First Track.jpg
    ├── 1. First Track_credits.txt
    ├── 2. Second Track.jpg
    ├── 2. Second Track_credits.txt
    ├── 3. Third Track.jpg
    ├── 3. Third Track_credits.txt
    ├── cover.jpg
    ├── manifest.json
    └── playlist_credits.txt
```

- **Clean Media Root**: Media players, car stereos, and DAWs only see sequential audio files (`1. First Track.mp3`, etc.).
- **Metadata stays separate**: Album artwork, credits, and the export manifest remain in `metadata/`, keeping media folders clean.
- **Isolated Metadata**: Every track's full description, credits, lyrics, tags, and individual artwork are stored in the dedicated `metadata/` subfolder.

## Use the Command Line

You can also run conversions directly from PowerShell or Command Prompt:

### Single Track / Video Run

```powershell
\.venv\Scripts\python.exe run_converter.py --source "https://www.youtube.com/watch?v=VIDEO_ID" --format mp3 --bitrate 320k --normalize
```

### Apple Music Song or Album

```powershell
python run_converter.py --source "https://music.apple.com/us/album/ALBUM_SLUG/ALBUM_ID?i=TRACK_ID" --format flac
python run_converter.py --source "https://music.apple.com/us/album/ALBUM_SLUG/ALBUM_ID" --list-playlist
```

Apple Music uses catalog metadata and matching public-source search; it does not directly download subscription audio.

### Spotify Track or Album

```powershell
python run_converter.py --source "https://open.spotify.com/track/TRACK_ID" --format flac
python run_converter.py --source "https://open.spotify.com/album/ALBUM_ID" --format mp3
```

### Local File Conversion

```powershell
\.venv\Scripts\python.exe run_converter.py --source "C:\Music\recording.wav" --format mp3 --bitrate 320k
```

### Command-Line Arguments

| Argument | Description | Default |
|---|---|---|
| `--source URL_OR_PATH` | URL (YouTube, Spotify, etc.) or local file path | Required |
| `--format FMT` | Target format (`mp3`, `wav`, `flac`, `aac`, `m4a`, `ogg`, `mp4`, `mkv`, `webm`, `mov`, `gif`) | `mp3` |
| `--bitrate RATE` | Audio bitrate (`320k`, `256k`, `192k`, `128k`) | `320k` |
| `--sample-rate HZ` | Audio sample rate (`44100`, `48000`, `96000`) | `48000` |
| `--normalize` | Apply EBU R128 loudness normalization (-14 LUFS) | Disabled |
| `--resolution RES` | Video resolution (`original`, `4k`, `1080p`, `720p`, `480p`) | `original` |
| `--no-gpu` | Disable hardware acceleration and use multi-core CPU | Disabled |
| `--no-cover-art` | Skip cover art extraction and embedding | Disabled |
| `--no-metadata` | Skip writing credits and metadata `.txt` files | Disabled |
| `--category` | Library category (`Music`, `Video`, or `Miscellaneous`) | Source-based |
| `--browser-session` | Existing browser session (`none`, `chrome`, `edge`, `firefox`, `brave`, `vivaldi`, `opera`, `chromium`, `safari`) | `none` |
| `--retries` | Retry each failed playlist item (`0`-`5`) | `2` |
| `--output PATH` | Directory to save exported files | JaneConverter `converted/` |
| `--no-update` | Skip real-time extractor engine update check | Disabled |
| `--version` | Print the application version and exit | - |

Run this to see all CLI options:

```powershell
python run_converter.py --help
```

## Audio Engineering & Fidelity Standards

- **Studio PCM WAV (16-Bit / 24-Bit / 32-Bit Float)**: Preserves uncompressed studio audio (`pcm_s16le`, `pcm_s24le`, `pcm_f32le`) up to 32-bit floating point headroom.
- **FLAC Lossless (16-Bit CD / 24-Bit Studio Master)**: Level 8 maximum compression bit-perfect lossless encoding across CD and studio master bit depths.
- **320 kbps MP3**: High-fidelity MP3 using LAME encoder with ID3v2.3 attached picture frames.
- **EBU R128 Loudness Normalization**: Industry standard normalization target (-14 LUFS integrated, -1.5 dB true peak ceiling) ensures consistent volume across tracks without digital clipping.
- **Sample Rate Conversion**: High-quality resampling up to 96.0 kHz studio master quality.

## Privacy and Network Use

- **Local files stay local**: Local conversion does not upload media. Startup update checks are network requests and can be disabled with `--no-update`.
- **Zero API keys required**: Spotify metadata extraction uses public catalog endpoints and OpenGraph information. No Spotify account, developer keys, or logins are needed.
- **Direct stream retrieval**: Media streams are fetched directly from host servers without passing through third-party proxy services.
- **Update checks are read-only**: On launch, JaneConverter may check PyPI and the latest published GitHub release for available updates. It does not install packages, pull Git changes, or replace the launcher automatically. Extractor upgrades are kept within the tested dependency range and application upgrades remain a consent-based release-install step.

## Troubleshooting

### FFmpeg was not found

If FFmpeg is not detected in your system PATH, install it with your operating system's package manager, then restart your terminal. On Windows, use `winget install Gyan.FFmpeg`; on macOS, use `brew install ffmpeg`; on Debian/Ubuntu, use `sudo apt install ffmpeg`. JaneConverter also discovers a local Windows `ffmpeg.exe` build placed beside the application.

### Python runtime was not found

Run `.\setup.bat` in the JaneConverter folder on Windows, or `./install.sh` on macOS/Linux. Alternatively, install Python 3.10+ from [python.org](https://www.python.org/downloads/) or your operating system package manager.

### Windows setup finds Python but `.venv\Scripts\python.exe` is missing

This means setup found a system Python, but the private JaneConverter environment did not finish creating. The current installer checks every `python.exe` and `python3.exe` on PATH, the Windows Python launcher, and registered Python installations, then resolves the actual interpreter path. It also repairs a partial `.venv` before installing dependencies. Re-run the current `setup.bat`; it will not modify your global Python packages.

### Stream extraction fails or YouTube throttles

Make sure you have Node.js installed on your machine (`winget install OpenJS.NodeJS.LTS`). Node.js allows the extractor engine to execute JavaScript signature challenges from YouTube.

### Spotify playlist only loads first 100 tracks

Spotify public embed endpoints limit catalog payloads to the top 100 tracks of any public playlist. For albums or playlists with up to 100 tracks, all tracks are fetched.

## Automated Test Suite

JaneConverter includes a comprehensive test suite covering audio argument generation, metadata tagging, Spotify resolution, playlist ordering, UI components, and abort signals:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -v tests/
```

The offline suite runs in seconds (FFmpeg is required for the end-to-end transcode test). Playlist items are retried twice by default when a provider or FFmpeg operation has a temporary failure; use `--retries 0` to disable this. Nine additional live-network tests are opt-in: `python -m pytest -m online -v`. Continuous integration runs the hermetic suite on Windows, Ubuntu, and macOS; the live-network suite is available through a deliberate workflow dispatch.

## Versioning

The current version is defined in `engine/version.py`, surfaced in the GUI title bar and the CLI `--version` flag, and tagged on GitHub. See `CHANGELOG.md` for release history.

## Legal & Platform Notice

JaneConverter is a personal-use tool. It does not host, proxy, or re-distribute any media; all content is streamed directly from the platforms you point it at. Downloading media from streaming platforms may violate those platforms' Terms of Service, and downloaded material may be protected by copyright. You are responsible for complying with the laws and terms that apply in your jurisdiction and to the content you access. Use JaneConverter only with content you own or have permission to download.

## License

Copyright © 2026 project//aspyr.

JaneConverter is released under the MIT License. See [LICENSE](LICENSE) for the complete terms.
