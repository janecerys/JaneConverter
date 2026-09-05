"""
Media Converter Engine for JaneConverter
Transcodes media to high-fidelity audio (MP3, WAV, FLAC, AAC, OGG) and video (MP4, MKV, WEBM, MOV, GIF).
Supports NVIDIA NVENC acceleration, EBU R128 loudness normalization, sample rate control,
and metadata tagging.
"""

import os
import sys
import re
import time
import shutil
import threading
import subprocess
from typing import Optional, Dict, Any, Callable

SUPPORTED_AUDIO_FORMATS = {"mp3", "wav", "flac", "aac", "m4a", "ogg"}
SUPPORTED_VIDEO_FORMATS = {"mp4", "mkv", "webm", "mov", "gif"}

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
    Selects the optimal hardware video encoder for the current system.
    Supports NVIDIA (NVENC), AMD (AMF/VAAPI), Intel (QSV), Apple (VideoToolbox), and CPU fallback.
    Configured for maximum throughput and parallel hardware saturation.
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
                "args": ["-c:v", "h264_vaapi", "-qp", "23"]
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
        args = ["-c:v", encoder, "-quality", "speed", "-pix_fmt", "yuv420p"] if encoder == "h264_amf" else ["-c:v", encoder, "-qp", "23"]
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
            "args": ["-c:v", "h264_vaapi", "-qp", "23"]
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
    cover_path: Optional[str] = None
) -> list:
    """Constructs command line argument list for FFmpeg transcode, including optional cover art embedding."""
    target_format = target_format.lower().strip(".")
    active_gpu = use_gpu if use_gpu is not None else use_nvenc
    has_valid_cover = bool(cover_path and os.path.exists(cover_path))

    # Determine if target container format supports attached picture stream
    can_embed_art = has_valid_cover and target_format in ("mp3", "flac", "m4a", "aac")

    ffmpeg_bin = get_ffmpeg_binary()
    cmd = [ffmpeg_bin, "-y"]

    # Peak GPU Acceleration: offload video decoding to GPU silicon when hardware acceleration is active
    if active_gpu and target_format in SUPPORTED_VIDEO_FORMATS and target_format != "gif":
        cmd.extend(["-hwaccel", "auto"])

    # Multi-core thread scaling and input queue buffering for peak throughput
    cmd.extend(["-threads", "0", "-thread_queue_size", "1024"])

    if can_embed_art:
        cmd.extend(["-i", input_path, "-i", cover_path, "-map", "0:a", "-map", "1:v"])
    else:
        cmd.extend(["-i", input_path])

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
            audio_filters.append("loudnorm=I=-14:TP=-1.5:LRA=11")

        if audio_filters:
            cmd.extend(["-af", ",".join(audio_filters)])

        if sample_rate and target_format not in ("flac",):
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
            cmd.extend(["-c:a", "pcm_s24le"])
        elif target_format == "flac":
            cmd.extend(["-c:a", "flac", "-compression_level", "8"])
            if can_embed_art:
                cmd.extend(["-c:v", "copy", "-disposition:v", "attached_pic"])
        elif target_format in ("aac", "m4a"):
            cmd.extend(["-c:a", "aac", "-b:a", bitrate])
            if can_embed_art:
                cmd.extend(["-c:v", "copy", "-disposition:v", "attached_pic"])
        elif target_format == "ogg":
            cmd.extend(["-c:a", "libvorbis", "-q:a", "7"])

    # 2. Video Conversion
    elif target_format in SUPPORTED_VIDEO_FORMATS:
        if target_format == "gif":
            vf = "fps=15,scale=480:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
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

            if video_filters:
                cmd.extend(["-vf", ",".join(video_filters)])

            audio_filters = []
            if normalize_audio:
                audio_filters.append("loudnorm=I=-14:TP=-1.5:LRA=11")

            if audio_filters:
                cmd.extend(["-af", ",".join(audio_filters)])

            if target_format == "webm":
                cmd.extend(["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0", "-c:a", "libopus", "-b:a", "160k"])
            else:
                if active_gpu:
                    enc_spec = get_best_hardware_encoder(preferred_codec=gpu_codec)
                    cmd.extend(enc_spec["args"])
                else:
                    cmd.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p"])

                cmd.extend([
                    "-c:a", "aac",
                    "-b:a", "192k"
                ])
    else:
        raise ValueError(f"Unsupported conversion format: '{target_format}'")

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
    progress_callback: Optional[Callable[[float, str], None]] = None
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
        ".mp4", ".mkv", ".mov", ".avi", ".webm", ".wma", ".alac", ".aiff"
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

    report(0.80, f"Transcoding media to {target_format.upper()}...")

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
        cover_path=cover_path
    )

    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        creationflags=no_window
    )

    stderr_chunks = []

    def read_stderr():
        try:
            stderr_chunks.append(proc.stderr.read())
        except Exception:
            pass

    reader_thread = threading.Thread(target=read_stderr, daemon=True)
    reader_thread.start()

    try:
        while proc.poll() is None:
            if abort_event and abort_event.is_set():
                proc.kill()
                proc.wait()
                reader_thread.join(timeout=1.0)
                if os.path.exists(destination_path):
                    try:
                        os.remove(destination_path)
                    except Exception:
                        pass
                raise KeyboardInterrupt("Conversion aborted by user.")
            time.sleep(0.05)

        proc.wait()
        reader_thread.join(timeout=2.0)
        stderr = stderr_chunks[0] if stderr_chunks else b""

        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd, output=b"", stderr=stderr)

    except KeyboardInterrupt:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
            reader_thread.join(timeout=1.0)
        if os.path.exists(destination_path):
            try:
                os.remove(destination_path)
            except Exception:
                pass
        raise

    except subprocess.CalledProcessError as e:
        # If hardware GPU transcode failed, retry with multi-core CPU libx264
        if active_gpu and target_format in ("mp4", "mkv", "mov"):
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
        err_detail = e.stderr.decode("utf-8", errors="ignore")
        raise RuntimeError(f"FFmpeg transcode error: {err_detail}") from e

    report(1.0, f"Conversion complete: {os.path.basename(destination_path)}")
    return destination_path
