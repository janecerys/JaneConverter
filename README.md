# JaneConverter

<p align="center">
  <img src="assets/icon.png" width="128" height="128" alt="JaneConverter application icon" />
</p>

<p align="center">
  <strong>Universal Media Downloader & High-Fidelity Audio / Video / Image Transcode Studio</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows%2010%2F11%20%7C%20Linux%20%7C%20macOS-blue?style=flat-square" alt="Platform" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-blueviolet?style=flat-square" alt="Python" />
  <img src="https://img.shields.io/badge/Acceleration-NVENC%20%7C%20AMF%20%7C%20QSV%20%7C%20VAAPI-success?style=flat-square" alt="Hardware Acceleration" />
  <br />
  <img src="https://img.shields.io/badge/Audio-WAV%20%7C%20FLAC%20%7C%20MP3%20%7C%20AAC%20%7C%20OGG-orange?style=flat-square" alt="Audio Formats" />
  <img src="https://img.shields.io/badge/Video-MP4%20%7C%20MKV%20%7C%20WebM%20%7C%20MOV%20%7C%20GIF-red?style=flat-square" alt="Video Formats" />
  <img src="https://img.shields.io/badge/Image-PNG%20%7C%20JPG%20%7C%20WebP-green?style=flat-square" alt="Image Formats" />
</p>

JaneConverter downloads and converts media through a sleek Tauri desktop app or high-speed Python CLI. It supports audio, video, and image processing with studio-grade SoX resampling, zero-loss stream copy remuxing (`-c copy`), EBU R128 loudness normalization, and hardware-accelerated GPU encoding.

[Latest release](https://github.com/jeongchaeul/JaneConverter/releases/latest) · [Changelog](CHANGELOG.md)

## Features

- **Comprehensive Multi-Format Processing**:
  - **Audio**: WAV (16/24/32-bit linear PCM), FLAC (lossless archive), MP3 (up to 320 kbps), AAC/M4A, and OGG/Opus.
  - **Video**: MP4, MKV, WebM, MOV, and high-framerate GIF with zero-loss stream copying or hardware GPU transcoding.
  - **Image**: Lossless PNG, high-efficiency WebP, and JPG optimization.
- **Audiophile-Grade Sound Engine**: 64-bit float SoX resampler (`soxr`, precision 28, cutoff 0.99), EBU R128 loudness normalization (`-14 LUFS`), and post-conversion `ffprobe` stream validation to prevent corrupt, 0-byte completions.
- **Instant Stream Copy Remuxing**: Zero-loss container conversion (`-c copy`) when underlying codecs match, with automatic safety fallback to transcode when audio normalization or filters are requested.
- **Drag-and-Drop & Batch Queue**: Drag local media files or web links directly into the converter. Dropping multiple files automatically populates the sequential batch queue with live per-item progress, cancel, and retry controls.
- **1-Click Intent Presets**: Goal-oriented presets including *Preserve Quality (raw stream without re-encoding)*, *Studio Master (32-bit WAV)*, *Universal Music (320k MP3)*, *Lossless FLAC (24-bit)*, *Universal Video (1080p MP4)*, and *Lossless Image (PNG)*. Presets are optional; users can choose **No preset** to customize parameters manually.
- **Hardware Acceleration**: NVIDIA NVENC, AMD AMF, Intel QSV, and Linux VAAPI with multi-core CPU fallback.
- **Online Extraction**: Smart playlist selection, public Spotify & Apple Music metadata matching, and 4x parallel fragment downloading with anti-throttling heuristics.
- **Air-Gapped Browser Bridge**: Optional local companion extension to capture active media from authenticated browser pages without ever exporting or reading cookies, session tokens, or passwords.

## Install

Download the matching artifact from the [latest release](https://github.com/jeongchaeul/JaneConverter/releases/latest):

- Windows x64 installer: `JaneConverter-<version>-windows-x64-setup.exe`
- Windows x64 portable: `JaneConverter-<version>-windows-x64-portable.zip`
- Linux x86_64 portable: `JaneConverter-<version>-linux-x86_64.tar.gz`
- macOS Apple Silicon: `JaneConverter-<version>-macos-arm64.dmg`
- macOS Intel: `JaneConverter-<version>-macos-x86_64.dmg`

Python, FFmpeg, FFprobe, and Node.js are bundled. Windows requires WebView2. Linux requires WebKitGTK 4.1 and standard GTK desktop libraries. macOS builds are architecture-specific, not universal binaries.

Each artifact includes a `.sha256` checksum. Verify it with `Get-FileHash <file> -Algorithm SHA256` on Windows, `sha256sum -c <file>.sha256` on Linux, or `shasum -a 256 -c <file>.sha256` on macOS.

Launch `JaneConverter.exe` on Windows or `./JaneConverter/JaneConverter` from the extracted Linux archive. On macOS, open the DMG and drag JaneConverter to Applications.

The macOS app is only ad-hoc signed, and the DMGs are not Developer ID signed or notarized. Gatekeeper may block the first launch. In Finder, Control-click JaneConverter, choose **Open**, then confirm **Open**. Only bypass the warning after verifying the checksum and release source.

Application data is stored in the OS user-data directory. Set `JANECONVERTER_DATA_DIR` to override it.

## Usage

Paste a supported URL or choose a local file (or drag and drop files / links directly into the source box), select your desired output settings or 1-click preset, then start the conversion. The desktop app includes playlist selection, a sequential batch queue, a converted-library browser, live logs, diagnostics, and instant abort controls.

### Public Facebook photo posts

Paste a public Facebook post link and choose **Download all photos**. JaneConverter reads the post in a separate, hidden temporary guest WebView, collects the photo URLs Facebook renders for logged-out visitors, then passes that short-lived list directly to the local engine. Photos are validated and saved in a grouped folder under `Images/Facebook`, where the library lists image files alongside audio and video. JaneConverter does not use the normal browser profile, a browser extension, saved login cookies, or a remote download service. Facebook page scripts run in the temporary WebView and make the requests needed to display the post. The temporary profile is removed after capture. Posts that require sign-in or do not expose a complete photo set are stopped without saving a partial album.

### Public Instagram and X/Twitter photo posts

Paste a public Instagram post or X/Twitter post link and choose **Download all photos**. JaneConverter uses a separate, hidden temporary guest WebView to collect the photos the post exposes to logged-out visitors, then downloads them locally into grouped folders under `Images/Instagram` or `Images/Twitter`. Instagram carousel slides are opened in sequence. Posts that require sign-in or do not expose photos to logged-out visitors cannot be captured; X/Twitter posts without photos continue through the standard media downloader. No normal browser profile, saved login cookies, browser extension, or remote download service is used.

Spotify and Apple Music links provide public catalog metadata matching. JaneConverter does not download protected DRM-subscription audio directly.

Browser-captured files appear in the **Fetched Media.** tab and are saved in the configured fetched-media folder. The default is a `fetched` folder beside the converted library; clearing access ends the browser session without deleting those files. Each item supports **Open file**, **Open path**, **Use for conversion**, and **Discard**.

## Browser Extension (Local Installation Guide)

The **JaneConverter Browser Bridge** is an optional companion extension that lets you capture active audio and video streams from browser tabs directly into the JaneConverter desktop inbox.

> [!NOTE]
> **Privacy First & Air-Gapped**: The extension is strictly local and runs entirely on your machine. It **never** reads, exports, or stores your cookies, login tokens, browsing history, or passwords. It only forwards direct media stream URLs to your local JaneConverter instance via an authenticated local loopback token.

Because the extension is a local power-user tool and not distributed through the Chrome Web Store or Firefox Add-ons, install it manually in **under 60 seconds**:

### Chromium-Based Browsers (Google Chrome, Microsoft Edge, Brave, Vivaldi, Opera)

1. **Locate the Extension Folder**:
   - In the JaneConverter repository or release package, locate the `browser-extension` folder.
2. **Open Extensions Page**:
   - **Google Chrome**: Navigate to `chrome://extensions`
   - **Microsoft Edge**: Navigate to `edge://extensions`
   - **Brave**: Navigate to `brave://extensions`
   - **Vivaldi**: Navigate to `vivaldi://extensions`
   - **Opera**: Navigate to `opera://extensions`
3. **Enable Developer Mode**:
   - Toggle the **Developer mode** switch (usually in the top-right corner).
4. **Load the Extension**:
   - Click the **Load unpacked** button (top-left).
   - Select the `browser-extension` folder from Step 1.
5. **Pin & Connect**:
   - Pin the JaneConverter icon to your browser extensions toolbar.
   - In the JaneConverter desktop app, click **Create Access Link** on the **Fetched Media.** tab (or go to **Settings** > **Browser Bridge**) to generate a pairing token.
   - Click the extension icon in your browser to complete one-click pairing.
   - Any video or audio stream captured in your browser can now be sent straight to your desktop queue!

## Command line

Source use requires [uv](https://docs.astral.sh/uv/), Python 3.10+, FFmpeg with FFprobe, and Node.js:

```bash
uv sync
uv run janeconverter --source "https://example.com/media" --format mp3
uv run janeconverter --help
```

## Development

Desktop development also requires Rust, npm, and the [Tauri 2 prerequisites](https://v2.tauri.app/start/prerequisites/).

```bash
cd desktop-ui
npm ci
npm run tauri:dev
```

Run the test suites:

```bash
uv sync --locked
uv run pytest tests/ -v
cd desktop-ui
npm test -- --run
cargo test --manifest-path src-tauri/Cargo.toml
```

The Python backend uses the `src/janeconverter/` package. Its supported entry point is the `janeconverter` console command.

## Release builds

`src/janeconverter/version.py` is the canonical application version. Set it and synchronize all desktop metadata with one command:

```bash
uv run --locked python packaging/set_version.py 2.0.1-alpha
```

Run the command without a version to resynchronize from the canonical value, or pass `--check` to verify metadata without writing. The optional Browser Bridge is independently versioned and is not changed by this tool.

Windows x64:

```powershell
.\packaging\build_consumer.ps1 -FFmpegPath C:\tools\ffmpeg.exe -FFprobePath C:\tools\ffprobe.exe -NodePath C:\tools\node.exe
```

Linux x86_64:

```bash
./packaging/build_linux.sh --ffmpeg /opt/ffmpeg/ffmpeg --ffprobe /opt/ffmpeg/ffprobe --node /opt/node/bin/node
```

macOS arm64 or x86_64 must be built natively on the matching architecture. Install Xcode Command Line Tools, Rust, uv, Python 3.12, and Node.js 22, then provide matching-architecture FFmpeg and FFprobe executables:

```bash
./packaging/build_macos.sh --ffmpeg /opt/ffmpeg/ffmpeg --ffprobe /opt/ffmpeg/ffprobe --node "$(command -v node)"
```

Tagged `v*` releases are built and published by GitHub Actions. The release workflow uses GPL FFmpeg builds, so distributors must preserve the required notices and satisfy the corresponding source obligations.

## Legal

Use JaneConverter only with content you own or have permission to download. Platform terms and copyright law still apply. Local files remain local; update checks and online extraction make network requests.

Released under the [MIT License](LICENSE). Copyright © 2026 project//aspyr.
