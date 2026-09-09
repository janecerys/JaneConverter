# JaneConverter

<p align="center">
  <img src="assets/icon.png" width="128" height="128" alt="JaneConverter application icon" />
</p>

<p align="center">
  <strong>Universal Media Downloader & High-Fidelity Transcode Studio</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-blue?style=flat-square" alt="Platform" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-blueviolet?style=flat-square" alt="Python" />
  <img src="https://img.shields.io/badge/Acceleration-Universal%20GPU%20(NVENC%20%2F%20AMF%20%2F%20QSV)-success?style=flat-square" alt="Hardware Acceleration" />
  <img src="https://img.shields.io/badge/Audio-24--bit%20WAV%20%7C%20FLAC%20%7C%20320k%20MP3-orange?style=flat-square" alt="Audio" />
</p>

JaneConverter downloads media from virtually any online source, matches high-resolution metadata and album cover art, normalizes audio to streaming broadcast standards, and transcodes files into studio-grade audio or hardware-accelerated video formats.

The standard way to use JaneConverter is its modern dark-themed desktop studio application. A complete command-line interface is also available for automated workflows and terminal users.

JaneConverter runs from a private Python environment with a native launcher executable (`JaneConverter.exe`) and an automated 1-click Windows setup script. Update checks are read-only and never patch the running installation silently.

## What it does

For each media link or local file, JaneConverter:

1. **Analyzes the source**: Identifies whether the input is a single video, audio stream, public Spotify link, playlist, or local disk file.
2. **Extracts public metadata**: For Spotify tracks or albums, resolves the official title, artist, album, release year, and high-resolution cover art without requiring user logins or API keys.
3. **Retrieves the stream**: Automatically queries the highest-fidelity audio or video stream from YouTube, SoundCloud, TikTok, Twitter/X, Reddit, Vimeo, Facebook, Twitch, or supported adult streaming platforms.
4. **Normalizes loudness**: Optionally applies industry-standard EBU R128 loudness normalization (-14 LUFS integrated, -1.5 dB true peak) to match commercial streaming broadcast loudness without clipping.
5. **Embeds artwork and tags**: Attaches front cover art directly into ID3v2.3 (MP3), FLAC, and M4A containers, and exports formatted production credits files (`_credits.txt`).
6. **Transcodes media**: Converts audio into 320 kbps MP3, 24-bit PCM WAV, FLAC Level 8, AAC/M4A, or OGG, or video into MP4/MKV via universal hardware acceleration (NVIDIA NVENC, AMD AMF, Intel QuickSync, Apple VideoToolbox, Linux VAAPI, or multi-core CPU threading).
7. **Organizes exports**: Saves regular media under `Music/<Source>/` or `Videos/<Source>/`, puts general-purpose material under `Miscellaneous/Audio/` or `Miscellaneous/Videos/`, and keeps metadata in collision-safe `metadata/` subfolders.

## Before you install

You need:

- A 64-bit computer running **Windows 10** or **Windows 11**.
- **Python 3.10 or newer** (automatically verified and installed by `setup.bat`).
- **FFmpeg** with `ffprobe` (automatically verified and installed by `setup.bat`).
- Available disk space for downloaded media and high-resolution audio exports.

Hardware acceleration:
- **Universal GPU Support**: Automatically detects NVIDIA (NVENC with p2 high-performance preset), AMD (AMF speed preset), Intel (Quick Sync / QSV), Apple Silicon (VideoToolbox), and Linux (VAAPI).
- **Full Hardware Pipeline**: Automatically offloads both hardware decoding (`-hwaccel auto`) and video encoding to your host GPU silicon.
- **Multi-Core Threading**: Automatically configures FFmpeg (`-threads 0`, `-thread_queue_size 1024`) to utilize all available CPU threads for peak throughput when processing media.
- **Zero Configuration Fallback**: If GPU encoding is unavailable or unsupported on a given system, JaneConverter seamlessly falls back to multi-core CPU encoding (`libx264`) without interrupting your queue.

Node.js is optional but recommended when fetching YouTube media, as it enables the extraction engine to solve current YouTube signature challenges.

## Installation & Setup

### 1-Click Automated Setup (Recommended)

Clone this repository or extract the downloaded ZIP folder, open PowerShell or Command Prompt in the `JaneConverter` folder, and run:

```powershell
.\setup.bat
```

What `setup.bat` does automatically:
1. Verifies **Python 3.10+** (installs it via winget if missing).
2. Verifies **FFmpeg** (installs it via winget if missing).
3. Verifies **Node.js** for YouTube bot challenge handling.
4. Creates a private `.venv` and installs all required Python dependencies from `requirements.txt` without changing the user's global Python environment.
5. Compiles the native `JaneConverter.exe` executable with embedded app icon.
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
3. **Destination Folder**: Choose where converted files are saved (defaults to JaneConverter's writable user data folder).
4. **Convert & Abort**:
   - Click **CONVERT MEDIA** to begin processing.
   - Click **Abort** at any time to immediately kill the FFmpeg process, stop downloads, and remove partial files.
   - Click **Open Folder** to reveal the export folder and select the most recently exported file in Windows Explorer.

### 2. Playlist Track Selector

When pasting a playlist or album URL (YouTube playlist, Spotify album or playlist, SoundCloud set):

1. JaneConverter detects the playlist and offers to open the **Playlist Tracks** catalog window.
2. Inspect the playlist title, total track count, and duration.
3. Use the search bar to filter tracks by title or artist in real time.
4. Use **Select All** or **Deselect All**, or check individual tracks to customize your download.
5. Click **Convert Selected Items** to begin the batch pipeline.

### 3. Converted Library Tab

- Lists all exported audio and video files organized by date.
- Shows file size, format, and its organized source location.
- Click **Folder** to open the specific output location.
- Click **Delete** to remove files you no longer need.

### 4. Console Tab

- Displays real-time streaming output from the extraction and transcode engine.
- Displays automatic update checks for the underlying extractor engine.
- Displays live CPU, RAM, and GPU telemetry in the top header.
- Includes **Copy Logs** and **Clear** tools.

## Playlist Folder Organization

When exporting playlists or albums, JaneConverter keeps media players and file explorers clean and uncluttered:

```text
%LOCALAPPDATA%\JaneConverter\converted\Music\<Source>\<Playlist_Name>\
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
| `--format FMT` | Target format (`mp3`, `wav`, `flac`, `aac`, `ogg`, `mp4`, `mkv`, `webm`, `gif`) | `mp3` |
| `--bitrate RATE` | Audio bitrate (`320k`, `256k`, `192k`, `128k`) | `320k` |
| `--sample-rate HZ` | Audio sample rate (`44100`, `48000`, `96000`) | `48000` |
| `--normalize` | Apply EBU R128 loudness normalization (-14 LUFS) | Disabled |
| `--resolution RES` | Video resolution (`original`, `4k`, `1080p`, `720p`, `480p`) | `original` |
| `--no-gpu` | Disable hardware acceleration and use multi-core CPU | Disabled |
| `--no-cover-art` | Skip cover art extraction and embedding | Disabled |
| `--no-metadata` | Skip writing credits and metadata `.txt` files | Disabled |
| `--category` | Library category (`Music`, `Video`, or `Miscellaneous`) | Source-based |
| `--output PATH` | Directory to save exported files | User data `converted/` |
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
- **Update checks are read-only**: On launch, JaneConverter may check PyPI and the application repository for available updates. It does not install packages, pull Git changes, or replace the launcher automatically.

## Troubleshooting

### FFmpeg was not found

If FFmpeg is not detected in your system PATH, you can either:
1. Run `winget install Gyan.FFmpeg` in PowerShell, then restart your terminal.
2. Or download a static build of `ffmpeg.exe` from [ffmpeg.org](https://ffmpeg.org/) and place `ffmpeg.exe` directly inside the `JaneConverter` folder. JaneConverter will discover it automatically.

### Python runtime was not found

Run `.\setup.bat` in the JaneConverter folder. It will detect your missing runtime and install Python automatically via Winget. Alternatively, install Python 3.10+ from [python.org](https://www.python.org/downloads/) and make sure to check **Add Python to PATH** during installation.

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

The 58 hermetic tests run offline in seconds (FFmpeg required for the end-to-end transcode test). Eight additional live-network tests are opt-in: `python -m pytest -m online -v`. Continuous integration runs both suites on Windows and Ubuntu via GitHub Actions on every push.

## Versioning

The current version is defined in `engine/version.py`, surfaced in the GUI title bar and the CLI `--version` flag, and tagged on GitHub. See `CHANGELOG.md` for release history.

## Legal & Platform Notice

JaneConverter is a personal-use tool. It does not host, proxy, or re-distribute any media; all content is streamed directly from the platforms you point it at. Downloading media from streaming platforms may violate those platforms' Terms of Service, and downloaded material may be protected by copyright. You are responsible for complying with the laws and terms that apply in your jurisdiction and to the content you access. Use JaneConverter only with content you own or have permission to download.

## License

Copyright © 2026 project//aspyr.

JaneConverter is released under the MIT License. See [LICENSE](LICENSE) for the complete terms.
