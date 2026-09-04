"""
Universal Stream Extractor Module for JaneConverter
Fetches media from across the internet (YouTube, SoundCloud, TikTok, Twitter/X,
Facebook, Reddit, Vimeo, Twitch, adult sites, and Spotify metadata matching) or local files.
"""

import os
import re
import urllib.parse
from typing import Optional, Dict, Any, Callable
import json
import requests
import yt_dlp

def is_url(path_or_url: str) -> bool:
    """Checks if input string is a valid HTTP/HTTPS URL."""
    if not isinstance(path_or_url, str):
        return False
    try:
        parsed = urllib.parse.urlparse(path_or_url.strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False

def sanitize_filename(name: str, max_length: int = 100) -> str:
    """Cleans illegal Windows filesystem characters from names."""
    if not name:
        return "media_file"
    cleaned = re.sub(r'[\\/*?:"<>|]', '_', name).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = cleaned.strip(" .")
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip(" .")
    return cleaned or "media_file"

def identify_source_type(url_or_path: str) -> str:
    """Identifies the media source platform or local file status."""
    if not is_url(url_or_path):
        return "local_file"

    url_lower = url_or_path.lower()
    if "spotify.com" in url_lower:
        return "spotify"
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    if "soundcloud.com" in url_lower:
        return "soundcloud"
    if "tiktok.com" in url_lower:
        return "tiktok"
    if "twitter.com" in url_lower or "x.com" in url_lower:
        return "twitter"
    if "facebook.com" in url_lower or "fb.watch" in url_lower:
        return "facebook"
    if "reddit.com" in url_lower:
        return "reddit"
    if "twitch.tv" in url_lower:
        return "twitch"
    return "generic_url"

def is_playlist_url(url_or_path: str) -> bool:
    """
    Checks if a URL points to a playlist, album, or multi-track compilation.
    Supports YouTube playlists, Spotify playlists and albums, SoundCloud sets, and generic playlist endpoints.
    """
    if not is_url(url_or_path):
        return False
    url_lower = url_or_path.lower()
    if "spotify.com" in url_lower and ("/playlist/" in url_lower or "/album/" in url_lower):
        return True
    if ("youtube.com" in url_lower or "youtu.be" in url_lower) and "list=" in url_lower:
        return True
    if "soundcloud.com" in url_lower and "/sets/" in url_lower:
        return True
    if "bandcamp.com" in url_lower and "/album/" in url_lower:
        return True
    if "/playlist/" in url_lower or "/sets/" in url_lower:
        return True
    return False

def format_duration(seconds: int) -> str:
    """Formats duration seconds into mm:ss or hh:mm:ss string."""
    if not seconds or seconds <= 0:
        return "0:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

def resolve_spotify_metadata(spotify_url: str) -> Dict[str, str]:
    """
    Extracts public track title, artist, and album from Spotify via public oEmbed and OpenGraph.
    No API keys or authentication required.
    """
    clean_url = spotify_url.split("?")[0].strip()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    title = "Unknown Track"
    artist = "Unknown Artist"
    album = ""
    thumbnail = ""

    # 1. Try public oEmbed endpoint for exact track title and thumbnail
    try:
        oembed_url = f"https://open.spotify.com/oembed?url={urllib.parse.quote(clean_url)}"
        resp = requests.get(oembed_url, headers=headers, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            title = data.get("title", title)
            thumbnail = data.get("thumbnail_url", "")
    except Exception:
        pass

    # 2. Scrape OpenGraph description for artist name and album
    try:
        page_resp = requests.get(clean_url, headers=headers, timeout=8)
        if page_resp.status_code == 200:
            html = page_resp.text
            # Look for description pattern: <meta property="og:description" content="Artist · Album · Song · Year">
            desc_match = re.search(r'<meta property="og:description" content="([^"]+)"', html)
            if desc_match:
                desc_text = desc_match.group(1)
                parts = [p.strip() for p in re.split(r'[·•|]', desc_text)]
                if parts:
                    artist = parts[0]
                if len(parts) > 1 and "Song" not in parts[1]:
                    album = parts[1]
    except Exception:
        pass

    search_query = f"{artist} - {title} audio" if artist != "Unknown Artist" else f"{title} audio"
    return {
        "title": title,
        "artist": artist,
        "album": album,
        "search_query": search_query,
        "thumbnail": thumbnail
    }

def fetch_media_stream(
    source: str,
    output_dir: str,
    audio_only: bool = False,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> Dict[str, Any]:
    """
    Fetches the media stream from a URL (or validates local file) into output_dir.
    Returns metadata dict with local path, title, artist, and media type.
    """
    os.makedirs(output_dir, exist_ok=True)

    def report(pct: float, msg: str):
        if progress_callback:
            progress_callback(pct, msg)

    source_type = identify_source_type(source)

    # 1. Local File
    if source_type == "local_file":
        if not os.path.exists(source):
            raise FileNotFoundError(f"Local file not found at: '{source}'")
        base = os.path.splitext(os.path.basename(source))[0]
        report(1.0, f"Loaded local file: {os.path.basename(source)}")
        return {
            "media_path": os.path.abspath(source),
            "title": base,
            "artist": "Local Audio",
            "album": "",
            "source_type": "local",
            "is_local": True
        }

    # 2. Spotify Track
    spotify_meta = None
    target_url = source
    if source_type == "spotify":
        report(0.05, "Extracting Spotify track details from public metadata...")
        spotify_meta = resolve_spotify_metadata(source)
        report(0.12, f"Resolved Spotify track: {spotify_meta['artist']} - {spotify_meta['title']}")
        target_url = f"ytsearch1:{spotify_meta['search_query']}"

    # 3. Web Stream Download via yt-dlp
    report(0.15, "Connecting to stream provider and parsing media formats...")

    def progress_hook(d):
        if progress_callback and d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            speed = d.get("speed", 0) or 0
            speed_mb = speed / (1024 * 1024) if speed else 0.0
            percent = (downloaded / total * 100.0) if total > 0 else 0.0
            # Scale download phase from 15% to 75%
            scaled_pct = 0.15 + (percent / 100.0) * 0.60
            report(scaled_pct, f"Downloading stream: {percent:.1f}% ({speed_mb:.1f} MB/s)")
        elif progress_callback and d.get("status") == "finished":
            report(0.75, "Stream download complete. Preparing conversion...")

    format_selector = "bestaudio/best" if audio_only else "bv*[height<=2160]+ba/b[height<=2160]/best"

    ydl_opts = {
        "format": format_selector,
        "outtmpl": os.path.join(output_dir, "%(title).80s_%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "js_runtimes": {"node": {"path": None}},
        "remote_components": ["ejs:github"],
        "progress_hooks": [progress_hook]
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(target_url, download=True)
            if not info:
                raise ValueError("No media stream found for the provided link.")

            if "entries" in info:
                entries = info.get("entries")
                if not entries:
                    raise ValueError("No matching streams returned from search.")
                info = entries[0]

            downloaded_file = ydl.prepare_filename(info)
            if not os.path.exists(downloaded_file):
                base_stem, _ = os.path.splitext(downloaded_file)
                for ext in (".mp4", ".mkv", ".webm", ".m4a", ".mp3", ".opus"):
                    candidate = base_stem + ext
                    if os.path.exists(candidate):
                        downloaded_file = candidate
                        break

            if not os.path.exists(downloaded_file):
                raise FileNotFoundError(f"Downloaded stream file not found at: {downloaded_file}")

            extracted_title = spotify_meta["title"] if spotify_meta else info.get("title", "Media Track")
            extracted_artist = spotify_meta["artist"] if spotify_meta else info.get("uploader", "Unknown Artist")
            extracted_album = spotify_meta["album"] if spotify_meta else ""

            return {
                "media_path": os.path.abspath(downloaded_file),
                "title": extracted_title,
                "artist": extracted_artist,
                "album": extracted_album,
                "duration": info.get("duration", 0),
                "source_type": source_type,
                "is_local": False
            }
    except Exception as e:
        raise RuntimeError(f"Stream extraction failed: {str(e)}") from e

def fetch_playlist_entries(
    url: str,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> Dict[str, Any]:
    """
    Extracts metadata for all tracks or videos in a playlist without downloading media stream files.
    Supports Spotify playlists/albums, YouTube playlists, SoundCloud sets, and generic sources.
    """
    def report(pct: float, msg: str):
        if progress_callback:
            progress_callback(pct, msg)

    source_type = identify_source_type(url)
    clean_url = url.strip()

    # 1. Spotify Playlist or Album via Embed Endpoint
    if source_type == "spotify":
        report(0.1, "Connecting to Spotify public catalog service...")
        m_id = re.search(r'/(playlist|album)/([a-zA-Z0-9]+)', clean_url)
        if not m_id:
            raise ValueError(f"Could not parse Spotify playlist or album ID from: {url}")

        kind, item_id = m_id.groups()
        embed_url = f"https://open.spotify.com/embed/{kind}/{item_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        report(0.3, f"Fetching Spotify {kind} metadata...")
        resp = requests.get(embed_url, headers=headers, timeout=12)
        if resp.status_code != 200:
            raise RuntimeError(f"Spotify embed returned HTTP status {resp.status_code}")

        m_data = re.search(r'<script id="__NEXT_DATA__"[^>]*>([^<]+)</script>', resp.text)
        if not m_data:
            raise RuntimeError("Could not locate Spotify catalog payload in response.")

        try:
            payload = json.loads(m_data.group(1))
            entity = payload.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})
            playlist_title = entity.get("title") or entity.get("name") or f"Spotify {kind.capitalize()}"
            raw_tracks = entity.get("trackList", [])
        except Exception as e:
            raise RuntimeError(f"Failed to parse Spotify catalog data: {e}") from e

        report(0.7, f"Extracting {len(raw_tracks)} tracks from {playlist_title}...")
        entries = []
        for idx, t in enumerate(raw_tracks, 1):
            t_title = t.get("title") or f"Track {idx}"
            t_artist = t.get("subtitle") or ""
            t_dur_ms = t.get("duration", 0) or 0
            t_dur_sec = t_dur_ms // 1000
            uri = t.get("uri", "")
            track_id = uri.split(":")[-1] if uri else ""
            track_url = f"https://open.spotify.com/track/{track_id}" if track_id else f"ytsearch1:{t_artist} - {t_title} audio"

            entries.append({
                "index": idx,
                "title": t_title,
                "artist": t_artist,
                "duration": t_dur_sec,
                "duration_str": format_duration(t_dur_sec),
                "url": track_url,
                "id": track_id
            })

        report(1.0, f"Successfully loaded {len(entries)} items from {playlist_title}.")
        return {
            "playlist_title": playlist_title,
            "source_type": f"spotify_{kind}",
            "total_count": len(entries),
            "entries": entries
        }

    # 2. YouTube, SoundCloud, or Generic Playlists via yt-dlp Flat Extraction
    report(0.1, "Inspecting playlist catalog...")
    ydl_opts = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": False,
        "js_runtimes": {"node": {"path": None}},
        "remote_components": ["ejs:github"]
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            report(0.3, "Extracting playlist index and track listings...")
            info = ydl.extract_info(clean_url, download=False)
            if not info:
                raise ValueError("Could not extract playlist information from URL.")

            playlist_title = info.get("title") or "Playlist"
            raw_entries = info.get("entries") or []

            if not raw_entries and info.get("_type") != "playlist":
                raw_entries = [info]

            report(0.7, f"Processing {len(raw_entries)} entries...")
            entries = []
            for idx, e in enumerate(raw_entries, 1):
                if not e:
                    continue
                t_title = e.get("title") or f"Track {idx}"
                t_artist = e.get("uploader") or e.get("channel") or e.get("artist") or ""
                t_dur_sec = int(e.get("duration") or 0)
                e_url = e.get("url") or ""
                e_id = e.get("id") or ""

                if not e_url or not is_url(e_url):
                    if e_id and ("youtube" in clean_url.lower() or "youtu.be" in clean_url.lower() or "list=" in clean_url.lower()):
                        e_url = f"https://www.youtube.com/watch?v={e_id}"
                    elif e_id:
                        e_url = e_id

                entries.append({
                    "index": idx,
                    "title": t_title,
                    "artist": t_artist,
                    "duration": t_dur_sec,
                    "duration_str": format_duration(t_dur_sec),
                    "url": e_url,
                    "id": e_id
                })

            report(1.0, f"Successfully loaded {len(entries)} items from {playlist_title}.")
            return {
                "playlist_title": playlist_title,
                "source_type": source_type,
                "total_count": len(entries),
                "entries": entries
            }
    except Exception as e:
        raise RuntimeError(f"Playlist extraction failed: {str(e)}") from e

