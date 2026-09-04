# JaneConverter ⚡🎵

<p align="center">
  <img src="assets/icon.png" width="128" height="128" alt="JaneConverter Icon" />
</p>

<p align="center">
  <strong>Universal Media Downloader & High-Fidelity Transcode Studio</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-blue?style=flat-square" alt="Platform" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-blueviolet?style=flat-square" alt="Python" />
  <img src="https://img.shields.io/badge/Acceleration-NVIDIA%20NVENC-76B900?style=flat-square" alt="NVIDIA" />
  <img src="https://img.shields.io/badge/Audio-Lossless%20PCM%20%7C%20FLAC%20%7C%20320k%20MP3-orange?style=flat-square" alt="Audio" />
</p>

---

## ⚡ 1-Click Automated Setup

To set up JaneConverter on a Windows computer, open PowerShell or Command Prompt and run:

```powershell
git clone https://github.com/janecerys/JaneConverter.git
cd JaneConverter
.\setup.bat
```

> **What `setup.bat` does automatically:**
> 1. Verifies **Python 3.10+** (installs it via winget if missing).
> 2. Verifies **FFmpeg** and **Node.js** for high-speed transcode and bot challenge solving.
> 3. Installs Python dependencies from `requirements.txt`.
> 4. Compiles the native `JaneConverter.exe` executable with embedded app icon.
> 5. Creates a **JaneConverter** shortcut on your Desktop.
> 6. Launches the studio immediately.

---

## 🎨 Supported Formats & Platforms

### Universal Media Ingestion
- **Streaming Platforms:** YouTube, SoundCloud, TikTok, Twitter/X, Facebook, Reddit, Vimeo, Twitch.
- **Spotify Links:** Automatically resolves track metadata (title, artist, album) and matches the highest-fidelity audio stream from YouTube Music / SoundCloud.
- **Public Video Sites:** Full support for public video tubes and NSFW platforms.
- **Local Files:** Browse and convert any existing `.mp4`, `.mkv`, `.mov`, `.avi`, `.webm`, `.wav`, `.flac`, `.mp3`.

### Export Formats
- **Audio:**
  - **MP3:** 320 kbps (Studio Master), 256 kbps, 192 kbps, 128 kbps
  - **WAV:** 24-bit Lossless Uncompressed PCM
  - **FLAC:** Level 8 Lossless Compression
  - **AAC / M4A:** 320 kbps / 256 kbps High Efficiency
  - **OGG:** Vorbis High Fidelity
- **Video:**
  - **MP4:** NVIDIA NVENC H.264 GPU Accelerated (or CPU libx264 fallback)
  - **MKV / MOV / WEBM:** Multi-track and web standards
  - **GIF:** High-quality palette-mapped animated GIFs
- **Audio Engineering & Metadata Enhancements:**
  - **Sample Rates:** 44.1 kHz, 48.0 kHz (Broadcast), 96.0 kHz (Hi-Res)
  - **Loudness Normalization:** Optional EBU R128 (-14 LUFS Streaming Standard)
  - **Embedded Cover Art:** High-resolution artwork embedded into audio containers (ID3v2.3 attached pictures for MP3, FLAC, M4A)
  - **Artwork on Disk:** Saves cover art as `{Title}.jpg` or `cover.jpg` for playlists and albums
  - **Full Production Credits (.txt):** Exports formatted `{Title}_credits.txt` with title, artist, album, track, release year, duration, source link, tags, and complete description
  - **Ordered Playlist Export:** Downloads playlists into dedicated folders with sequential track numbering (1. Song, 2. Song, etc.)

---

## 💻 Running from Source

```bash
python gui.py
```

### CLI Batch Conversion
```bash
python run_converter.py --source "https://www.youtube.com/watch?v=..." --format mp3 --bitrate 320k --normalize
python run_converter.py --source "https://open.spotify.com/playlist/..." --format flac
```

### Running Automated Tests
```powershell
pytest -v tests/
```

---

## 📄 License
Private and Proprietary. Created by Jane Cerys.
