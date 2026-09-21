# JaneConverter

<p align="center">
  <img src="assets/icon.png" width="128" height="128" alt="JaneConverter application icon" />
</p>

<p align="center">
  <strong>Universal Media Downloader & High-Fidelity Transcode Studio</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows%2010%2F11%20%7C%20Linux-blue?style=flat-square" alt="Platform" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-blueviolet?style=flat-square" alt="Python" />
  <img src="https://img.shields.io/badge/Acceleration-NVENC%20%7C%20AMF%20%7C%20QSV%20%7C%20VAAPI-success?style=flat-square" alt="Hardware Acceleration" />
  <img src="https://img.shields.io/badge/Audio-WAV%20%7C%20FLAC%20%7C%20MP3-orange?style=flat-square" alt="Audio" />
</p>

JaneConverter downloads and converts media through a Tauri desktop app or Python CLI. It supports playlists, metadata and artwork, loudness normalization, and hardware-accelerated video encoding.

[Latest release](https://github.com/janecerys/JaneConverter/releases/latest) · [Changelog](CHANGELOG.md)

## Features

- MP3, WAV, FLAC, AAC/M4A, OGG, MP4, MKV, WEBM, MOV, and GIF output
- Playlist selection and organized media libraries
- Metadata, cover art, credits, and EBU R128 normalization
- NVIDIA NVENC, AMD AMF, Intel QSV, and Linux VAAPI acceleration with CPU fallback
- Public Spotify and Apple Music metadata matching
- Authorized browser-session support without exported cookie files

## Install

Download the matching artifact from the [latest release](https://github.com/janecerys/JaneConverter/releases/latest):

- Windows x64 installer: `JaneConverter-<version>-windows-x64-setup.exe`
- Windows x64 portable: `JaneConverter-<version>-windows-x64-portable.zip`
- Linux x86_64 portable: `JaneConverter-<version>-linux-x86_64.tar.gz`

Python, FFmpeg, FFprobe, and Node.js are bundled. Windows requires WebView2. Linux requires WebKitGTK 4.1 and standard GTK desktop libraries.

Each artifact includes a `.sha256` checksum. Verify it with `Get-FileHash <file> -Algorithm SHA256` on Windows or `sha256sum -c <file>.sha256` on Linux.

Launch `JaneConverter.exe` on Windows or `./JaneConverter/JaneConverter` from the extracted Linux archive.

Application data is stored in the OS user-data directory. Set `JANECONVERTER_DATA_DIR` to override it.

## Usage

Paste a supported URL or choose a local file, select the output settings, then start the conversion. The desktop app includes playlist selection, a converted-library browser, live logs, diagnostics, and abort controls.

Spotify and Apple Music links provide public catalog metadata. JaneConverter does not download protected subscription audio directly.

Use **Create Access Link** only for media your signed-in account is authorized to access. The optional [Browser Bridge](browser-extension/README.md) is available to source-checkout users and is not bundled in production packages.

Browser-captured files appear in the **Fetched Media** tab and are saved in the configured fetched-media folder. The default is a etched folder beside the converted library; clearing access ends the browser session without deleting those files. Each item supports **Open file**, **Open path**, **Use for conversion**, and **Discard**. **Capture story sequence** remains experimental because story viewers can change their media identifiers and expose unrelated page assets.

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

Windows x64:

```powershell
.\packaging\build_consumer.ps1 -FFmpegPath C:\tools\ffmpeg.exe -FFprobePath C:\tools\ffprobe.exe -NodePath C:\tools\node.exe
```

Linux x86_64:

```bash
./packaging/build_linux.sh --ffmpeg /opt/ffmpeg/ffmpeg --ffprobe /opt/ffmpeg/ffprobe --node /opt/node/bin/node
```

Tagged `v*` releases are built and published by GitHub Actions. The release workflow uses GPL FFmpeg builds, so distributors must preserve the required notices and satisfy the corresponding source obligations.

## Legal

Use JaneConverter only with content you own or have permission to download. Platform terms and copyright law still apply. Local files remain local; update checks and online extraction make network requests.

Released under the [MIT License](LICENSE). Copyright © 2026 project//aspyr.
