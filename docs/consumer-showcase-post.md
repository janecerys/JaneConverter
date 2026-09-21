# Introducing JaneConverter 2.0: The Studio-Grade Universal Media Converter for Creators and Audiophiles

*Engineered by Jane Cerys ([project//aspyr](https://github.com/janecerys))*

---

## The Pitch: Why Another Media Converter?

If you work with audio, video, or web media in 2026, you know the frustration of modern converters:

1. **Ad-Riddled Web Converters**: Upload limits capped at 50MB–100MB, endless captcha walls, shady popups, privacy vulnerabilities, and compressed lossy audio that ruins your master tracks.
2. **Bulky Open-Source Workhorses (HandBrake, Shutter Encoder)**: Industrial engineering interfaces covered in dozens of confusing bitrate sliders, codec dropdowns, and GOP structure menus that overwhelm anyone who just wants clean, pristine media.
3. **Pure Command-Line Utilities (FFmpeg, yt-dlp)**: Incomparably powerful, but demanding strict terminal syntax, command memorization, and manual script maintenance.

**JaneConverter was built to bridge this divide.**

It combines the raw processing power and surgical precision of an audio engineer’s terminal setup with a sleek, fluid, and intuitive desktop app built on **Tauri v2, Rust, and React 19**. Whether you are an audio producer rendering 24-bit studio masters, an editor extracting video clips, or a regular user wanting your playlists archived in lossless FLAC, JaneConverter delivers professional results in one click—with zero bloat and 100% local privacy.

---

## Key Highlights: What Makes JaneConverter S-Tier?

### 1. Studio-Grade Audiophile Pipelines
Most consumer converters cut corners during sample rate conversion and volume adjustment, causing harmonic distortion and phase smear. JaneConverter implements professional mastering standards out of the box:
- **High-Precision SoX Resampler (`soxr`)**: Bit-depth upsampling and downsampling configured with `precision=28` and `cutoff=0.99` for mathematically transparent audio preservation.
- **EBU R128 Loudness Normalization**: Industry-standard dual-pass audio leveling targeting `-14 LUFS` and `-1 dBFS` true peak—ensuring consistent, distortion-free playback across Spotify, YouTube, and mobile players.
- **True 24-bit / 32-bit Float PCM Support**: Pristine uncompressed audio export for DAW compatibility without truncation noise.

### 2. Instant Zero-Loss Remuxing (`-c copy`)
Why waste CPU cycles and degrade visual quality re-encoding a video file when both formats use the same underlying codec?
- When you convert compatible containers (e.g., an MKV with AAC audio to MP4, or web media to native streams), JaneConverter automatically engages **Stream Copy mode**.
- Converts multi-gigabyte video files in **seconds** without recompression artifacts or generational loss.
- **Defensive Guardrails**: If you enable audio normalization, sample rate conversion, or video scaling, the engine automatically and seamlessly routes to high-efficiency hardware transcoding (NVENC, AMF, QSV) or multi-core CPU encoding.

### 3. Strict Verification: No More 0-Byte False Positives
We have all experienced a converter that says "Done 100%" only to leave behind a 0-byte corrupt file. JaneConverter solves this with automated post-conversion validation:
- Inspects container headers and verifies media streams with `ffprobe` JSON analysis before declaring a conversion successful.
- Proactively flags corrupt inputs or incomplete downloads with actionable, human-readable error messages.

### 4. 1-Click Intent Presets & Context-Aware UI
Instead of forcing you to decipher complex codec matrices, JaneConverter introduces **Goal-Oriented Presets**:
- 🛡️ **Preserve Quality**: Raw source extraction without re-encoding passes.
- 🎧 **Studio Master**: 32-bit 48kHz uncompressed WAV with SoX precision resampling.
- 🎵 **Universal Music**: Pristine 320 kbps MP3 with EBU R128 broadcast normalization.
- 💎 **Lossless FLAC**: 24-bit compressed archival quality at 48kHz.
- 🎬 **Universal Video**: 1080p Full HD MP4 with hardware acceleration enabled.
- 🖼️ **Lossless Image**: Lossless pixel-for-pixel PNG export.

The interface dynamically adapts its sliders and menus based on whether you are working with **Audio**, **Video**, or **Images**, keeping the workspace clean while tucking power-user parameters inside a collapsible drawer.

### 5. Multi-File Batch Queue with Sequential Protection
Need to convert an entire album or a folder of video clips?
- Select multiple files or drag and drop a batch directly into the app.
- Watch individual, real-time progress bars, cancel individual jobs, or retry failed items on the fly.
- Sequential job runner prevents resource exhaustion, preventing your computer from freezing during heavy exports.

### 6. Privacy-Preserving Browser Bridge & Fetched Media
JaneConverter includes an optional companion browser extension designed for content creators archiving their own media:
- **Zero Credential Sharing**: Unlike sketchy cloud scrapers or unsafe scripts, JaneConverter **never** exports your login cookies, session tokens, or private browsing history.
- The browser fetches only the approved raw media stream and hands the binary bytes locally to your desktop JaneConverter app.
- Saved media appears directly in the **Fetched Media** gallery, ready to be previewed, organized, or converted with a single click.

### 7. Transparent Diagnostics & Zero Silent Updates
- **Runtime Readiness Panel**: Instant visual status of your local Python environment, FFmpeg installation, and detected GPU acceleration hardware (NVENC / AMF / QSV).
- **User-Directed Relaunches & Updates**: Nothing is ever downloaded or installed in the background without your explicit permission. You own your software.

---

## Walkthrough & Demo Script: How to Operate JaneConverter

Use this step-by-step recording script to showcase JaneConverter's capabilities on video or in a live demonstration:

### Scene 1: Welcome & Interface Overview
- **Visual**: Launch JaneConverter. Show the deep dark mode interface with neon purple/cyan accents and smooth typography.
- **Action**: Navigate to the **Settings** tab.
- **Talking Point**: *"Here in the Settings panel, JaneConverter immediately reports system health: Python is ready, FFmpeg is active, and our RTX 5060 NVENC GPU encoder is detected and ready for hardware acceleration. All processing happens 100% locally on your machine."*

### Scene 2: 1-Click Single Conversion with Intent Presets
- **Visual**: Click back to the **Converter** tab.
- **Action**: Click **Browse** and select an uncompressed audio file or video file.
- **Demonstration**: Notice how the UI immediately identifies the file type and configures the appropriate options.
- **Action**: Click the **Studio Master (WAV)** or **Universal Music (MP3)** intent preset button at the top.
- **Action**: Click **Convert**.
- **Result**: Watch the smooth progress bar. Within seconds, a success banner appears with action buttons: **Open File**, **Show in Folder**, **Copy Path**, and **Use as Source**.
- **Talking Point**: *"With one click, JaneConverter applied studio-grade SoX resampling, calibrated loudness, and validated the output stream headers. You can open the file or open the folder immediately from the completion banner."*

### Scene 3: Multi-File Batch Processing
- **Visual**: In the Converter tab, click **Select multiple files**.
- **Action**: Select 4–5 different files (e.g., songs or video clips).
- **Result**: The Batch Conversion Queue unfolds, showing all queued items with pending badges.
- **Action**: Click **Convert All**.
- **Talking Point**: *"JaneConverter processes batch queues sequentially to keep your system responsive. Each file shows its own live progress bar, with instant cancel and retry controls."*

### Scene 4: Stream Copy Remuxing (Zero-Loss Conversion)
- **Visual**: Select a high-resolution video file (e.g., an `.mkv` container).
- **Action**: Set the output format to `.mp4` and select **Stream Copy (Instant Remux)** or leave quality at Balanced without filters.
- **Action**: Click **Convert**.
- **Result**: The conversion completes almost instantly (1–2 seconds for a multi-gigabyte file).
- **Talking Point**: *"Notice how fast that finished! Because the video and audio streams were already compatible, JaneConverter bypassed the re-encoding step entirely. It remuxed the container with zero quality loss and zero heat."*

### Scene 5: Authenticated Browser Media & Fetched Gallery
- **Visual**: Open a browser tab with the JaneConverter Browser Bridge.
- **Action**: Click **Capture current media**.
- **Visual**: Switch back to JaneConverter desktop app and click **Fetched Media**.
- **Result**: The captured clip appears in the visual media grid with its title, thumbnail, and file size.
- **Action**: Click **Convert** directly on the card to send it to the converter engine.
- **Talking Point**: *"No cookies or passwords ever left the browser. JaneConverter received only the raw media bytes and placed it right into your library, ready for editing or conversion."*

---

## Supported Formats Matrix

| Category | Input Formats | Output Formats | Primary Engine Features |
| :--- | :--- | :--- | :--- |
| **Audio** | MP3, WAV, FLAC, M4A, AAC, OGG, OPUS, AIFF, WMA, ALAC | MP3, WAV, FLAC, M4A, OGG, OPUS | 64-bit SoX resampler, EBU R128 normalization (`-14 LUFS`), 24/32-bit linear PCM, instant remuxing |
| **Video** | MP4, MKV, WEBM, MOV, AVI, WMV, FLV, TS, M4V | MP4, MKV, WEBM, MOV, GIF | Hardware GPU encoding (NVENC/AMF/QSV), zero-loss container remuxing, high-framerate GIF optimization |
| **Image** | JPG, PNG, WEBP, BMP, TIFF, GIF, ICO, AVIF | JPG, PNG, WEBP, BMP, TIFF, ICO | Lossless PNG compression, high-efficiency WebP, format auto-scaling |
| **Online / Web** | YouTube, Vimeo, Bandcamp, Soundcloud, Direct Streams | Extracted Audio / Video streams | yt-dlp multi-fragment parallel downloads, anti-throttling mobile client heuristics |

---

## Download & Getting Started

JaneConverter is available as a standalone desktop application for Windows, with macOS and Linux support coming soon.

- **GitHub Repository**: [github.com/janecerys/JaneConverter](https://github.com/janecerys/JaneConverter)
- **Direct Installer**: Check the [Releases](https://github.com/janecerys/JaneConverter/releases) page for the latest `.msi` and portable `.zip` distributions.
- **Open Source & Extensible**: Built with Tauri 2, Rust, React 19, and Python 3.12.

*Crafted with passion for sound clarity and creator independence.*
