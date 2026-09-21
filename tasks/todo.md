# JaneConverter Roadmap Task List

## Phase 0: Baseline & Defensive Protection

- [x] Task 1: Define the supported conversion matrix (explicit boundary for stream-copy vs transcode)
- [x] Task 2: Establish the conversion regression baseline (fixtures for audio, video, images, corrupted inputs)

### Checkpoint: Baseline & Regression
- [x] Supported conversion matrix documented & approved
- [x] All existing test suites pass (Python, Rust, and frontend unit tests)
- [x] Conversion failure paths map cleanly to specific stages (`InputInvalid`, `ExtractorFailed`, `FFmpegProcessError`, `ValidationFailed`)

---

## Phase 1: Performance Optimization & Engine Refinement

- [x] Task 3: Transparent FFmpeg & hardware diagnostics (startup health check & GPU encoder probe)
- [x] Task 4: High-throughput yt-dlp extraction enhancements (concurrent fragments, format sorting, anti-throttling heuristics)
- [x] Task 5: High-efficiency, audiophile-grade FFmpeg pipelines (conditional `-c copy`, SoX resampling, bit-depth precision, `ffprobe` output validation)

### Checkpoint: Engine Optimization
- [x] Stream-copy (`-c copy`) executes instantly when safe, and reliably transcodes when filters/resampling are active
- [x] Post-conversion `ffprobe` verification eliminates false-positive completions
- [x] SoX high-precision resampling and explicit 24-bit PCM depth active for lossless audio
- [x] Hardware GPU encoders (NVENC, AMF, QSV, VAAPI) discoverable with multi-core CPU fallback

---

## Phase 2: Consumer Workflow Polish

- [x] Task 6: Lightweight conversion queue (drag-and-drop batch conversions with per-item progress and retry)
- [x] Task 7: Context-aware media controls & intent presets (dynamic Audio/Video/Image UI, plain-English goals)
- [x] Task 8: Library completion & post-conversion actions (1-click Open File, Open Folder, Copy Path, Send to Converter)

### Checkpoint: Consumer Workflow
- [x] Non-technical user can process single files or small batches effortlessly
- [x] UI dynamically adapts controls to the active media type without visual clutter
- [x] Converted files are immediately discoverable and accessible

---

## Phase 3: The Adaptive "Mahoraga" Story & Browser Capture Engine

- [x] Task 9: Story surface detection & candidate scoring (modal geometry + accessibility signals + evidence weighting)
- [x] Task 10: Multi-tier capture strategy ladder (Direct → Page fetch → Network → Canvas → Tab crop → MediaRecorder)
- [ ] Task 11: Composite story fingerprinting & deduplication (perceptual hashing across rotating CDN tokens)
- [ ] Task 12: Local adaptation memory & graceful recovery (structural layout caching without saving secrets/cookies)

### Checkpoint: Adaptive Story Capture
- [x] Story surface detector successfully isolates story modals from avatar/profile thumbnails
- [x] Strategy ladder falls back smoothly through alternatives upon DOM or delivery changes
- [x] Captured items normalize cleanly into Fetched Media
- [x] Story capture failures remain quarantined and cannot freeze or crash the core converter

---

## Phase 4: Maintenance, Security & Release Hardening

- [x] Task 13: User-initiated engine health checks (in-app version check with verified updates & rollback; no silent auto-updates)
- [x] Task 14: Packaged clean-machine smoke tests (automated CI verification of bundled Python, FFmpeg, and Node on clean OS)

### Final Release Gate
- [x] Core local conversion fixture matrix passes across all supported targets
- [x] Conditional stream-copy and high-fidelity SoX audio processing verified
- [x] Post-conversion `ffprobe` validation prevents false completions
- [x] Lightweight batch queue operates reliably without memory leaks
- [x] Mahoraga story engine adapts across test fixtures without destabilizing the core app
- [x] Packaged Windows installer and portable builds convert cleanly on fresh machines
