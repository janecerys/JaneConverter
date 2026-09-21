# JaneConverter Improvement Roadmap

## Product Direction & Core Posture

JaneConverter's primary promise is:

> *I have this media. I need it in another format.*

JaneConverter is an **S-tier consumer-first media converter**. The core engine is already dependable: it converts local files and public URLs without exposing terminal complexity, bundles all necessary runtimes in production packages, embeds metadata and artwork, and respects user privacy.

This roadmap is **not a remediation plan for a broken converter**. It is a strategic evolution focused on:
1. **Defensive hardening & regression protection** for the core conversion pipeline.
2. **Performance optimizations** (conditional instant remuxing, high-throughput extraction).
3. **Consumer workflow polish** (lightweight batch queue, context-aware controls).
4. **The Adaptive "Mahoraga" Story Engine** (a self-correcting, multi-strategy capture architecture for ephemeral social media).

---

## Architectural Principles & Boundaries

- **Pure Media Converter**: Takes media (local disk or web ingestion) and produces clean, playback-ready files in the user's requested container.
- **Not a Transcoder/Encoder Studio**: It is not HandBrake or Shutter Encoder. Quality settings exist because conversion requires choosing an output target, not for configuring matrix transforms or GOP structures.
- **Not a Download Manager**: It is not JDownloader 2. It avoids multi-threaded link crawling and CAPTCHA harvesting bloat.
- **Images are Valid Media**: Modern platforms deliver stills, artwork, and carousel posts alongside audio and video. Image conversion (JPG, PNG, WebP) is a first-class citizen.
- **Story Capture Isolation**: Social platforms deliberately alter DOM structures and CDN tokens. The story engine is treated as an adaptive experimental research module—it must never destabilize or delay core converter releases.
- **Zero-Secret Privacy**: Never dump, log, or persist browser cookies, passwords, session databases, or signed tokens.

---

## Technical Engine Architecture

```
[ Input: URL / Local File / Browser Capture ]
                      │
        ┌─────────────┴─────────────┐
        ▼                           ▼
 [ Local Media ]             [ Web Ingestion ]
        │                           │
        │             ┌─────────────┴─────────────┐
        │             ▼                           ▼
        │     yt-dlp Extractor             Browser Bridge
        │     - Concurrent fragments (4x)  - Current-media direct
        │     - Smart codec sorting        - Adaptive "Mahoraga" Engine
        │     - Anti-throttling heuristics   (Surface → Ladder → Memory)
        │             │                           │
        └─────────────┼───────────────────────────┘
                      ▼
            FFmpeg High-Fidelity Engine
      ┌───────────────────────────────────────────┐
      │ 1. Conditional Stream-Copy Check:         │
      │    (-c copy ONLY if container compatible  │
      │     AND no filters/rescaling/norm active) │
      │ 2. Hardware Acceleration: (NVENC/AMF/QSV) │
      │ 3. Audio Precision: (SoX resampler,       │
      │    explicit 24/32-bit PCM, EBU R128)      │
      │ 4. Image Pipeline: (MJPEG, PNG-9, WebP)   │
      └───────────────────────────────────────────┘
                      ▼
          [ Output Validation & Probe ]
                      ▼
         [ Converted Library & Explorer ]
```

---

## Roadmap Phases

### Phase 0: Baseline & Defensive Protection
*Goal: Lock in current stability with formal matrix documentation and regression fixtures.*

#### Task 1: Define the supported conversion matrix
- Document all valid input $\rightarrow$ output permutations across Audio (`mp3`, `flac`, `wav`, `aac`, `ogg`, `m4a`), Video (`mp4`, `mkv`, `webm`, `mov`, `gif`), and Image (`jpg`, `png`, `webp`).
- Formally document the exact boundary where zero-loss stream copying (`-c copy`) is permitted versus when transcoding is strictly mandatory.
- Define actionable, user-friendly error categories for unsupported conversions.

#### Task 2: Establish the conversion regression baseline
- Maintain local automated fixtures in `tests/` covering sample rates, video aspect ratios, still frames, artwork embedding, and corrupted inputs.
- Ensure all failure paths report clear, stage-specific diagnostics: `InputInvalid`, `ExtractorFailed`, `FFmpegProcessError`, `ValidationFailed`.
- Confirm all existing Python, Rust, and frontend test suites pass before engine refactors.

---

### Phase 1: Performance Optimization & Engine Refinement
*Goal: Accelerate extraction and conversion speed while preserving pristine audio/video fidelity.*

#### Task 3: Transparent FFmpeg & hardware diagnostics
- Maintain explicit runtime health indicators: detect bundled vs. system FFmpeg/FFprobe paths and versions.
- Run a harmless startup probe to discover active GPU encoders (NVIDIA NVENC, AMD AMF, Intel QSV, Linux VAAPI) with CPU fallback.

#### Task 4: High-throughput yt-dlp extraction enhancements
- **Concurrent Ingestion**: Enable `--concurrent-fragments 4` by default to bypass single-stream bandwidth throttling on supported CDNs.
- **Intelligent Format Sorting**: Prioritize cleanest codecs (`bv*[vcodec^=av01]+ba / bv*[vcodec^=vp9]+ba` for video; uncompressed Opus/M4A for audio).
- **Anti-Throttling Heuristics**: Utilize mobile client emulation (`player_client=android,web`) where appropriate to avoid aggressive web-client rate limits.

#### Task 5: High-efficiency, audiophile-grade FFmpeg pipelines
- **Conditional Stream-Copy (`-c copy`)**: Enable instant remuxing *only* when the target container accepts the existing codec AND no rescaling, normalization, filtering, or sample-rate conversions are requested.
- **SoX High-Precision Resampling**: Use `aresample=resampler=soxr:precision=28:cutoff=0.99` for audiophile sample rate changes without aliasing noise or phase distortion.
- **Bit-Depth Precision**: Enforce explicit PCM mapping (`pcm_s16le`, `pcm_s24le`, `pcm_f32le`) for lossless containers.
- **Output Probing**: Enforce post-conversion `ffprobe` verification (confirming readable headers, valid streams, non-zero bytes) before reporting success.

---

### Phase 2: Consumer Workflow Polish
*Goal: Refine everyday user ergonomics without bloating the interface.*

#### Task 6: Lightweight conversion queue
- Allow dragging and dropping a small batch of local files or URLs into a simple conversion queue.
- Apply a single unified preset across the batch while providing per-item progress, cancellation, and retry controls.
- Keep the queue strictly linear and consumer-oriented—avoiding download manager scraping bloat.

#### Task 7: Context-aware media controls & intent presets
- Automatically detect input media type (Audio, Video, Image) and dynamically display only relevant options (hide sample rate for images; hide resolution for audio).
- Provide goal-oriented presets (*"Studio Master (24-bit WAV)"*, *"Universal Compatibility (MP3/MP4)"*, *"High-Efficiency Web (WebP)"*) with technical knobs kept in an accessible Advanced drawer.

#### Task 8: Library completion & post-conversion actions
- Add instantaneous 1-click completion actions: **Open File**, **Open Folder**, **Copy Path**, and **Send to Converter** (for chaining).
- Ensure failed conversions never generate phantom entries in the Converted Library.

---

### Phase 3: The Adaptive "Mahoraga" Story & Browser Capture Engine
*Goal: Transform experimental story capture into an adaptive, multi-strategy orchestrator that overcomes obfuscated DOMs and ephemeral CDNs.*

*(Reference: [`docs/adaptive-story-capture-engine.md`](file:///d:/Documents/GitHub%20Repo/JaneConverter/docs/adaptive-story-capture-engine.md))*

#### Task 9: Story surface detection & candidate scoring
- Identify the active story modal using geometry (full-screen overlays, z-index, viewport-sized containers) and accessibility cues (`next`, `close`, `pause`, progress bars).
- Implement an evidence scoring matrix (+points for active playback, viewport fill, navigation proximity; -points for small avatar dimensions, repeated icons) to eliminate unrelated thumbnails.

#### Task 10: Multi-tier capture strategy ladder
Implement an ordered strategy ladder from least invasive to most approximate:
1. **Direct Media Response**: Validated media URL or response body.
2. **Page-Context Fetch**: Authenticated in-page fetch for approved hosts.
3. **Network Compatibility Capture**: Tab-scoped debugger stream interception.
4. **Rendered Image Capture**: Direct canvas or rendered image surface extraction.
5. **Cropped Visible-Tab Capture**: High-precision boundary crop of the active story rectangle.
6. **Rendered Video Capture**: MediaStream / MediaRecorder fallback for canvas-only video playback.

#### Task 11: Composite story fingerprinting & deduplication
- Generate perceptual composite hashes (surface geometry + media kind + dimensions + duration + visual hash + sequence index) to recognize the same story across rotating CDN tokens and prevent duplicate captures.

#### Task 12: Local adaptation memory & graceful recovery
- Cache successful capture strategies by hostname and layout signature (e.g., `site.com / layout-A -> preferred: page-context fetch`).
- Keep adaptation memory strictly structural: **never** store cookies, credentials, tokens, or private media.
- Ensure that if a strategy fails, the engine automatically steps down the ladder, updates its memory, and recovers without freezing the UI.

---

### Phase 4: Maintenance, Security & Release Hardening
*Goal: Ensure effortless long-term maintenance and verified release integrity.*

#### Task 13: User-initiated engine health checks
- Provide an in-app "Check Engine Health" button in Settings that displays current `yt-dlp` and `ffmpeg` versions.
- Allow user-confirmed, checksum-verified extractor updates with rollback capability, avoiding unpredictable silent background modifications.

#### Task 14: Packaged clean-machine smoke tests
- Automate CI verification ensuring packaged Windows installers and portable archives execute correctly on a fresh OS environment with all bundled runtimes (Python, FFmpeg, FFprobe, Node) fully functional.

---

## Explicit Non-Goals

- Do not turn JaneConverter into a download manager (no multi-threaded link crawlers, no CAPTCHA harvesting).
- Do not expose raw yt-dlp or FFmpeg CLI complexity to ordinary users.
- Do not turn JaneConverter into a video editor or transcoder matrix (HandBrake / Shutter Encoder).
- Do not allow story capture failures to block, freeze, or destabilize the core converter.
- Do not borrow or export browser cookies to disk by default.

---

## Release Gates

A release is validated when:
- [ ] Core local conversion fixture matrix passes across all supported audio, video, and image targets.
- [ ] Conditional stream-copy (`-c copy`) executes instantly when safe and falls back to transcode when filters are active.
- [ ] Every completed conversion is verified via `ffprobe` before showing the completion indicator.
- [ ] The lightweight batch queue handles multi-item local conversions predictably.
- [ ] The Mahoraga story engine runs in its isolated sandbox without leaking errors into ordinary conversion.
- [ ] Packaged application smoke tests pass on a clean Windows machine with bundled runtimes.
