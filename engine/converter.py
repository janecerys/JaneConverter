"""
Media Converter Engine for JaneConverter
Transcodes media to high-fidelity audio (MP3, WAV, FLAC, AAC, OGG) and video (MP4, MKV, WEBM, MOV, GIF).
Supports NVIDIA NVENC acceleration, EBU R128 loudness normalization, sample rate control,
and metadata tagging.
"""

import os
import sys
import time
import shutil
import threading
import subprocess
from typing import Optional, Dict, Any, Callable

SUPPORTED_AUDIO_FORMATS = {"mp3", "wav", "flac", "aac", "m4a", "ogg"}
SUPPORTED_VIDEO_FORMATS = {"mp4", "mkv", "webm", "mov", "gif"}
VIDEO_QUALITY_SETTINGS = {
    "best": {"crf": 18, "audio_bitrate": "192k", "gif_fps": 30},
    "high": {"crf": 20, "audio_bitrate": "160k", "gif_fps": 24},
    "balanced": {"crf": 23, "audio_bitrate": "128k", "gif_fps": 15},
    "small": {"crf": 28, "audio_bitrate": "96k", "gif_fps": 10},
}

# Industry standard EBU R128 loudness normalization targets
LOUDNORM_FILTER = "loudnorm=I=-14:TP=-1.5:LRA=11"

# Explicit bit-depth selection for lossless containers (no substring sniffing)
WAV_BIT_DEPTH_CODECS = {
    "16": "pcm_s16le", "16-bit": "pcm_s16le", "16bit": "pcm_s16le",
    "32": "pcm_f32le", "32-bit": "pcm_f32le", "32bit": "pcm_f32le",
    "32-bit float": "pcm_f32le", "float": "pcm_f32le",
}
FLAC_BIT_DEPTHS = {
    "16": "s16", "16-bit": "s16", "16bit": "s16",
}
FLAC_DEFAULT_DEPTH = "s32"
WAV_DEFAULT_CODEC = "pcm_s24le"

VAAPI_ENCODER_ARGS = ["-vaapi_device", "/dev/dri/renderD128", "-c:v", "h264_vaapi", "-qp", "23"]

_encoder_cache: Dict[Optional[str], Dict[str, Any]] = {}
_encoder_cache_lock = threading.Lock()

ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(ENGINE_DIR)

def get_ffmpeg_binary() -> str:
    """
    Finds FFmpeg executable in local application root, bin folder, or system PATH.
    """
    candidates = [
        os.path.join(PROJECT_ROOT, "ffmpeg.exe"),
        os.path.join(PROJECT_ROOT, "bin", "ffmpeg.exe"),
        os.path.join(ENGINE_DIR, "ffmpeg.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)

    which_path = shutil.which("ffmpeg")
    if which_path:
        return which_path

    return "ffmpeg"

def get_ffprobe_binary() -> str:
    """
    Finds FFprobe next to the selected FFmpeg binary or on system PATH.
    """
    ffmpeg_bin = get_ffmpeg_binary()
    sibling = os.path.join(os.path.dirname(os.path.abspath(ffmpeg_bin)),
                           "ffprobe" + (".exe" if os.name == "nt" else ""))
    if os.path.isfile(sibling):
        return sibling
    which_path = shutil.which("ffprobe")
    if which_path:
        return which_path
    return "ffprobe"

def probe_media_duration(input_path: str) -> Optional[float]:
    """
    Returns the duration of the media in seconds via ffprobe, or None if it cannot be determined.
    """
    try:
        no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        res = subprocess.run(
            [get_ffprobe_binary(), "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", input_path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=15.0, creationflags=no_window
        )
        if res.returncode == 0 and res.stdout.strip():
            return float(res.stdout.strip())
    except Exception:
        pass
    return None

def get_unique_target_path(directory: str, filename: str) -> str:
    """Appends an incrementing counter if a file already exists to prevent overwriting."""
    base_target = os.path.join(directory, filename)
    if not os.path.exists(base_target):
        return base_target

    stem, ext = os.path.splitext(filename)
    counter = 1
    while True:
        candidate = os.path.join(directory, f"{stem}_{counter}{ext}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1

def get_host_gpus() -> list:
    """
    Discovers all physical and integrated GPUs on the host system.
    Supports Windows (Registry & PowerShell), Linux (lspci / sysfs), and macOS (system_profiler / sysctl).
    """
    gpus = []
    if sys.platform == "win32":
        try:
            import winreg
            key_path = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as k:
                for i in range(20):
                    try:
                        sub_name = winreg.EnumKey(k, i)
                        with winreg.OpenKey(k, sub_name) as sk:
                            try:
                                desc, _ = winreg.QueryValueEx(sk, "DriverDesc")
                                if desc and desc not in gpus:
                                    low = desc.lower()
                                    if not any(v in low for v in ["virtual", "mirage", "remote", "vbox", "parsec", "rdp"]):
                                        gpus.append(desc)
                            except Exception:
                                pass
                    except Exception:
                        break
        except Exception:
            pass

    elif sys.platform.startswith("linux"):
        try:
            no_win = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            res = subprocess.run(["lspci"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2.0, creationflags=no_win)
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    if any(k in line.lower() for k in ["vga", "3d", "display"]):
                        parts = line.split(":", 2)
                        model = parts[-1].strip() if len(parts) >= 3 else line.strip()
                        if model and model not in gpus:
                            gpus.append(model)
        except Exception:
            pass

    elif sys.platform == "darwin":
        try:
            no_win = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            res = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2.0, creationflags=no_win)
            if res.returncode == 0 and "apple" in res.stdout.lower():
                gpus.append(f"{res.stdout.strip()} (GPU)")
        except Exception:
            pass
        if not gpus:
            gpus.append("Apple Silicon GPU")

    return gpus

def get_best_hardware_encoder(preferred_codec: Optional[str] = None) -> Dict[str, Any]:
    """
    Selects the optimal hardware video encoder for the current system (cached per session).
    Supports NVIDIA (NVENC), AMD (AMF/VAAPI), Intel (QSV), Apple (VideoToolbox), and CPU fallback.
    Configured for maximum throughput and parallel hardware saturation.
    """
    cache_key = preferred_codec if preferred_codec else "__auto__"
    with _encoder_cache_lock:
        cached = _encoder_cache.get(cache_key)
    if cached is not None:
        return dict(cached)
    spec = _detect_best_hardware_encoder(preferred_codec)
    with _encoder_cache_lock:
        _encoder_cache[cache_key] = spec
    return dict(spec)

def _detect_best_hardware_encoder(preferred_codec: Optional[str] = None) -> Dict[str, Any]:
    """
    Performs the actual GPU registry walk / platform probe for get_best_hardware_encoder.
    """
    if preferred_codec:
        if preferred_codec == "h264_nvenc":
            return {
                "has_gpu": True, "vendor": "nvidia", "gpu_name": "NVIDIA GPU", "short_name": "NVIDIA",
                "encoder": "h264_nvenc", "encoder_label": "NVIDIA NVENC",
                "args": ["-c:v", "h264_nvenc", "-preset", "p2", "-cq", "23", "-b:v", "0", "-pix_fmt", "yuv420p"]
            }
        elif preferred_codec == "h264_amf":
            return {
                "has_gpu": True, "vendor": "amd", "gpu_name": "AMD Radeon GPU", "short_name": "AMD",
                "encoder": "h264_amf", "encoder_label": "AMD AMF",
                "args": ["-c:v", "h264_amf", "-quality", "speed", "-pix_fmt", "yuv420p"]
            }
        elif preferred_codec == "h264_qsv":
            return {
                "has_gpu": True, "vendor": "intel", "gpu_name": "Intel GPU", "short_name": "Intel",
                "encoder": "h264_qsv", "encoder_label": "Intel Quick Sync",
                "args": ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", "23", "-pix_fmt", "nv12"]
            }
        elif preferred_codec == "h264_videotoolbox":
            return {
                "has_gpu": True, "vendor": "apple", "gpu_name": "Apple Silicon", "short_name": "Apple",
                "encoder": "h264_videotoolbox", "encoder_label": "Apple VideoToolbox",
                "args": ["-c:v", "h264_videotoolbox", "-q:v", "65", "-realtime", "0", "-pix_fmt", "yuv420p"]
            }
        elif preferred_codec == "h264_vaapi":
            return {
                "has_gpu": True, "vendor": "linux_vaapi", "gpu_name": "VAAPI Display", "short_name": "VAAPI",
                "encoder": "h264_vaapi", "encoder_label": "Linux VAAPI",
                "args": list(VAAPI_ENCODER_ARGS)
            }
        elif preferred_codec == "libx264":
            return {
                "has_gpu": False, "vendor": "cpu", "gpu_name": "Multi-Core CPU", "short_name": "CPU Mode",
                "encoder": "libx264", "encoder_label": "CPU Multi-Core",
                "args": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p"]
            }

    gpus = get_host_gpus()
    has_nvidia = any(any(k in g.lower() for k in ["nvidia", "geforce", "quadro", "rtx", "gtx", "tesla"]) for g in gpus)
    has_amd = any(any(k in g.lower() for k in ["amd", "radeon"]) for g in gpus)
    has_intel = any(any(k in g.lower() for k in ["intel", "arc", "iris", "uhd"]) for g in gpus)
    has_apple = (sys.platform == "darwin")

    # Priority 1: NVIDIA GPU (NVENC)
    if has_nvidia:
        gpu_name = next((g for g in gpus if any(k in g.lower() for k in ["nvidia", "geforce", "quadro", "rtx", "gtx", "tesla"])), "NVIDIA GPU")
        short = gpu_name.replace("NVIDIA ", "").replace("GeForce ", "").strip()
        return {
            "has_gpu": True,
            "vendor": "nvidia",
            "gpu_name": gpu_name,
            "short_name": short,
            "encoder": "h264_nvenc",
            "encoder_label": "NVIDIA NVENC",
            "args": ["-c:v", "h264_nvenc", "-preset", "p2", "-cq", "23", "-b:v", "0", "-pix_fmt", "yuv420p"]
        }

    # Priority 2: AMD GPU (AMF on Windows, AMF/VAAPI on Linux)
    if has_amd:
        gpu_name = next((g for g in gpus if any(k in g.lower() for k in ["amd", "radeon"])), "AMD Radeon GPU")
        short = gpu_name.replace("AMD ", "").replace("Radeon(TM) ", "Radeon ").replace("Graphics", "").strip() or "Radeon"
        encoder = "h264_amf" if sys.platform == "win32" else "h264_vaapi"
        label = "AMD AMF" if sys.platform == "win32" else "AMD VAAPI"
        args = ["-c:v", encoder, "-quality", "speed", "-pix_fmt", "yuv420p"] if encoder == "h264_amf" else list(VAAPI_ENCODER_ARGS)
        return {
            "has_gpu": True,
            "vendor": "amd",
            "gpu_name": gpu_name,
            "short_name": short,
            "encoder": encoder,
            "encoder_label": label,
            "args": args
        }

    # Priority 3: Intel GPU (QSV)
    if has_intel:
        gpu_name = next((g for g in gpus if any(k in g.lower() for k in ["intel", "arc", "iris", "uhd"])), "Intel GPU")
        short = gpu_name.replace("Intel(R) ", "").replace("Graphics", "").strip() or "Intel HD/Arc"
        return {
            "has_gpu": True,
            "vendor": "intel",
            "gpu_name": gpu_name,
            "short_name": short,
            "encoder": "h264_qsv",
            "encoder_label": "Intel Quick Sync",
            "args": ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", "23", "-pix_fmt", "nv12"]
        }

    # Priority 4: Apple Silicon / macOS (VideoToolbox)
    if has_apple:
        gpu_name = gpus[0] if gpus else "Apple Silicon GPU"
        short = "Apple M-Series" if "apple" in gpu_name.lower() else "Apple GPU"
        return {
            "has_gpu": True,
            "vendor": "apple",
            "gpu_name": gpu_name,
            "short_name": short,
            "encoder": "h264_videotoolbox",
            "encoder_label": "Apple VideoToolbox",
            "args": ["-c:v", "h264_videotoolbox", "-q:v", "65", "-realtime", "0", "-pix_fmt", "yuv420p"]
        }

    # Priority 5: Linux generic VAAPI
    if sys.platform.startswith("linux") and gpus:
        return {
            "has_gpu": True,
            "vendor": "linux_vaapi",
            "gpu_name": gpus[0],
            "short_name": "VAAPI GPU",
            "encoder": "h264_vaapi",
            "encoder_label": "Linux VAAPI",
            "args": list(VAAPI_ENCODER_ARGS)
        }

    # CPU Fallback
    return {
        "has_gpu": False,
        "vendor": "cpu",
        "gpu_name": "Multi-Core CPU",
        "short_name": "CPU Mode",
        "encoder": "libx264",
        "encoder_label": "CPU Multi-Core",
        "args": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p"]
    }

def build_ffmpeg_args(
    input_path: str,
    output_path: str,
    target_format: str,
    bitrate: str = "320k",
    sample_rate: int = 48000,
    normalize_audio: bool = False,
    resolution: str = "original",
    use_nvenc: bool = True,
    use_gpu: Optional[bool] = None,
    gpu_codec: Optional[str] = None,
    metadata: Optional[Dict[str, str]] = None,
    cover_path: Optional[str] = None,
    fps: Optional[int] = None
) -> list:
    """Constructs command line argument list for FFmpeg transcode, including optional cover art embedding."""
    target_format = target_format.lower().strip(".")
    active_gpu = use_gpu if use_gpu is not None else use_nvenc
    has_valid_cover = bool(cover_path and os.path.exists(cover_path))

    # Determine if target container format supports attached picture stream
    can_embed_art = has_valid_cover and target_format in ("mp3", "flac", "m4a", "aac")

    ffmpeg_bin = get_ffmpeg_binary()
    cmd = [ffmpeg_bin, "-y"]

    # Resolve the encoder once so decode acceleration and encode args stay consistent
    enc_spec = None
    if active_gpu and target_format in SUPPORTED_VIDEO_FORMATS and target_format != "gif":
        enc_spec = get_best_hardware_encoder(preferred_codec=gpu_codec)

    # Peak GPU Acceleration: offload video decoding to GPU silicon when hardware acceleration is
    # active. VAAPI is excluded: it uses software decode plus an explicit hwupload filter below.
    if enc_spec is not None and enc_spec["encoder"] != "h264_vaapi":
        cmd.extend(["-hwaccel", "auto"])

    if can_embed_art:
        cmd.extend(["-thread_queue_size", "1024", "-i", input_path])
        cmd.extend(["-thread_queue_size", "64", "-i", cover_path])
        cmd.extend(["-map", "0:a", "-map", "1:v"])
    else:
        cmd.extend(["-thread_queue_size", "1024", "-i", input_path])

    # Metadata tags
    if metadata:
        for k, v in metadata.items():
            if v:
                cmd.extend(["-metadata", f"{k}={v}"])

    # 1. Audio Conversion
    if target_format in SUPPORTED_AUDIO_FORMATS:
        if not can_embed_art:
            cmd.append("-vn")

        # Audio filters
        audio_filters = []
        if normalize_audio:
            # Industry standard EBU R128 loudness normalization
            audio_filters.append(LOUDNORM_FILTER)

        if audio_filters:
            cmd.extend(["-af", ",".join(audio_filters)])

        if sample_rate:
            cmd.extend(["-ar", str(sample_rate)])

        # Codecs and cover art mapping
        if target_format == "mp3":
            cmd.extend(["-c:a", "libmp3lame", "-b:a", bitrate])
            if can_embed_art:
                cmd.extend([
                    "-c:v", "copy",
                    "-id3v2_version", "3",
                    "-metadata:s:v", "title=Album cover",
                    "-metadata:s:v", "comment=Cover (front)",
                    "-disposition:v", "attached_pic"
                ])
        elif target_format == "wav":
            cmd.extend(["-c:a", WAV_BIT_DEPTH_CODECS.get((bitrate or "").lower(), WAV_DEFAULT_CODEC)])
        elif target_format == "flac":
            depth = FLAC_BIT_DEPTHS.get((bitrate or "").lower(), FLAC_DEFAULT_DEPTH)
            cmd.extend(["-c:a", "flac", "-sample_fmt", depth, "-compression_level", "8"])
            if can_embed_art:
                cmd.extend(["-c:v", "copy", "-disposition:v", "attached_pic"])
        elif target_format in ("aac", "m4a"):
            cmd.extend(["-c:a", "aac", "-b:a", bitrate])
            if can_embed_art:
                cmd.extend(["-c:v", "copy", "-disposition:v", "attached_pic"])
        elif target_format == "ogg":
            ogg_quality = {"q10": "10", "q8": "8", "q6": "6", "q4": "4"}.get(
                (bitrate or "").lower(), "7"
            )
            cmd.extend(["-c:a", "libvorbis", "-q:a", ogg_quality])

    # 2. Video Conversion
    elif target_format in SUPPORTED_VIDEO_FORMATS:
        video_quality = VIDEO_QUALITY_SETTINGS.get(
            (bitrate or "").lower(), VIDEO_QUALITY_SETTINGS["balanced"]
        )
        if target_format == "gif":
            cmd.append("-an")
            cmd.extend(["-loop", "0"])

            gif_fps = fps or video_quality["gif_fps"]
            scale_filter = ""
            res_lower = (resolution or "").lower()
            if "1080" in res_lower:
                scale_filter = "scale=1080:-2:flags=lanczos,"
            elif "720" in res_lower:
                scale_filter = "scale=720:-2:flags=lanczos,"
            elif "480" in res_lower:
                scale_filter = "scale=480:-2:flags=lanczos,"
            elif "360" in res_lower:
                scale_filter = "scale=360:-2:flags=lanczos,"
            elif "240" in res_lower:
                scale_filter = "scale=240:-2:flags=lanczos,"
            elif "original" in res_lower:
                scale_filter = ""
            else:
                scale_filter = "scale=480:-2:flags=lanczos,"

            vf = f"fps={gif_fps},{scale_filter}split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3"
            cmd.extend(["-vf", vf])
        else:
            video_filters = []
            if resolution == "4k":
                video_filters.append("scale=-2:2160")
            elif resolution == "1440p":
                video_filters.append("scale=-2:1440")
            elif resolution == "1080p":
                video_filters.append("scale=-2:1080")
            elif resolution == "720p":
                video_filters.append("scale=-2:720")
            elif resolution == "480p":
                video_filters.append("scale=-2:480")

            audio_filters = []
            if normalize_audio:
                audio_filters.append(LOUDNORM_FILTER)

            if audio_filters:
                cmd.extend(["-af", ",".join(audio_filters)])

            if target_format == "webm":
                cmd.extend([
                    "-c:v", "libvpx-vp9", "-crf", str(video_quality["crf"]),
                    "-b:v", "0", "-c:a", "libopus", "-b:a", video_quality["audio_bitrate"]
                ])
            else:
                if enc_spec is not None:
                    if enc_spec["encoder"] == "h264_vaapi":
                        # Software decode: upload frames to the VAAPI render device before encoding
                        video_filters.append("format=nv12")
                        video_filters.append("hwupload")
                    encoder_args = list(enc_spec["args"])
                    if enc_spec["encoder"] == "h264_nvenc" and "-cq" in encoder_args:
                        encoder_args[encoder_args.index("-cq") + 1] = str(video_quality["crf"])
                    cmd.extend(encoder_args)
                else:
                    cmd.extend([
                        "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", str(video_quality["crf"]), "-pix_fmt", "yuv420p"
                    ])

                cmd.extend([
                    "-c:a", "aac",
                    "-b:a", video_quality["audio_bitrate"]
                ])

            if video_filters:
                cmd.extend(["-vf", ",".join(video_filters)])
    else:
        raise ValueError(f"Unsupported conversion format: '{target_format}'")

    cmd.extend(["-threads", "0"])
    cmd.append(output_path)
    return cmd

def convert_media(
    input_path: str,
    output_dir: str,
    output_filename: str,
    target_format: str,
    bitrate: str = "320k",
    sample_rate: int = 48000,
    normalize_audio: bool = False,
    resolution: str = "original",
    use_nvenc: bool = True,
    use_gpu: Optional[bool] = None,
    gpu_codec: Optional[str] = None,
    metadata: Optional[Dict[str, str]] = None,
    cover_path: Optional[str] = None,
    abort_event: Optional[Any] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    fps: Optional[int] = None
) -> str:
    """
    Transcodes input_path into the specified target format and writes to output_dir.
    Optionally embeds cover art image and tags metadata.
    Automatically handles hardware GPU fallback to multi-core CPU, and cover embedding fallback if needed.
    """
    os.makedirs(output_dir, exist_ok=True)
    target_format = target_format.lower().strip(".")
    active_gpu = use_gpu if use_gpu is not None else use_nvenc
    known_media_exts = {
        ".mp3", ".wav", ".flac", ".aac", ".ogg", ".opus", ".m4a",
        ".mp4", ".mkv", ".mov", ".avi", ".webm", ".wma", ".alac", ".aiff", ".gif"
    }
    raw_stem, raw_ext = os.path.splitext(output_filename)
    if raw_ext.lower() in known_media_exts or raw_ext.lower() == f".{target_format}":
        stem = raw_stem
    else:
        stem = output_filename
    destination_path = get_unique_target_path(output_dir, f"{stem}.{target_format}")

    if abort_event and abort_event.is_set():
        raise KeyboardInterrupt("Conversion aborted by user.")

    ffmpeg_bin = get_ffmpeg_binary()
    if not shutil.which(ffmpeg_bin) and not os.path.isfile(ffmpeg_bin):
        raise FileNotFoundError(
            "FFmpeg executable not found. Please install FFmpeg, add it to PATH, or place ffmpeg.exe in the JaneConverter directory."
        )

    def report(frac: float, msg: str):
        if progress_callback:
            progress_callback(frac, msg)

    report(0.70, f"Transcoding media to {target_format.upper()}...")

    cmd = build_ffmpeg_args(
        input_path=input_path,
        output_path=destination_path,
        target_format=target_format,
        bitrate=bitrate,
        sample_rate=sample_rate,
        normalize_audio=normalize_audio,
        resolution=resolution,
        use_nvenc=active_gpu,
        use_gpu=active_gpu,
        gpu_codec=gpu_codec,
        metadata=metadata,
        cover_path=cover_path,
        fps=fps
    )
    # Request machine-readable progress on stdout (inserted before the output path)
    cmd = cmd[:-1] + ["-progress", "pipe:1", "-nostats"] + [cmd[-1]]

    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=no_window
    )

    stderr_chunks = []

    def read_stderr():
        try:
            stderr_chunks.append(proc.stderr.read())
        except Exception:
            pass

    duration = probe_media_duration(input_path)
    transcode_base, transcode_span = 0.70, 0.25
    last_report_time = [0.0]

    def read_progress():
        try:
            for raw_line in iter(proc.stdout.readline, b""):
                line = raw_line.decode("ascii", errors="ignore").strip()
                if not line or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                if key == "progress" and value == "end":
                    report(transcode_base + transcode_span, "Transcode finishing up...")
                    continue
                if duration and duration > 0 and key in ("out_time_us", "out_time_ms"):
                    try:
                        out_us = float(value)
                    except ValueError:
                        continue
                    frac = max(0.0, min(1.0, out_us / (duration * 1_000_000.0)))
                    now = time.time()
                    if frac > 0 and now - last_report_time[0] >= 0.5:
                        last_report_time[0] = now
                        report(
                            transcode_base + transcode_span * frac,
                            f"Transcoding {target_format.upper()}: {int(frac * 100)}%"
                        )
        except Exception:
            pass

    reader_thread = threading.Thread(target=read_stderr, daemon=True)
    reader_thread.start()
    progress_thread = threading.Thread(target=read_progress, daemon=True)
    progress_thread.start()

    try:
        while proc.poll() is None:
            if abort_event and abort_event.is_set():
                proc.kill()
                proc.wait()
                reader_thread.join(timeout=1.0)
                progress_thread.join(timeout=1.0)
                if os.path.exists(destination_path):
                    try:
                        os.remove(destination_path)
                    except Exception:
                        pass
                raise KeyboardInterrupt("Conversion aborted by user.")
            time.sleep(0.05)

        proc.wait()
        reader_thread.join(timeout=2.0)
        progress_thread.join(timeout=2.0)
        stderr = stderr_chunks[0] if stderr_chunks else b""

        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd, output=b"", stderr=stderr)

    except KeyboardInterrupt:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
            reader_thread.join(timeout=1.0)
            progress_thread.join(timeout=1.0)
        if os.path.exists(destination_path):
            try:
                os.remove(destination_path)
            except Exception:
                pass
        raise

    except subprocess.CalledProcessError as e:
        # Clean up the partial output so retries don't leave orphaned truncated files
        if os.path.exists(destination_path):
            try:
                os.remove(destination_path)
            except Exception:
                pass

        # If hardware GPU transcode failed, retry with multi-core CPU libx264
        if active_gpu and target_format in ("mp4", "mkv", "mov", "webm"):
            report(0.85, "Hardware GPU encoder unavailable or failed, switching to multi-core CPU transcode...")
            return convert_media(
                input_path=input_path,
                output_dir=output_dir,
                output_filename=output_filename,
                target_format=target_format,
                bitrate=bitrate,
                sample_rate=sample_rate,
                normalize_audio=normalize_audio,
                resolution=resolution,
                use_nvenc=False,
                use_gpu=False,
                metadata=metadata,
                cover_path=cover_path,
                abort_event=abort_event,
                progress_callback=progress_callback
            )
        # If cover art embedding failed, retry without cover art
        if cover_path:
            report(0.85, "Cover art embedding encountered an issue, transcoding media directly...")
            return convert_media(
                input_path=input_path,
                output_dir=output_dir,
                output_filename=output_filename,
                target_format=target_format,
                bitrate=bitrate,
                sample_rate=sample_rate,
                normalize_audio=normalize_audio,
                resolution=resolution,
                use_nvenc=active_gpu,
                use_gpu=active_gpu,
                gpu_codec=gpu_codec,
                metadata=metadata,
                cover_path=None,
                abort_event=abort_event,
                progress_callback=progress_callback
            )
        err_detail = e.stderr.decode("utf-8", errors="ignore") if e.stderr else ""
        raise RuntimeError(f"FFmpeg transcode error: {err_detail}") from e

    report(1.0, f"Conversion complete: {os.path.basename(destination_path)}")
    return destination_path
