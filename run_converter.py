"""
Main Pipeline Runner and CLI Driver for JaneConverter
Orchestrates stream fetching, Spotify resolution, and FFmpeg transcode.
"""

import os
import sys
import re
import uuid
import shutil
import argparse
from typing import Optional, Dict, Any, Callable

if sys.stdout is not None and hasattr(sys.stdout, "encoding") and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONVERTED_DIR = os.path.join(BASE_DIR, "converted")
DEFAULT_TEMP_DIR = os.path.join(BASE_DIR, "temp")

from engine.extractor import (
    is_url, sanitize_filename, fetch_media_stream, identify_source_type,
    is_playlist_url, fetch_playlist_entries, download_and_convert_thumbnail, format_duration
)
from engine.converter import convert_media, SUPPORTED_AUDIO_FORMATS, SUPPORTED_VIDEO_FORMATS
from engine.updater import update_engine

def write_credits_file(output_path: str, meta: Dict[str, Any]) -> str:
    """
    Writes a formatted, human-readable credits and metadata file.
    """
    title = meta.get("title", "Unknown Title")
    artist = meta.get("artist", "Unknown Artist")
    album = meta.get("album", "")
    track = meta.get("track", "")
    year = meta.get("year", "")
    source_url = meta.get("source_url", "") or meta.get("webpage_url", "")
    platform = meta.get("platform", "") or meta.get("source_type", "")
    dur_val = meta.get("duration", 0)
    dur_str = meta.get("duration_str", "") or (format_duration(dur_val) if dur_val else "")
    description = meta.get("description", "").strip()
    tags = meta.get("tags", [])
    categories = meta.get("categories", [])

    lines = [
        "=" * 80,
        "JANECONVERTER - MEDIA CREDITS & METADATA",
        "=" * 80,
        f"Title:        {title}",
        f"Artist:       {artist}",
    ]
    if album:
        lines.append(f"Album:        {album}")
    if track:
        lines.append(f"Track:        {track}")
    if year:
        lines.append(f"Release Date: {year}")
    if dur_str:
        lines.append(f"Duration:     {dur_str}")
    if platform:
        lines.append(f"Platform:     {platform.replace('_', ' ').title()}")
    if source_url:
        lines.append(f"Source URL:   {source_url}")

    if description:
        lines.extend([
            "",
            "-" * 80,
            "CREDITS & DESCRIPTION",
            "-" * 80,
            description
        ])

    if tags or categories:
        lines.extend([
            "",
            "-" * 80,
            "TAGS & CATEGORIES",
            "-" * 80
        ])
        if tags:
            tag_str = ", ".join(tags) if isinstance(tags, list) else str(tags)
            lines.append(f"Tags:       {tag_str}")
        if categories:
            cat_str = ", ".join(categories) if isinstance(categories, list) else str(categories)
            lines.append(f"Categories: {cat_str}")

    lines.extend([
        "=" * 80,
        ""
    ])

    content = "\n".join(lines)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path

def process_conversion(
    source: str,
    output_dir: Optional[str] = None,
    target_format: str = "mp3",
    bitrate: str = "320k",
    sample_rate: int = 48000,
    normalize_audio: bool = False,
    resolution: str = "original",
    use_nvenc: bool = True,
    save_cover_art: bool = True,
    save_metadata: bool = True,
    keep_temp: bool = False,
    check_updates: bool = True,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> str:
    """
    Orchestrates downloading/extracting stream, embedding cover art, exporting credits,
    and transcoding into the desired format.
    """
    if check_updates:
        update_engine(status_callback=lambda m: print(f"[AutoUpdate] {m}"))

    if not output_dir:
        output_dir = DEFAULT_CONVERTED_DIR
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(DEFAULT_TEMP_DIR, exist_ok=True)

    def report(pct: float, msg: str):
        if progress_callback:
            progress_callback(pct, msg)
        print(f"[{int(pct * 100)}%] {msg}")

    target_format = target_format.lower().strip(".")
    is_audio_target = target_format in SUPPORTED_AUDIO_FORMATS

    job_id = uuid.uuid4().hex[:8]
    work_dir = os.path.join(DEFAULT_TEMP_DIR, f"job_{job_id}")
    os.makedirs(work_dir, exist_ok=True)

    print("=" * 60)
    print(f"[*] JANECONVERTER PIPELINE")
    print(f"Source: {source}")
    print(f"Target Format: {target_format.upper()}")
    print(f"Output Directory: {output_dir}")
    print(f"Hardware NVENC: {use_nvenc}")
    print(f"Cover Art: {save_cover_art} | Metadata: {save_metadata}")
    print("=" * 60)

    try:
        # Stage 1: Stream Extraction or File Ingestion
        report(0.05, f"Analyzing source link and fetching media stream...")
        stream_info = fetch_media_stream(
            source=source,
            output_dir=work_dir,
            audio_only=is_audio_target,
            progress_callback=report
        )

        input_media = stream_info["media_path"]
        title = stream_info.get("title", "converted_media")
        safe_title = sanitize_filename(title)
        artist = stream_info.get("artist", "")
        album = stream_info.get("album", "")
        year = stream_info.get("year", "")
        description = stream_info.get("description", "")
        cover_path = stream_info.get("thumbnail_path")

        # Save standalone cover art image if requested
        if save_cover_art and cover_path and os.path.exists(cover_path):
            standalone_cover = os.path.join(output_dir, f"{safe_title}.jpg")
            try:
                shutil.copy2(cover_path, standalone_cover)
                print(f"[+] Saved cover art: {os.path.basename(standalone_cover)}")
            except Exception as e:
                print(f"[!] Warning copying cover art: {e}")

        # Save standalone credits / metadata text file if requested
        if save_metadata:
            credits_file = os.path.join(output_dir, f"{safe_title}_credits.txt")
            try:
                write_credits_file(credits_file, stream_info)
                print(f"[+] Saved credits: {os.path.basename(credits_file)}")
            except Exception as e:
                print(f"[!] Warning writing credits file: {e}")

        metadata = {
            "title": title,
            "artist": artist,
            "album": album
        }
        if year:
            metadata["date"] = year
        if description:
            metadata["comment"] = description[:1000]

        # Stage 2: Conversion & Transcode
        report(0.78, f"Transcoding '{safe_title}' to {target_format.upper()}...")
        result_path = convert_media(
            input_path=input_media,
            output_dir=output_dir,
            output_filename=safe_title,
            target_format=target_format,
            bitrate=bitrate,
            sample_rate=sample_rate,
            normalize_audio=normalize_audio,
            resolution=resolution,
            use_nvenc=use_nvenc,
            metadata=metadata,
            cover_path=cover_path if save_cover_art else None,
            progress_callback=report
        )

        report(1.0, f"Ready! File exported to: {os.path.basename(result_path)}")
        print("\n" + "=" * 60)
        print(f"DONE! Exported: {os.path.abspath(result_path)}")
        print("=" * 60)
        return result_path

    finally:
        if not keep_temp and os.path.exists(work_dir):
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
            except Exception:
                pass

def process_playlist_conversion(
    playlist_title: str,
    selected_entries: list,
    output_dir: Optional[str] = None,
    target_format: str = "mp3",
    bitrate: str = "320k",
    sample_rate: int = 48000,
    normalize_audio: bool = False,
    resolution: str = "original",
    use_nvenc: bool = True,
    save_cover_art: bool = True,
    save_metadata: bool = True,
    keep_temp: bool = False,
    check_updates: bool = True,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> Dict[str, Any]:
    """
    Batch-downloads and transcodes selected playlist items into a dedicated playlist folder.
    Embeds cover art, writes credits files, and names output files strictly by playlist order.
    """
    if check_updates:
        update_engine(status_callback=lambda m: print(f"[AutoUpdate] {m}"))

    if not output_dir:
        output_dir = DEFAULT_CONVERTED_DIR

    safe_folder = sanitize_filename(playlist_title) or "Playlist_Media"
    playlist_dir = os.path.join(output_dir, safe_folder)
    metadata_dir = os.path.join(playlist_dir, "metadata")
    os.makedirs(playlist_dir, exist_ok=True)
    os.makedirs(DEFAULT_TEMP_DIR, exist_ok=True)
    if save_metadata or save_cover_art:
        os.makedirs(metadata_dir, exist_ok=True)

    target_format = target_format.lower().strip(".")
    is_audio_target = target_format in SUPPORTED_AUDIO_FORMATS

    total_items = len(selected_entries)
    if total_items == 0:
        raise ValueError("No playlist items selected for conversion.")

    def report_overall(frac: float, msg: str):
        if progress_callback:
            progress_callback(frac, msg)
        print(f"[{int(frac * 100)}%] {msg}")

    print("=" * 60)
    print(f"[*] JANECONVERTER PLAYLIST BATCH PIPELINE")
    print(f"Playlist: {playlist_title}")
    print(f"Selected Items: {total_items}")
    print(f"Target Directory: {playlist_dir}")
    print(f"Format: {target_format.upper()}")
    print(f"Cover Art: {save_cover_art} | Metadata: {save_metadata}")
    print("=" * 60)

    # Pre-fetch album / playlist cover art if available
    playlist_cover_dest = os.path.join(playlist_dir, "cover.jpg")
    if save_cover_art and not os.path.exists(playlist_cover_dest):
        first_thumb = next((e.get("thumbnail") for e in selected_entries if e.get("thumbnail")), None)
        if first_thumb:
            download_and_convert_thumbnail(first_thumb, playlist_cover_dest)
            meta_cover_copy = os.path.join(metadata_dir, "cover.jpg")
            try:
                shutil.copy2(playlist_cover_dest, meta_cover_copy)
            except Exception:
                pass

    converted_files = []
    failed_files = []

    for i, entry in enumerate(selected_entries):
        idx = entry.get("index", i + 1)
        raw_title = entry.get("title", f"Track_{idx}")
        artist = entry.get("artist", "")
        item_url = entry.get("url", "")

        # Clean any preexisting numeric prefixes to guarantee clean '1. Song1' format
        clean_title = re.sub(r'^\d+[\.\s\-_]+\s*', '', sanitize_filename(raw_title)).strip()
        if not clean_title:
            clean_title = sanitize_filename(raw_title)

        ordered_filename = f"{idx}. {clean_title}"
        base_pct = i / total_items
        slice_pct = 1.0 / total_items

        def item_progress_hook(sub_frac: float, sub_msg: str):
            scaled_pct = base_pct + (sub_frac * slice_pct)
            report_overall(scaled_pct, f"[{i+1}/{total_items}] #{idx}: {clean_title} ({int(sub_frac * 100)}%)")

        report_overall(base_pct, f"[{i+1}/{total_items}] Fetching #{idx}: {clean_title}...")

        track_job_id = uuid.uuid4().hex[:8]
        track_work_dir = os.path.join(DEFAULT_TEMP_DIR, f"track_{track_job_id}")
        os.makedirs(track_work_dir, exist_ok=True)

        try:
            stream_info = fetch_media_stream(
                source=item_url,
                output_dir=track_work_dir,
                audio_only=is_audio_target,
                fallback_title=raw_title,
                fallback_artist=artist,
                progress_callback=item_progress_hook
            )

            input_media = stream_info["media_path"]
            track_artist = artist or stream_info.get("artist", "")
            track_cover = stream_info.get("thumbnail_path") or (playlist_cover_dest if os.path.exists(playlist_cover_dest) else None)

            # Save per-track cover image into metadata folder if desired
            if save_cover_art and stream_info.get("thumbnail_path"):
                track_jpg = os.path.join(metadata_dir, f"{ordered_filename}.jpg")
                try:
                    shutil.copy2(stream_info["thumbnail_path"], track_jpg)
                except Exception:
                    pass
                if not os.path.exists(playlist_cover_dest):
                    try:
                        shutil.copy2(stream_info["thumbnail_path"], playlist_cover_dest)
                    except Exception:
                        pass

            # Save per-track credits / description into metadata folder if available
            if save_metadata and stream_info.get("description"):
                track_credits = os.path.join(metadata_dir, f"{ordered_filename}_credits.txt")
                try:
                    write_credits_file(track_credits, stream_info)
                except Exception:
                    pass

            metadata = {
                "title": clean_title,
                "artist": track_artist,
                "album": playlist_title,
                "track": f"{idx}"
            }
            if stream_info.get("year"):
                metadata["date"] = stream_info["year"]
            if stream_info.get("description"):
                metadata["comment"] = stream_info["description"][:1000]

            result_path = convert_media(
                input_path=input_media,
                output_dir=playlist_dir,
                output_filename=ordered_filename,
                target_format=target_format,
                bitrate=bitrate,
                sample_rate=sample_rate,
                normalize_audio=normalize_audio,
                resolution=resolution,
                use_nvenc=use_nvenc,
                metadata=metadata,
                cover_path=track_cover if save_cover_art else None,
                progress_callback=item_progress_hook
            )

            converted_files.append(result_path)
            print(f"[+] Converted: {os.path.basename(result_path)}")

        except Exception as e:
            failed_files.append({"index": idx, "title": raw_title, "error": str(e)})
            print(f"[!] Error converting track #{idx} '{raw_title}': {e}")
        finally:
            if not keep_temp and os.path.exists(track_work_dir):
                try:
                    shutil.rmtree(track_work_dir, ignore_errors=True)
                except Exception:
                    pass

    # Save overall playlist credits index inside metadata folder
    if save_metadata:
        summary_credits_path = os.path.join(metadata_dir, "playlist_credits.txt")
        try:
            pl_lines = [
                "=" * 80,
                f"PLAYLIST: {playlist_title}",
                "=" * 80,
                f"Total Tracks Converted: {len(converted_files)} / {total_items}",
                f"Format: {target_format.upper()} | Bitrate: {bitrate}",
                "-" * 80,
                "TRACK LISTING:",
                "-" * 80
            ]
            for e in selected_entries:
                idx = e.get("index", "?")
                t_tit = e.get("title", "Track")
                t_art = e.get("artist", "")
                t_dur = e.get("duration_str", "")
                pl_lines.append(f"{idx}. {t_tit} - {t_art} ({t_dur})")
            pl_lines.extend(["=" * 80, ""])
            with open(summary_credits_path, "w", encoding="utf-8") as f:
                f.write("\n".join(pl_lines))
            print(f"[+] Exported playlist summary: {os.path.basename(summary_credits_path)}")
        except Exception:
            pass

    report_overall(1.0, f"Completed playlist! {len(converted_files)}/{total_items} tracks converted.")
    print("=" * 60)
    print(f"PLAYLIST SUMMARY: {len(converted_files)} succeeded, {len(failed_files)} failed.")
    print(f"Export Directory: {playlist_dir}")
    print("=" * 60)

    return {
        "playlist_dir": playlist_dir,
        "metadata_dir": metadata_dir,
        "total_selected": total_items,
        "successful_count": len(converted_files),
        "failed_count": len(failed_files),
        "converted_files": converted_files,
        "failed_files": failed_files
    }

def main():
    parser = argparse.ArgumentParser(description="JaneConverter: Universal Media Downloader & Converter")
    parser.add_argument("--source", "-s", required=True, help="Media URL (YouTube, Spotify, SoundCloud, TikTok, Twitter, etc.) or local file path")
    parser.add_argument("--format", "-f", default="mp3", help="Target output format (mp3, wav, flac, aac, mp4, mkv, gif)")
    parser.add_argument("--output", "-o", default=DEFAULT_CONVERTED_DIR, help="Destination directory for converted files")
    parser.add_argument("--bitrate", "-b", default="320k", help="Audio bitrate (320k, 256k, 192k, 128k)")
    parser.add_argument("--sample-rate", "-r", type=int, default=48000, help="Audio sample rate in Hz (44100, 48000, 96000)")
    parser.add_argument("--normalize", "-n", action="store_true", help="Apply EBU R128 loudness normalization")
    parser.add_argument("--resolution", default="original", help="Video resolution (original, 4k, 1440p, 1080p, 720p, 480p)")
    parser.add_argument("--no-nvenc", action="store_true", help="Disable NVIDIA NVENC GPU acceleration (use CPU libx264)")
    parser.add_argument("--keep-temp", action="store_true", help="Keep intermediate downloaded stream files in temp directory")
    parser.add_argument("--playlist", "-p", action="store_true", help="Force treat input source as playlist")
    parser.add_argument("--no-cover-art", action="store_true", help="Disable downloading and embedding cover art")
    parser.add_argument("--no-metadata", action="store_true", help="Disable exporting credits and metadata text files")

    args = parser.parse_args()

    save_cover = not args.no_cover_art
    save_meta = not args.no_metadata

    if args.playlist or is_playlist_url(args.source):
        print(f"[*] Detected playlist source. Fetching items...")
        pdata = fetch_playlist_entries(args.source)
        print(f"[*] Found {len(pdata['entries'])} tracks in '{pdata['playlist_title']}'. Converting all...")
        process_playlist_conversion(
            playlist_title=pdata["playlist_title"],
            selected_entries=pdata["entries"],
            output_dir=args.output,
            target_format=args.format,
            bitrate=args.bitrate,
            sample_rate=args.sample_rate,
            normalize_audio=args.normalize,
            resolution=args.resolution,
            use_nvenc=not args.no_nvenc,
            save_cover_art=save_cover,
            save_metadata=save_meta,
            keep_temp=args.keep_temp
        )
    else:
        process_conversion(
            source=args.source,
            output_dir=args.output,
            target_format=args.format,
            bitrate=args.bitrate,
            sample_rate=args.sample_rate,
            normalize_audio=args.normalize,
            resolution=args.resolution,
            use_nvenc=not args.no_nvenc,
            save_cover_art=save_cover,
            save_metadata=save_meta,
            keep_temp=args.keep_temp
        )

if __name__ == "__main__":
    main()
