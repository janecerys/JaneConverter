"""
JaneConverter Desktop Studio GUI
Universal media downloader and transcode studio built with CustomTkinter.
Supports YouTube, SoundCloud, TikTok, Twitter/X, Facebook, Reddit, Twitch, adult sites,
Spotify metadata matching, and local files with NVENC GPU hardware acceleration.
"""

import os
import sys
import time
import queue
import threading
import platform
import subprocess
from typing import Callable, Optional, Dict, Any

import customtkinter as ctk
from PIL import Image
from tkinter import messagebox

try:
    import psutil
except ImportError:
    psutil = None

try:
    import pynvml
    pynvml.nvmlInit()
    nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
except Exception:
    pynvml = None
    nvml_handle = None

# CustomTkinter theme setup
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONVERTED_DIR = os.path.join(BASE_DIR, "converted")
DEFAULT_TEMP_DIR = os.path.join(BASE_DIR, "temp")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
ICON_ICO = os.path.join(ASSETS_DIR, "icon.ico")
ICON_PNG = os.path.join(ASSETS_DIR, "icon.png")

for d in (DEFAULT_CONVERTED_DIR, DEFAULT_TEMP_DIR, ASSETS_DIR):
    os.makedirs(d, exist_ok=True)

from engine.extractor import identify_source_type, is_url, is_playlist_url, fetch_playlist_entries
from engine.converter import (
    SUPPORTED_AUDIO_FORMATS,
    SUPPORTED_VIDEO_FORMATS,
    get_best_hardware_encoder,
    get_host_gpus
)
from engine.updater import (
    update_engine,
    get_current_engine_version,
    check_for_repo_updates,
    check_and_apply_all_updates
)
from run_converter import process_conversion, process_playlist_conversion

THEME = {
    "bg_main": "#02000a",          # Deep space obsidian
    "card_bg": "#090814",          # Glass card surface
    "card_inner": "#0f0e1f",       # Elevated card inner
    "card_border": "#1b192e",      # Subtle border
    "card_border_glow": "#282540", # Focus border
    "magenta": "#e82c75",          # Neon Magenta
    "magenta_hover": "#cf2064",
    "magenta_subtle": "#2e0f1d",
    "cyan": "#3b82f6",             # Electric Cyan / Neon Blue
    "cyan_hover": "#2563eb",
    "cyan_subtle": "#0c1938",
    "yellow": "#facc15",           # Neon Yellow accent
    "text_primary": "#ededed",     # Crisp white
    "text_muted": "#9ca3af",       # Muted zinc
    "text_dark": "#64748b",        # Slate dark
    "input_bg": "#05040d",         # Deep input field
    "success": "#10b981",          # Emerald green
}

def get_system_hardware_info() -> Dict[str, Any]:
    """Dynamically queries host CPU, RAM, and GPU models across NVIDIA, AMD, Intel, and Apple platforms."""
    cpu_name = "Host Processor"
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        val, _ = winreg.QueryValueEx(key, "ProcessorNameString")
        if val and str(val).strip():
            cpu_name = str(val).strip()
    except Exception:
        cpu_name = platform.processor() or "Multi-Core CPU"

    cores = psutil.cpu_count(logical=False) if psutil else 0
    threads = psutil.cpu_count(logical=True) if psutil else 0
    cpu_details = f"{cores} Cores / {threads} Threads" if cores and threads else "Host CPU Architecture"

    total_ram_gb = 16.0
    if psutil:
        try:
            total_ram_gb = psutil.virtual_memory().total / (1024 ** 3)
        except Exception:
            pass

    # Universal GPU and Hardware Acceleration Detection
    enc_info = get_best_hardware_encoder()
    all_gpus = get_host_gpus()
    has_gpu = enc_info.get("has_gpu", False)
    has_nvidia = (enc_info.get("vendor") == "nvidia")
    gpu_model = enc_info.get("gpu_name", "Multi-Core CPU")
    short_gpu = enc_info.get("short_name", "CPU Mode")
    encoder_name = enc_info.get("encoder_label", "CPU Multi-Core")
    encoder_id = enc_info.get("encoder", "libx264")

    # If NVIDIA GPU is present and PyNVML is available, query real-time handle
    if has_nvidia and pynvml and nvml_handle:
        try:
            raw_name = pynvml.nvmlDeviceGetName(nvml_handle)
            if isinstance(raw_name, bytes):
                raw_name = raw_name.decode("utf-8")
            if raw_name:
                gpu_model = raw_name
                short_gpu = raw_name.replace("NVIDIA ", "").replace("GeForce ", "").strip()
        except Exception:
            pass

    return {
        "cpu_name": cpu_name,
        "cpu_details": cpu_details,
        "total_ram_gb": total_ram_gb,
        "gpu_model": gpu_model,
        "short_gpu": short_gpu,
        "has_nvidia": has_nvidia,
        "has_gpu": has_gpu,
        "encoder_name": encoder_name,
        "encoder_id": encoder_id,
        "all_gpus": all_gpus
    }

class StdoutRedirector:
    """Redirects stdout/stderr to a queue for the UI console log, echoing to the original stream."""
    def __init__(self, log_queue: queue.Queue, original=None):
        self.log_queue = log_queue
        self.original = original

    def write(self, text: str):
        if text:
            self.log_queue.put(text)
            if self.original:
                try:
                    self.original.write(text)
                except Exception:
                    pass

    def flush(self):
        if self.original:
            try:
                self.original.flush()
            except Exception:
                pass

class PlaylistSelectionWindow(ctk.CTkToplevel):
    """
    Interactive modal dialog allowing users to inspect playlist tracks,
    filter by title/artist, select or deselect specific items, and initiate batch transcode.
    """
    def __init__(self, parent, playlist_data: Dict[str, Any], on_confirm: Callable[[list, str], None]):
        super().__init__(parent)

        self.playlist_data = playlist_data
        self.on_confirm = on_confirm
        self.entries = playlist_data.get("entries", [])
        self.playlist_title = playlist_data.get("playlist_title", "Playlist")
        self.check_vars = {}
        self.row_widgets = []

        self.title(f"Select Tracks: {self.playlist_title}")
        self.geometry("820x660")
        self.minsize(700, 500)
        self.configure(fg_color=THEME["bg_main"])

        if os.path.exists(ICON_ICO):
            try:
                self.iconbitmap(ICON_ICO)
            except Exception:
                pass

        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._center_window(parent)

    def _center_window(self, parent):
        self.update_idletasks()
        try:
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            w = 820
            h = 660
            x = max(0, px + (pw - w) // 2)
            y = max(0, py + (ph - h) // 2)
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color=THEME["card_bg"], corner_radius=0, height=75)
        header.pack(fill="x", padx=0, pady=(0, 8))
        header.pack_propagate(False)

        h_inner = ctk.CTkFrame(header, fg_color="transparent")
        h_inner.pack(fill="both", expand=True, padx=16, pady=10)

        title_lbl = ctk.CTkLabel(
            h_inner,
            text=f"📑 {self.playlist_title}",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=THEME["text_primary"],
            anchor="w"
        )
        title_lbl.pack(fill="x")

        source_type = self.playlist_data.get("source_type", "web").replace("_", " ").upper()
        total_dur_sec = sum(e.get("duration", 0) for e in self.entries)
        dur_str = ""
        if total_dur_sec > 0:
            m, s = divmod(total_dur_sec, 60)
            h, m = divmod(m, 60)
            dur_str = f" • Approx {h}h {m}m" if h > 0 else f" • Approx {m}m {s}s"

        sub_lbl = ctk.CTkLabel(
            h_inner,
            text=f"{len(self.entries)} tracks found [{source_type}]{dur_str}",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=THEME["magenta"],
            anchor="w"
        )
        sub_lbl.pack(fill="x")

        # Toolbar Card
        toolbar = ctk.CTkFrame(self, fg_color=THEME["card_inner"], corner_radius=8, border_width=1, border_color=THEME["card_border"])
        toolbar.pack(fill="x", padx=14, pady=(0, 8))

        tb_inner = ctk.CTkFrame(toolbar, fg_color="transparent")
        tb_inner.pack(fill="x", padx=10, pady=8)

        self.search_entry = ctk.CTkEntry(
            tb_inner,
            placeholder_text="🔍 Filter tracks...",
            width=220,
            height=30,
            font=ctk.CTkFont(size=11),
            fg_color=THEME["input_bg"],
            border_color=THEME["card_border"],
            border_width=1,
            text_color=THEME["text_primary"]
        )
        self.search_entry.pack(side="left", padx=(0, 10))
        self.search_entry.bind("<KeyRelease>", self._filter_tracks)

        select_all_btn = ctk.CTkButton(
            tb_inner,
            text="Select All",
            width=85,
            height=30,
            fg_color=THEME["input_bg"],
            hover_color=THEME["card_border_glow"],
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._select_all
        )
        select_all_btn.pack(side="left", padx=(0, 6))

        deselect_all_btn = ctk.CTkButton(
            tb_inner,
            text="Deselect All",
            width=95,
            height=30,
            fg_color=THEME["input_bg"],
            hover_color=THEME["card_border_glow"],
            font=ctk.CTkFont(size=11),
            command=self._deselect_all
        )
        deselect_all_btn.pack(side="left", padx=(0, 6))

        invert_btn = ctk.CTkButton(
            tb_inner,
            text="Invert",
            width=70,
            height=30,
            fg_color=THEME["input_bg"],
            hover_color=THEME["card_border_glow"],
            font=ctk.CTkFont(size=11),
            command=self._invert_selection
        )
        invert_btn.pack(side="left", padx=(0, 6))

        self.counter_badge = ctk.CTkLabel(
            tb_inner,
            text=f"Selected: {len(self.entries)} / {len(self.entries)}",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=THEME["cyan"]
        )
        self.counter_badge.pack(side="right", padx=6)

        # Scrollable Track List
        self.scroll_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=THEME["input_bg"],
            border_color=THEME["card_border"],
            border_width=1,
            corner_radius=8
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        for entry in self.entries:
            idx = entry.get("index", 1)
            var = ctk.BooleanVar(value=True)
            self.check_vars[id(entry)] = var

            row = ctk.CTkFrame(self.scroll_frame, fg_color=THEME["card_inner"], corner_radius=6, height=38)
            row.pack(fill="x", padx=2, pady=2)
            row.pack_propagate(False)

            cb = ctk.CTkCheckBox(
                row,
                text="",
                variable=var,
                width=24,
                checkbox_width=18,
                checkbox_height=18,
                fg_color=THEME["magenta"],
                hover_color=THEME["magenta_hover"],
                border_color=THEME["card_border_glow"],
                command=self._update_counter
            )
            cb.pack(side="left", padx=(8, 4))

            idx_badge = ctk.CTkLabel(
                row,
                text=f"#{idx}",
                width=36,
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color=THEME["cyan"],
                fg_color=THEME["cyan_subtle"],
                corner_radius=4
            )
            idx_badge.pack(side="left", padx=(0, 8))

            title_str = entry.get("title", f"Track {idx}")
            t_lbl = ctk.CTkLabel(
                row,
                text=title_str,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=THEME["text_primary"],
                anchor="w"
            )
            t_lbl.pack(side="left", fill="x", expand=True, padx=4)

            artist_str = entry.get("artist", "")
            if artist_str:
                a_lbl = ctk.CTkLabel(
                    row,
                    text=artist_str,
                    font=ctk.CTkFont(family="Segoe UI", size=10),
                    text_color=THEME["text_muted"],
                    anchor="e",
                    width=160
                )
                a_lbl.pack(side="left", padx=6)

            dur_str = entry.get("duration_str", "")
            d_lbl = ctk.CTkLabel(
                row,
                text=dur_str,
                font=ctk.CTkFont(family="Consolas", size=10),
                text_color=THEME["text_dark"],
                width=48
            )
            d_lbl.pack(side="right", padx=(4, 10))

            self.row_widgets.append((row, entry, var))

        # Bottom Action Bar
        bottom_bar = ctk.CTkFrame(self, fg_color=THEME["card_bg"], corner_radius=0, height=58)
        bottom_bar.pack(fill="x", padx=0, pady=0)
        bottom_bar.pack_propagate(False)

        b_inner = ctk.CTkFrame(bottom_bar, fg_color="transparent")
        b_inner.pack(fill="both", expand=True, padx=16, pady=8)

        cancel_btn = ctk.CTkButton(
            b_inner,
            text="Cancel",
            width=90,
            height=38,
            fg_color=THEME["card_inner"],
            hover_color=THEME["card_border_glow"],
            text_color=THEME["text_primary"],
            font=ctk.CTkFont(size=12),
            command=self.destroy
        )
        cancel_btn.pack(side="left")

        self.confirm_btn = ctk.CTkButton(
            b_inner,
            text=f"⚡ CONVERT SELECTED TRACKS ({len(self.entries)} ITEMS)",
            height=38,
            fg_color=THEME["magenta"],
            hover_color=THEME["magenta_hover"],
            text_color="#ffffff",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            corner_radius=8,
            command=self._on_confirm_click
        )
        self.confirm_btn.pack(side="right", fill="x", expand=True, padx=(12, 0))

    def _filter_tracks(self, event=None):
        q = self.search_entry.get().strip().lower()
        for row, entry, _ in self.row_widgets:
            t = entry.get("title", "").lower()
            a = entry.get("artist", "").lower()
            if not q or q in t or q in a:
                row.pack(fill="x", padx=2, pady=2)
            else:
                row.pack_forget()

    def _select_all(self):
        for var in self.check_vars.values():
            var.set(True)
        self._update_counter()

    def _deselect_all(self):
        for var in self.check_vars.values():
            var.set(False)
        self._update_counter()

    def _invert_selection(self):
        for var in self.check_vars.values():
            var.set(not var.get())
        self._update_counter()

    def _update_counter(self):
        sel_count = sum(1 for v in self.check_vars.values() if v.get())
        total = len(self.entries)
        self.counter_badge.configure(text=f"Selected: {sel_count} / {total}")
        self.confirm_btn.configure(text=f"⚡ CONVERT SELECTED TRACKS ({sel_count} ITEMS)")
        if sel_count == 0:
            self.confirm_btn.configure(state="disabled", fg_color=THEME["card_inner"])
        else:
            self.confirm_btn.configure(state="normal", fg_color=THEME["magenta"])

    def _on_confirm_click(self):
        selected = [entry for _, entry, var in self.row_widgets if var.get()]
        if not selected:
            return
        self.destroy()
        self.on_confirm(selected, self.playlist_title)

class JaneConverterApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("JaneConverter - Universal Media Studio")
        self.geometry("1100x820")
        self.minsize(980, 750)
        self.configure(fg_color=THEME["bg_main"])

        # Hardware specs
        self.hw_info = get_system_hardware_info()

        # Taskbar and title bar icon
        if os.path.exists(ICON_ICO):
            try:
                self.iconbitmap(ICON_ICO)
            except Exception:
                pass

        # Windows AppUserModelID for taskbar pinning
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("JaneCerys.JaneConverter.Studio.1.0")
        except Exception:
            pass

        # State tracking
        self.log_queue = queue.Queue()
        self.ui_queue = queue.Queue()
        self.is_converting = False
        self.abort_requested = threading.Event()
        self.start_conversion_time = 0
        self.last_converted_file = None

        # Clean up stale temp directories from previous sessions
        self._cleanup_stale_temp()

        # Build Interface
        self._build_header()
        self._build_tabs()
        self._build_studio_tab()
        self._build_library_tab()
        self._build_console_tab()

        # Start telemetry and logging threads
        self._start_log_listener()
        self._start_ui_pump()
        self._start_hardware_monitor()
        self._start_engine_auto_updater()

        # Install the console redirector once, process-wide, so worker threads never
        # race on swapping sys.stdout/sys.stderr.
        sys.stdout = StdoutRedirector(self.log_queue, sys.stdout)
        sys.stderr = StdoutRedirector(self.log_queue, sys.stderr)

        # Handle clean window close and terminate process
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _post_ui(self, fn):
        """Thread-safe way for worker threads to run a callable on the UI thread."""
        self.ui_queue.put(fn)

    def _start_ui_pump(self):
        def pump():
            while True:
                try:
                    fn = self.ui_queue.get_nowait()
                except queue.Empty:
                    break
                try:
                    fn()
                except Exception:
                    pass
            self.after(80, pump)

        self.after(80, pump)

    def _cleanup_stale_temp(self):
        # Only remove job directories left behind by previous sessions (older than 24h)
        # so a concurrently running second app instance is never disturbed.
        if not os.path.exists(DEFAULT_TEMP_DIR):
            return
        import shutil
        cutoff = time.time() - 24 * 3600
        for item in os.listdir(DEFAULT_TEMP_DIR):
            item_path = os.path.join(DEFAULT_TEMP_DIR, item)
            try:
                if os.path.getmtime(item_path) > cutoff:
                    continue
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path, ignore_errors=True)
                elif os.path.isfile(item_path):
                    os.remove(item_path)
            except Exception:
                pass

    def _on_close(self):
        if self.is_converting:
            from tkinter import messagebox
            confirm = messagebox.askyesno(
                "Conversion In Progress",
                "A conversion is still running. Aborting now will discard its progress.\n\nAbort and close JaneConverter?",
                icon="warning"
            )
            if not confirm:
                return
            self.abort_requested.set()
        try:
            self.destroy()
        except Exception:
            pass
        os._exit(0)

    def _start_engine_auto_updater(self):
        def worker():
            def on_status(msg):
                self.log_queue.put(f"[AutoUpdate] {msg}\n")
            update_engine(status_callback=on_status)
            try:
                repo_info = check_for_repo_updates()
                if repo_info.get("has_update"):
                    commits = repo_info.get("commits_behind", 1)
                    s = "s" if commits > 1 else ""
                    on_status(f"JaneConverter update available ({commits} new commit{s}). Click 'Check for Updates' to patch.")
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _on_check_updates_clicked(self):
        if getattr(self, "_is_checking_updates", False):
            return

        confirmed = messagebox.askyesno(
            "Check for Updates",
            "JaneConverter will check for new application commits and a newer yt-dlp engine,\n"
            "then download and install them automatically.\n\n"
            "Application updates restart nothing — you'll be asked to restart afterwards.\n\n"
            "Continue?"
        )
        if not confirmed:
            return

        self._is_checking_updates = True
        self.update_btn.configure(state="disabled", text="🔄 Checking...")

        def worker():
            def on_status(msg):
                self.log_queue.put(f"[AutoUpdate] {msg}\n")

            try:
                result = check_and_apply_all_updates(status_callback=on_status)
            except Exception as e:
                result = {
                    "repo_updated": False,
                    "engine_updated": False,
                    "already_up_to_date": False,
                    "error": str(e),
                }

            self._post_ui(lambda: self._on_update_completed(result))

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_completed(self, result: Dict[str, Any]):
        self._is_checking_updates = False
        self.update_btn.configure(state="normal", text="🔄 Check for Updates")

        if result.get("repo_updated") or result.get("engine_updated"):
            changes = []
            if result.get("repo_updated"):
                changes.append("JaneConverter application code updated to the latest repository commit.")
            if result.get("engine_updated"):
                changes.append(f"Extractor engine updated to v{result.get('current_engine_version', 'latest')}.")

            body = "\n\n".join(changes)
            if result.get("repo_updated"):
                body += "\n\nPlease restart JaneConverter to run the updated code."
            messagebox.showinfo("Updates Installed", body)
        elif result.get("already_up_to_date"):
            commit = result.get("current_commit", "latest")
            eng_ver = result.get("current_engine_version", "latest")
            messagebox.showinfo(
                "JaneConverter Up to Date",
                f"JaneConverter is already running the latest version!\n\n"
                f"Repo Commit: {commit}\n"
                f"Extractor Engine: v{eng_ver}"
            )
        else:
            err = result.get("error") or "Could not check for updates."
            messagebox.showwarning("Update Check", f"{err}\n\nPlease check your internet connection and try again.")

    # -------------------------------------------------------------
    # 1. HEADER SECTION
    # -------------------------------------------------------------
    def _build_header(self):
        header_frame = ctk.CTkFrame(
            self,
            fg_color=THEME["card_bg"],
            corner_radius=0,
            border_width=0,
            height=70
        )
        header_frame.pack(fill="x", padx=0, pady=(0, 10))
        header_frame.pack_propagate(False)

        brand_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        brand_frame.pack(side="left", padx=16, pady=12)

        if os.path.exists(ICON_PNG):
            try:
                pil_img = Image.open(ICON_PNG).resize((34, 34), Image.Resampling.LANCZOS)
                self.header_icon = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(34, 34))
                icon_lbl = ctk.CTkLabel(brand_frame, image=self.header_icon, text="")
                icon_lbl.pack(side="left", padx=(0, 10))
            except Exception:
                pass

        title_lbl = ctk.CTkLabel(
            brand_frame,
            text="JaneConverter",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=THEME["text_primary"]
        )
        title_lbl.pack(side="left", padx=(0, 8))

        sub_lbl = ctk.CTkLabel(
            brand_frame,
            text="Universal Media Studio",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=THEME["magenta"]
        )
        sub_lbl.pack(side="left")

        # Telemetry Pill (Far Right)
        hw_pill = ctk.CTkFrame(
            header_frame,
            fg_color=THEME["input_bg"],
            corner_radius=20,
            border_width=1,
            border_color=THEME["card_border"]
        )
        hw_pill.pack(side="right", padx=14, pady=12)

        self.hw_pulse_dot = ctk.CTkLabel(
            hw_pill,
            text="●",
            font=ctk.CTkFont(size=11),
            text_color=THEME["success"]
        )
        self.hw_pulse_dot.pack(side="left", padx=(10, 4))

        self.hw_badge = ctk.CTkLabel(
            hw_pill,
            text="CPU: 0% | RAM: 0GB | Initializing...",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=THEME["cyan"]
        )
        self.hw_badge.pack(side="left", padx=(0, 12), pady=4)

        # Check for Updates Button (Left of Telemetry Pill)
        self.update_btn = ctk.CTkButton(
            header_frame,
            text="🔄 Check for Updates",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color=THEME["card_inner"],
            hover_color=THEME["card_border_glow"],
            border_width=1,
            border_color=THEME["card_border"],
            text_color=THEME["text_primary"],
            height=30,
            corner_radius=15,
            command=self._on_check_updates_clicked
        )
        self.update_btn.pack(side="right", padx=(0, 10), pady=12)

    # -------------------------------------------------------------
    # 2. MAIN TABS
    # -------------------------------------------------------------
    def _build_tabs(self):
        self.tabview = ctk.CTkTabview(
            self,
            fg_color=THEME["card_bg"],
            segmented_button_fg_color=THEME["card_inner"],
            segmented_button_selected_color=THEME["magenta"],
            segmented_button_selected_hover_color=THEME["magenta_hover"],
            segmented_button_unselected_color=THEME["card_inner"],
            segmented_button_unselected_hover_color=THEME["card_border_glow"],
            text_color=THEME["text_primary"],
            border_width=1,
            border_color=THEME["card_border"],
            corner_radius=12
        )
        self.tabview.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        self.tab_studio = self.tabview.add("⚡ Converter")
        self.tab_library = self.tabview.add("📁 Converted Library")
        self.tab_console = self.tabview.add("💻 Console")

        self.tabview.set("⚡ Converter")

    # -------------------------------------------------------------
    # 3. TAB 1: STUDIO / CONVERTER
    # -------------------------------------------------------------
    def _build_studio_tab(self):
        tab = self.tab_studio
        tab.grid_columnconfigure(0, weight=1)

        # 3.1 Source Media Input Card
        src_card = ctk.CTkFrame(
            tab,
            fg_color=THEME["card_inner"],
            corner_radius=10,
            border_width=1,
            border_color=THEME["card_border"]
        )
        src_card.pack(fill="x", padx=12, pady=(8, 8))

        top_row = ctk.CTkFrame(src_card, fg_color="transparent")
        top_row.pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkLabel(
            top_row,
            text="Source Media URL or Local Path",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=THEME["text_primary"]
        ).pack(side="left")

        self.source_badge = ctk.CTkLabel(
            top_row,
            text="Ready for URL",
            font=ctk.CTkFont(size=11),
            text_color=THEME["cyan"]
        )
        self.source_badge.pack(side="right")

        input_row = ctk.CTkFrame(src_card, fg_color="transparent")
        input_row.pack(fill="x", padx=12, pady=(4, 12))

        self.src_entry = ctk.CTkEntry(
            input_row,
            placeholder_text="Paste any link (YouTube, Spotify, SoundCloud, TikTok, Twitter, NSFW) or local path...",
            height=38,
            font=ctk.CTkFont(size=12),
            fg_color=THEME["input_bg"],
            border_color=THEME["card_border"],
            border_width=1,
            text_color=THEME["text_primary"]
        )
        self.src_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.src_entry.bind("<KeyRelease>", self._on_source_text_changed)

        paste_btn = ctk.CTkButton(
            input_row,
            text="📋 Paste",
            width=80,
            height=38,
            fg_color=THEME["card_inner"],
            hover_color=THEME["card_border_glow"],
            text_color=THEME["text_primary"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._paste_clipboard
        )
        paste_btn.pack(side="left", padx=(0, 6))

        browse_btn = ctk.CTkButton(
            input_row,
            text="📁 Browse",
            width=85,
            height=38,
            fg_color=THEME["card_inner"],
            hover_color=THEME["card_border_glow"],
            text_color=THEME["text_primary"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._browse_local_file
        )
        browse_btn.pack(side="left", padx=(0, 6))

        self.playlist_btn = ctk.CTkButton(
            input_row,
            text="📑 Playlist Tracks",
            width=140,
            height=38,
            fg_color=THEME["card_inner"],
            hover_color=THEME["magenta_hover"],
            text_color=THEME["text_muted"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._fetch_and_open_playlist_selector
        )
        self.playlist_btn.pack(side="left")

        # 3.2 Conversion Settings Card
        settings_card = ctk.CTkFrame(
            tab,
            fg_color=THEME["card_inner"],
            corner_radius=10,
            border_width=1,
            border_color=THEME["card_border"]
        )
        settings_card.pack(fill="x", padx=12, pady=(4, 8))

        s_header = ctk.CTkFrame(settings_card, fg_color="transparent")
        s_header.pack(fill="x", padx=12, pady=(10, 6))

        ctk.CTkLabel(
            s_header,
            text="Output Format & Transcode Parameters",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=THEME["text_primary"]
        ).pack(side="left")

        # Mode Selector: Audio Only vs Full Video
        self.mode_var = ctk.StringVar(value="audio")
        self.mode_selector = ctk.CTkSegmentedButton(
            s_header,
            values=["🎵 Audio Format", "🎬 Video Format"],
            command=self._on_mode_toggled,
            selected_color=THEME["magenta"],
            selected_hover_color=THEME["magenta_hover"],
            unselected_color=THEME["input_bg"],
            unselected_hover_color=THEME["card_border_glow"],
            font=ctk.CTkFont(size=11, weight="bold"),
            height=28
        )
        self.mode_selector.set("🎵 Audio Format")
        self.mode_selector.pack(side="right")

        # Parameters Grid Container
        grid_frame = ctk.CTkFrame(settings_card, fg_color="transparent")
        grid_frame.pack(fill="x", padx=12, pady=(4, 12))
        grid_frame.grid_columnconfigure((0, 1, 2), weight=1)

        # Col 0: Target Format
        f_box = ctk.CTkFrame(grid_frame, fg_color=THEME["input_bg"], corner_radius=8, border_width=1, border_color=THEME["card_border"])
        f_box.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        ctk.CTkLabel(f_box, text="Container Format", font=ctk.CTkFont(size=11, weight="bold"), text_color=THEME["text_muted"]).pack(anchor="w", padx=10, pady=(8, 4))
        self.format_menu = ctk.CTkOptionMenu(
            f_box,
            values=["MP3", "WAV", "FLAC", "AAC", "OGG"],
            command=self._on_format_changed,
            fg_color=THEME["card_inner"],
            button_color=THEME["card_border_glow"],
            button_hover_color=THEME["cyan_hover"],
            dropdown_fg_color=THEME["card_bg"],
            font=ctk.CTkFont(size=12),
            height=32
        )
        self.format_menu.pack(fill="x", padx=10, pady=(0, 10))

        # Col 1: Audio Bitrate / Quality
        self.q_box = ctk.CTkFrame(grid_frame, fg_color=THEME["input_bg"], corner_radius=8, border_width=1, border_color=THEME["card_border"])
        self.q_box.grid(row=0, column=1, sticky="nsew", padx=4, pady=4)
        self.q_label = ctk.CTkLabel(self.q_box, text="Audio Bitrate", font=ctk.CTkFont(size=11, weight="bold"), text_color=THEME["text_muted"])
        self.q_label.pack(anchor="w", padx=10, pady=(8, 4))
        self.quality_menu = ctk.CTkOptionMenu(
            self.q_box,
            values=["320 kbps (High Fidelity)", "256 kbps (High Quality)", "192 kbps (Standard)", "128 kbps (Compact)"],
            fg_color=THEME["card_inner"],
            button_color=THEME["card_border_glow"],
            button_hover_color=THEME["cyan_hover"],
            dropdown_fg_color=THEME["card_bg"],
            font=ctk.CTkFont(size=12),
            height=32
        )
        self.quality_menu.pack(fill="x", padx=10, pady=(0, 10))

        # Col 2: Sample Rate / Resolution
        self.sr_box = ctk.CTkFrame(grid_frame, fg_color=THEME["input_bg"], corner_radius=8, border_width=1, border_color=THEME["card_border"])
        self.sr_box.grid(row=0, column=2, sticky="nsew", padx=4, pady=4)
        self.sr_label = ctk.CTkLabel(self.sr_box, text="Sample Rate", font=ctk.CTkFont(size=11, weight="bold"), text_color=THEME["text_muted"])
        self.sr_label.pack(anchor="w", padx=10, pady=(8, 4))
        self.sr_menu = ctk.CTkOptionMenu(
            self.sr_box,
            values=["48.0 kHz (Studio Broadcast)", "44.1 kHz (CD Standard)", "96.0 kHz (Hi-Res Audio)"],
            fg_color=THEME["card_inner"],
            button_color=THEME["card_border_glow"],
            button_hover_color=THEME["cyan_hover"],
            dropdown_fg_color=THEME["card_bg"],
            font=ctk.CTkFont(size=12),
            height=32
        )
        self.sr_menu.pack(fill="x", padx=10, pady=(0, 10))

        # Additional Audio Switches row
        switches_row = ctk.CTkFrame(settings_card, fg_color="transparent")
        switches_row.pack(fill="x", padx=12, pady=(0, 6))

        self.norm_switch = ctk.CTkSwitch(
            switches_row,
            text="EBU R128 Loudness Normalization (-14 LUFS Streaming Standard)",
            progress_color=THEME["cyan"],
            font=ctk.CTkFont(size=11),
            text_color=THEME["text_primary"]
        )
        self.norm_switch.pack(side="left", padx=4)

        gpu_switch_text = f"Hardware Acceleration ({self.hw_info['short_gpu']} • {self.hw_info['encoder_name']})" if self.hw_info.get("has_gpu") else "Hardware Acceleration (CPU Mode)"
        self.gpu_switch = ctk.CTkSwitch(
            switches_row,
            text=gpu_switch_text,
            progress_color=THEME["success"],
            font=ctk.CTkFont(size=11),
            text_color=THEME["text_primary"]
        )
        if self.hw_info.get("has_gpu"):
            self.gpu_switch.select()
        else:
            self.gpu_switch.deselect()
            self.gpu_switch.configure(state="disabled")
        self.gpu_switch.pack(side="right", padx=4)

        # Metadata & Cover Art Switches row
        meta_switches_row = ctk.CTkFrame(settings_card, fg_color="transparent")
        meta_switches_row.pack(fill="x", padx=12, pady=(0, 10))

        self.save_art_switch = ctk.CTkSwitch(
            meta_switches_row,
            text="Embed & Save Cover Art / Thumbnail",
            progress_color=THEME["magenta"],
            font=ctk.CTkFont(size=11),
            text_color=THEME["text_primary"]
        )
        self.save_art_switch.select()
        self.save_art_switch.pack(side="left", padx=4)

        self.save_meta_switch = ctk.CTkSwitch(
            meta_switches_row,
            text="Export Full Credits & Metadata (.txt)",
            progress_color=THEME["cyan"],
            font=ctk.CTkFont(size=11),
            text_color=THEME["text_primary"]
        )
        self.save_meta_switch.select()
        self.save_meta_switch.pack(side="right", padx=4)

        # 3.3 Destination Directory Card
        dest_card = ctk.CTkFrame(
            tab,
            fg_color=THEME["card_inner"],
            corner_radius=10,
            border_width=1,
            border_color=THEME["card_border"]
        )
        dest_card.pack(fill="x", padx=12, pady=(4, 8))

        d_row = ctk.CTkFrame(dest_card, fg_color="transparent")
        d_row.pack(fill="x", padx=12, pady=10)

        ctk.CTkLabel(
            d_row,
            text="Export Folder:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=THEME["text_primary"]
        ).pack(side="left", padx=(0, 8))

        self.dest_entry = ctk.CTkEntry(
            d_row,
            height=32,
            font=ctk.CTkFont(size=11),
            fg_color=THEME["input_bg"],
            border_color=THEME["card_border"],
            border_width=1,
            text_color=THEME["text_primary"]
        )
        self.dest_entry.insert(0, DEFAULT_CONVERTED_DIR)
        self.dest_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        dest_btn = ctk.CTkButton(
            d_row,
            text="Browse",
            width=70,
            height=32,
            fg_color=THEME["input_bg"],
            hover_color=THEME["card_border_glow"],
            font=ctk.CTkFont(size=11),
            command=self._browse_dest_dir
        )
        dest_btn.pack(side="left")

        # 3.4 Action and Progress Area
        action_card = ctk.CTkFrame(tab, fg_color="transparent")
        action_card.pack(fill="x", padx=12, pady=(10, 4))

        self.convert_btn = ctk.CTkButton(
            action_card,
            text="✨ CONVERT MEDIA",
            height=46,
            fg_color=THEME["magenta"],
            hover_color=THEME["magenta_hover"],
            text_color="#ffffff",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            corner_radius=10,
            command=self._start_conversion
        )
        self.convert_btn.pack(fill="x", pady=(0, 8))

        self.progress_bar = ctk.CTkProgressBar(
            action_card,
            progress_color=THEME["magenta"],
            fg_color=THEME["card_inner"],
            height=10,
            corner_radius=5
        )
        self.progress_bar.set(0.0)
        self.progress_bar.pack(fill="x", pady=(0, 6))

        stat_row = ctk.CTkFrame(action_card, fg_color="transparent")
        stat_row.pack(fill="x")

        self.status_label = ctk.CTkLabel(
            stat_row,
            text="Ready. Paste a link or select a file to begin conversion.",
            font=ctk.CTkFont(size=12),
            text_color=THEME["text_muted"]
        )
        self.status_label.pack(side="left")

        self.open_folder_btn = ctk.CTkButton(
            stat_row,
            text="📂 Open Folder",
            width=105,
            height=26,
            fg_color=THEME["card_inner"],
            hover_color=THEME["card_border_glow"],
            text_color=THEME["text_primary"],
            font=ctk.CTkFont(size=11),
            command=self._open_output_folder
        )
        self.open_folder_btn.pack(side="right")

        self.abort_btn = ctk.CTkButton(
            stat_row,
            text="🛑 Abort",
            width=85,
            height=26,
            fg_color="#7f1d1d",
            hover_color="#b91c1c",
            text_color="#ffffff",
            font=ctk.CTkFont(size=11, weight="bold"),
            state="disabled",
            command=self._abort_conversion
        )
        self.abort_btn.pack(side="right", padx=(0, 6))

    # -------------------------------------------------------------
    # 4. TAB 2: LIBRARY / RECENT FILES
    # -------------------------------------------------------------
    def _build_library_tab(self):
        tab = self.tab_library
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        top_bar = ctk.CTkFrame(tab, fg_color="transparent")
        top_bar.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))

        ctk.CTkLabel(
            top_bar,
            text="Exported Media Files",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=THEME["text_primary"]
        ).pack(side="left")

        refresh_btn = ctk.CTkButton(
            top_bar,
            text="🔄 Refresh",
            width=80,
            height=28,
            fg_color=THEME["card_inner"],
            hover_color=THEME["card_border_glow"],
            font=ctk.CTkFont(size=11),
            command=self._refresh_library
        )
        refresh_btn.pack(side="right")

        self.library_scroll = ctk.CTkScrollableFrame(
            tab,
            fg_color=THEME["input_bg"],
            border_color=THEME["card_border"],
            border_width=1,
            corner_radius=8
        )
        self.library_scroll.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        self._refresh_library()

    def _refresh_library(self):
        for w in self.library_scroll.winfo_children():
            w.destroy()

        dest_dir = self.dest_entry.get().strip() or DEFAULT_CONVERTED_DIR
        if not os.path.exists(dest_dir):
            return

        items = []
        try:
            for entry in os.scandir(dest_dir):
                if entry.is_file():
                    ext = os.path.splitext(entry.name)[1].lower().strip(".")
                    if ext in SUPPORTED_AUDIO_FORMATS or ext in SUPPORTED_VIDEO_FORMATS:
                        items.append((entry.stat().st_mtime, entry.path, entry.name, entry.stat().st_size, ext, False, 0))
                elif entry.is_dir():
                    count = 0
                    sub_sz = 0
                    for sub in os.scandir(entry.path):
                        if sub.is_file():
                            sub_ext = os.path.splitext(sub.name)[1].lower().strip(".")
                            if sub_ext in SUPPORTED_AUDIO_FORMATS or sub_ext in SUPPORTED_VIDEO_FORMATS:
                                count += 1
                                sub_sz += sub.stat().st_size
                    if count > 0:
                        items.append((entry.stat().st_mtime, entry.path, entry.name, sub_sz, "folder", True, count))
        except Exception:
            pass

        items.sort(key=lambda x: x[0], reverse=True)

        if not items:
            empty_lbl = ctk.CTkLabel(
                self.library_scroll,
                text="No converted media files found in export directory.",
                font=ctk.CTkFont(size=12),
                text_color=THEME["text_dark"]
            )
            empty_lbl.pack(pady=40)
            return

        for _, path, name, sz, ext, is_dir, count in items:
            row = ctk.CTkFrame(self.library_scroll, fg_color=THEME["card_inner"], corner_radius=6, height=44)
            row.pack(fill="x", padx=4, pady=3)
            row.pack_propagate(False)

            if is_dir:
                tag_lbl = ctk.CTkLabel(
                    row,
                    text="📁 PLAYLIST",
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color="#ffffff",
                    fg_color=THEME["magenta"],
                    corner_radius=4,
                    width=78,
                    height=22
                )
                tag_lbl.pack(side="left", padx=(10, 8))

                name_lbl = ctk.CTkLabel(
                    row,
                    text=f"{name} ({count} tracks)",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color=THEME["text_primary"],
                    anchor="w"
                )
                name_lbl.pack(side="left", fill="x", expand=True, padx=4)

                sz_str = f"{sz / (1024 * 1024):.1f} MB"
                ctk.CTkLabel(row, text=sz_str, font=ctk.CTkFont(size=11), text_color=THEME["text_dark"]).pack(side="left", padx=8)

                open_b = ctk.CTkButton(
                    row,
                    text="📂 Open",
                    width=65,
                    height=24,
                    fg_color=THEME["input_bg"],
                    hover_color=THEME["cyan_hover"],
                    text_color=THEME["cyan"],
                    font=ctk.CTkFont(size=11),
                    command=lambda p=path: os.startfile(p)
                )
                open_b.pack(side="right", padx=(4, 10))

                del_b = ctk.CTkButton(
                    row,
                    text="🗑️",
                    width=32,
                    height=24,
                    fg_color=THEME["input_bg"],
                    hover_color="#991b1b",
                    font=ctk.CTkFont(size=11),
                    command=lambda p=path: self._delete_library_dir(p)
                )
                del_b.pack(side="right", padx=2)

            else:
                is_video = ext in SUPPORTED_VIDEO_FORMATS
                icon_tag = "🎬" if is_video else "🎵"
                badge_color = THEME["magenta"] if is_video else THEME["cyan"]

                tag_lbl = ctk.CTkLabel(
                    row,
                    text=f"{icon_tag} {ext.upper()}",
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color="#ffffff",
                    fg_color=badge_color,
                    corner_radius=4,
                    width=64,
                    height=22
                )
                tag_lbl.pack(side="left", padx=(10, 8))

                name_lbl = ctk.CTkLabel(
                    row,
                    text=name,
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color=THEME["text_primary"],
                    anchor="w"
                )
                name_lbl.pack(side="left", fill="x", expand=True, padx=4)

                sz_str = f"{sz / (1024 * 1024):.1f} MB"
                ctk.CTkLabel(row, text=sz_str, font=ctk.CTkFont(size=11), text_color=THEME["text_dark"]).pack(side="left", padx=8)

                play_b = ctk.CTkButton(
                    row,
                    text="▶ Play",
                    width=65,
                    height=24,
                    fg_color=THEME["input_bg"],
                    hover_color=THEME["cyan_hover"],
                    text_color=THEME["cyan"],
                    font=ctk.CTkFont(size=11),
                    command=lambda p=path: self._play_file(p)
                )
                play_b.pack(side="right", padx=(4, 10))

                del_b = ctk.CTkButton(
                    row,
                    text="🗑️",
                    width=32,
                    height=24,
                    fg_color=THEME["input_bg"],
                    hover_color="#991b1b",
                    font=ctk.CTkFont(size=11),
                    command=lambda p=path: self._delete_library_file(p)
                )
                del_b.pack(side="right", padx=2)

    def _delete_library_dir(self, dir_path: str):
        if os.path.exists(dir_path):
            import shutil
            try:
                shutil.rmtree(dir_path, ignore_errors=True)
                self._refresh_library()
            except Exception:
                pass

    def _play_file(self, file_path: str):
        if os.path.exists(file_path):
            try:
                os.startfile(file_path)
            except Exception as e:
                self.status_label.configure(text=f"Could not open file: {e}")

    def _delete_library_file(self, file_path: str):
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                self._refresh_library()
            except Exception:
                pass

    # -------------------------------------------------------------
    # 5. TAB 3: CONSOLE
    # -------------------------------------------------------------
    def _build_console_tab(self):
        tab = self.tab_console
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        c_top = ctk.CTkFrame(tab, fg_color="transparent")
        c_top.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))

        ctk.CTkLabel(
            c_top,
            text="Console",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=THEME["text_primary"]
        ).pack(side="left")

        copy_btn = ctk.CTkButton(
            c_top,
            text="📋 Copy Logs",
            width=100,
            height=28,
            fg_color=THEME["card_inner"],
            hover_color=THEME["card_border_glow"],
            font=ctk.CTkFont(size=11),
            command=self._copy_logs
        )
        copy_btn.pack(side="right", padx=(6, 0))

        clear_btn = ctk.CTkButton(
            c_top,
            text="🧹 Clear",
            width=70,
            height=28,
            fg_color=THEME["card_inner"],
            hover_color=THEME["card_border_glow"],
            font=ctk.CTkFont(size=11),
            command=self._clear_logs
        )
        clear_btn.pack(side="right")

        self.log_box = ctk.CTkTextbox(
            tab,
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#cbd5e1",
            fg_color="#030208",
            border_color=THEME["card_border"],
            border_width=1,
            corner_radius=8,
            wrap="char"
        )
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

    def _start_log_listener(self):
        def check_queue():
            while not self.log_queue.empty():
                try:
                    text = self.log_queue.get_nowait()
                    self.log_box.insert("end", text)
                    self.log_box.see("end")
                except queue.Empty:
                    break
            self.after(100, check_queue)

        self.after(100, check_queue)

    def _copy_logs(self):
        txt = self.log_box.get("1.0", "end").strip()
        if txt:
            self.clipboard_clear()
            self.clipboard_append(txt)

    def _clear_logs(self):
        while not self.log_queue.empty():
            try:
                self.log_queue.get_nowait()
            except queue.Empty:
                break
        self.log_box.delete("1.0", "end")

    # -------------------------------------------------------------
    # 6. HARDWARE TELEMETRY LOOP
    # -------------------------------------------------------------
    def _start_hardware_monitor(self):
        if psutil:
            # Prime the CPU counter: the first cpu_percent(None) call otherwise always reads 0
            psutil.cpu_percent(None)

        def loop():
            while True:
                time.sleep(1.5)
                cpu_val = 0.0
                ram_pct = 0.0
                ram_used_gb = 0.0
                ram_tot_gb = 0.0
                gpu_util = 0
                gpu_used_mb = 0
                gpu_tot_mb = 0
                gpu_temp = 0

                if psutil:
                    try:
                        cpu_val = psutil.cpu_percent(None)
                        mem = psutil.virtual_memory()
                        ram_pct = mem.percent
                        ram_used_gb = mem.used / (1024 ** 3)
                        ram_tot_gb = mem.total / (1024 ** 3)
                    except Exception:
                        pass

                if pynvml and nvml_handle:
                    try:
                        util = pynvml.nvmlDeviceGetUtilizationRates(nvml_handle)
                        mem = pynvml.nvmlDeviceGetMemoryInfo(nvml_handle)
                        temp = pynvml.nvmlDeviceGetTemperature(nvml_handle, pynvml.NVML_TEMPERATURE_GPU)
                        gpu_util = int(util.gpu)
                        gpu_used_mb = int(mem.used // (1024 * 1024))
                        gpu_tot_mb = int(mem.total // (1024 * 1024))
                        gpu_temp = int(temp)
                    except Exception:
                        pass

                stats = (cpu_val, ram_pct, ram_used_gb, ram_tot_gb,
                         gpu_util, gpu_used_mb, gpu_tot_mb, gpu_temp)
                self._post_ui(lambda s=stats: self._apply_hardware_stats(*s))

        threading.Thread(target=loop, daemon=True).start()

    def _apply_hardware_stats(self, cpu, ram_pct, ram_used, ram_tot, gpu_pct, gpu_used, gpu_tot, gpu_temp):
        if self.hw_info.get("has_nvidia") and (gpu_pct > 0 or gpu_temp > 0):
            self.hw_badge.configure(
                text=f"CPU: {cpu:.0f}% | RAM: {ram_used:.1f}GB | {self.hw_info['short_gpu']}: {gpu_pct}% ({gpu_temp}°C)"
            )
        elif self.hw_info.get("has_gpu"):
            self.hw_badge.configure(
                text=f"CPU: {cpu:.0f}% | RAM: {ram_used:.1f}GB | {self.hw_info['short_gpu']}"
            )
        else:
            self.hw_badge.configure(
                text=f"CPU: {cpu:.0f}% | RAM: {ram_used:.1f}GB | CPU Mode"
            )

    # -------------------------------------------------------------
    # 7. EVENT HANDLERS & HELPERS
    # -------------------------------------------------------------
    def _on_source_text_changed(self, event=None):
        txt = self.src_entry.get().strip()
        stype = identify_source_type(txt)
        is_playlist = is_playlist_url(txt)

        if is_playlist:
            self.source_badge.configure(text="📑 Playlist / Album Detected", text_color=THEME["yellow"])
            self.playlist_btn.configure(
                text="📑 Select Playlist",
                fg_color=THEME["magenta"],
                hover_color=THEME["magenta_hover"],
                text_color="#ffffff"
            )
        else:
            type_labels = {
                "spotify": "Spotify Track (Auto Search)",
                "youtube": "YouTube Video / Stream",
                "soundcloud": "SoundCloud Audio",
                "tiktok": "TikTok Short Video",
                "twitter": "Twitter / X Media",
                "facebook": "Facebook Video",
                "reddit": "Reddit Media",
                "twitch": "Twitch Stream / Clip",
                "generic_url": "Web Media Stream",
                "local_file": "Local Media File" if txt else "Ready for URL"
            }
            self.source_badge.configure(text=type_labels.get(stype, "Ready for URL"), text_color=THEME["cyan"])
            self.playlist_btn.configure(
                text="📑 Playlist Tracks",
                fg_color=THEME["card_inner"],
                hover_color=THEME["card_border_glow"],
                text_color=THEME["text_muted"]
            )

    def _on_format_changed(self, selected_fmt: str):
        fmt = selected_fmt.split()[0].lower()
        if fmt == "wav":
            self.q_label.configure(text="Audio Bit Depth")
            self.quality_menu.configure(values=[
                "16-bit PCM (CD Standard)",
                "24-bit PCM (Studio Master)",
                "32-bit Float (Studio Master)"
            ])
            self.quality_menu.set("24-bit PCM (Studio Master)")
            self.sr_label.configure(text="Sample Rate")
            self.sr_menu.configure(values=["48.0 kHz (Studio Broadcast)", "44.1 kHz (CD Standard)", "96.0 kHz (Hi-Res Audio)"])
            self.sr_menu.set("48.0 kHz (Studio Broadcast)")
        elif fmt == "flac":
            self.q_label.configure(text="Audio Bit Depth")
            self.quality_menu.configure(values=[
                "16-bit Lossless (CD Standard)",
                "24-bit Lossless (Studio Master)"
            ])
            self.quality_menu.set("24-bit Lossless (Studio Master)")
            self.sr_label.configure(text="Sample Rate")
            self.sr_menu.configure(values=["48.0 kHz (Studio Broadcast)", "44.1 kHz (CD Standard)", "96.0 kHz (Hi-Res Audio)"])
            self.sr_menu.set("48.0 kHz (Studio Broadcast)")
        elif fmt in ("mp3", "aac"):
            self.q_label.configure(text="Audio Bitrate")
            self.quality_menu.configure(values=[
                "320 kbps (High Fidelity)",
                "256 kbps (High Quality)",
                "192 kbps (Standard)",
                "128 kbps (Compact)"
            ])
            self.quality_menu.set("320 kbps (High Fidelity)")
            self.sr_label.configure(text="Sample Rate")
            self.sr_menu.configure(values=["48.0 kHz (Studio Broadcast)", "44.1 kHz (CD Standard)", "96.0 kHz (Hi-Res Audio)"])
            self.sr_menu.set("48.0 kHz (Studio Broadcast)")
        elif fmt == "ogg":
            self.q_label.configure(text="Audio Quality")
            self.quality_menu.configure(values=[
                "320 kbps (High Fidelity)",
                "256 kbps (High Quality)",
                "192 kbps (Standard)",
                "128 kbps (Compact)"
            ])
            self.quality_menu.set("320 kbps (High Fidelity)")
            self.sr_label.configure(text="Sample Rate")
            self.sr_menu.configure(values=["48.0 kHz (Studio Broadcast)", "44.1 kHz (CD Standard)", "96.0 kHz (Hi-Res Audio)"])
            self.sr_menu.set("48.0 kHz (Studio Broadcast)")
        elif fmt in ("mp4", "mkv", "webm", "mov", "gif"):
            self.q_label.configure(text="Video Resolution")
            self.quality_menu.configure(values=["Original Best", "1080p Full HD", "720p HD", "4K Ultra HD"])
            self.quality_menu.set("Original Best")
            self.sr_label.configure(text="Frame Rate / Profile")
            self.sr_menu.configure(values=["Auto (Match Source)", "60 FPS High Smoothness", "30 FPS Standard"])
            self.sr_menu.set("Auto (Match Source)")

    def _on_mode_toggled(self, selected_mode: str):
        if "Audio" in selected_mode:
            self.format_menu.configure(values=["MP3", "WAV", "FLAC", "AAC", "OGG"])
            self.format_menu.set("MP3")
            self._on_format_changed("MP3")
        else:
            self.format_menu.configure(values=["MP4", "MKV", "WEBM", "MOV", "GIF"])
            self.format_menu.set("MP4")
            self._on_format_changed("MP4")

    def _paste_clipboard(self):
        try:
            txt = self.clipboard_get().strip()
            self.src_entry.delete(0, "end")
            self.src_entry.insert(0, txt)
            self._on_source_text_changed()
        except Exception:
            pass

    def _browse_local_file(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Select Media File",
            filetypes=[
                ("Media Files", "*.mp4 *.mkv *.mov *.avi *.webm *.mp3 *.wav *.flac *.aac *.m4a *.ogg"),
                ("All Files", "*.*")
            ]
        )
        if path:
            self.src_entry.delete(0, "end")
            self.src_entry.insert(0, path)
            self._on_source_text_changed()

    def _browse_dest_dir(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(title="Select Destination Folder", initialdir=self.dest_entry.get().strip() or DEFAULT_CONVERTED_DIR)
        if path:
            self.dest_entry.delete(0, "end")
            self.dest_entry.insert(0, path)

    def _play_latest_file(self):
        if self.last_converted_file and os.path.exists(self.last_converted_file):
            self._play_file(self.last_converted_file)
        else:
            from tkinter import messagebox
            messagebox.showinfo("No Media", "No converted media file to play yet.")

    def _open_output_folder(self):
        out_dir = self.dest_entry.get().strip() or DEFAULT_CONVERTED_DIR
        os.makedirs(out_dir, exist_ok=True)
        try:
            os.startfile(out_dir)
        except Exception:
            pass

    # -------------------------------------------------------------
    # 8. CONVERSION RUNNER & PLAYLIST WORKFLOW
    # -------------------------------------------------------------
    def _fetch_and_open_playlist_selector(self):
        if self.is_converting:
            return

        source = self.src_entry.get().strip()
        if not source:
            from tkinter import messagebox
            messagebox.showwarning("Input Required", "Please paste a playlist or album link first.")
            return

        self.playlist_btn.configure(state="disabled", text="⏳ Inspecting...")
        self.status_label.configure(text="Fetching playlist track catalog...")
        self.progress_bar.set(0.05)

        def worker():
            try:
                pdata = fetch_playlist_entries(
                    url=source,
                    progress_callback=lambda f, m: self._post_ui(lambda: self._apply_progress(f, m))
                )
                self._post_ui(lambda: self._on_playlist_fetched(pdata))
            except Exception as e:
                error_message = str(e)
                self._post_ui(lambda: self._on_playlist_fetch_error(error_message))

        threading.Thread(target=worker, daemon=True).start()

    def _on_playlist_fetched(self, pdata: Dict[str, Any]):
        self.playlist_btn.configure(state="normal", text="📑 Select Playlist")
        self.progress_bar.set(0.0)
        total = pdata.get("total_count")
        total_str = str(total) if total is not None else "an unknown number of"
        self.status_label.configure(text=f"Loaded {total_str} tracks from '{pdata.get('playlist_title', 'Playlist')}'.")

        if not pdata.get("entries"):
            from tkinter import messagebox
            messagebox.showwarning("No Items Found", f"No tracks could be found in this playlist:\n{pdata.get('playlist_title')}")
            return

        PlaylistSelectionWindow(self, pdata, self._start_playlist_batch_conversion)

    def _on_playlist_fetch_error(self, err_msg: str):
        # Restore the highlighted playlist styling when the failed source was a playlist URL
        source = self.src_entry.get().strip()
        if is_playlist_url(source):
            self.playlist_btn.configure(
                state="normal", text="📑 Select Playlist",
                fg_color=THEME["magenta"], hover_color=THEME["magenta_hover"],
                text_color="#ffffff"
            )
        else:
            self.playlist_btn.configure(
                state="normal", text="📑 Playlist Tracks",
                fg_color=THEME["card_inner"], hover_color=THEME["card_border_glow"],
                text_color=THEME["text_muted"]
            )
        self.progress_bar.set(0.0)
        self.status_label.configure(text="Failed to fetch playlist catalog.")
        from tkinter import messagebox
        messagebox.showerror("Playlist Extraction Failed", f"Could not extract playlist information:\n{err_msg}")

    def _collect_settings(self):
        """
        Reads the current UI selections into pipeline parameters.
        Single source of truth for both single-track and playlist-batch conversion.
        """
        raw_fmt = self.format_menu.get().split()[0].lower()
        raw_quality = self.quality_menu.get()
        normalize_audio = bool(self.norm_switch.get())
        use_gpu = bool(self.gpu_switch.get())
        save_cover_art = bool(self.save_art_switch.get())
        save_metadata = bool(self.save_meta_switch.get())

        if raw_fmt == "wav":
            bitrate = ("16-bit" if "16" in raw_quality
                       else "32-bit" if "32" in raw_quality
                       else "24-bit")
        elif raw_fmt == "flac":
            bitrate = "16-bit" if "16" in raw_quality else "24-bit"
        elif raw_fmt in ("mp4", "mkv", "webm", "mov", "gif"):
            # In video mode the quality menu holds resolutions, not bitrates
            bitrate = None
        else:
            bitrate = "320k"
            for candidate in ("320", "256", "192", "128"):
                if candidate in raw_quality:
                    bitrate = f"{candidate}k"
                    break

        raw_res = raw_quality.lower()
        if "4k" in raw_res:
            resolution = "4k"
        elif "1440" in raw_res:
            resolution = "1440p"
        elif "1080" in raw_res:
            resolution = "1080p"
        elif "720" in raw_res:
            resolution = "720p"
        elif "480" in raw_res:
            resolution = "480p"
        else:
            resolution = "original"

        raw_sr = self.sr_menu.get()
        if "44.1" in raw_sr:
            sample_rate = 44100
        elif "96.0" in raw_sr:
            sample_rate = 96000
        else:
            sample_rate = 48000

        return {
            "format": raw_fmt,
            "bitrate": bitrate,
            "sample_rate": sample_rate,
            "normalize_audio": normalize_audio,
            "use_gpu": use_gpu,
            "save_cover_art": save_cover_art,
            "save_metadata": save_metadata,
            "resolution": resolution,
        }

    def _validate_destination(self, output_dir: str) -> bool:
        """Ensures the destination folder exists or can be created; shows an error dialog otherwise."""
        try:
            os.makedirs(output_dir, exist_ok=True)
            if not os.access(output_dir, os.W_OK):
                raise PermissionError("The folder is not writable.")
            return True
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror(
                "Invalid Destination Folder",
                f"Cannot use destination folder:\n{output_dir}\n\nReason: {e}"
            )
            return False

    def _start_playlist_batch_conversion(self, selected_entries: list, playlist_title: str):
        if self.is_converting:
            return

        output_dir = self.dest_entry.get().strip() or DEFAULT_CONVERTED_DIR
        if not self._validate_destination(output_dir):
            return
        settings = self._collect_settings()

        self.is_converting = True
        self.abort_requested.clear()
        self.abort_btn.configure(state="normal")
        self.start_conversion_time = time.time()
        self.convert_btn.configure(state="disabled", text="⏳ CONVERTING PLAYLIST...")
        self.playlist_btn.configure(state="disabled")
        self.progress_bar.set(0.01)
        self.status_label.configure(text=f"Batch converting {len(selected_entries)} playlist items...")

        threading.Thread(
            target=self._run_playlist_worker,
            args=(playlist_title, selected_entries, output_dir, settings),
            daemon=True
        ).start()

    def _run_playlist_worker(self, playlist_title, selected_entries, output_dir, settings):
        try:
            summary = process_playlist_conversion(
                playlist_title=playlist_title,
                selected_entries=selected_entries,
                output_dir=output_dir,
                target_format=settings["format"],
                bitrate=settings["bitrate"],
                sample_rate=settings["sample_rate"],
                normalize_audio=settings["normalize_audio"],
                resolution=settings["resolution"],
                use_nvenc=settings["use_gpu"],
                use_gpu=settings["use_gpu"],
                save_cover_art=settings["save_cover_art"],
                save_metadata=settings["save_metadata"],
                abort_event=self.abort_requested,
                progress_callback=lambda f, m: self._post_ui(lambda: self._apply_progress(f, m))
            )
            first_file = summary["converted_files"][0] if summary["converted_files"] else None
            self._post_ui(lambda: self._on_playlist_conversion_success(summary, first_file))
        except KeyboardInterrupt:
            self._post_ui(self._on_conversion_aborted)
        except Exception as e:
            error_message = str(e)
            if self.abort_requested.is_set() or "aborted" in error_message.lower():
                self._post_ui(self._on_conversion_aborted)
            else:
                import traceback
                traceback.print_exc()
                self._post_ui(lambda: self._on_conversion_error(error_message))

    def _on_playlist_conversion_success(self, summary: Dict[str, Any], first_file: Optional[str] = None):
        self.last_converted_file = first_file
        self.is_converting = False
        self.abort_requested.clear()
        self.abort_btn.configure(state="disabled")
        self.convert_btn.configure(state="normal", text="✨ CONVERT MEDIA")
        self.playlist_btn.configure(state="normal")
        self.progress_bar.set(1.0)
        p_dir = summary.get("playlist_dir", "")
        folder_name = os.path.basename(p_dir)
        succ = summary.get("successful_count", 0)
        tot = summary.get("total_selected", 0)
        self.status_label.configure(text=f"Playlist exported: {succ}/{tot} tracks saved to '{folder_name}'.")
        self._refresh_library()

        from tkinter import messagebox
        messagebox.showinfo(
            "Playlist Conversion Complete!",
            f"Successfully converted {succ} of {tot} tracks!\n\nFolder:\n{p_dir}"
        )

    def _start_conversion(self):
        if self.is_converting:
            return

        source = self.src_entry.get().strip()
        if not source:
            from tkinter import messagebox
            messagebox.showwarning("Input Required", "Please provide a valid media URL or select a local file.")
            return

        if is_playlist_url(source):
            from tkinter import messagebox
            choice = messagebox.askyesno(
                "Playlist Detected",
                "This URL appears to be a playlist or album containing multiple tracks.\n\nWould you like to open the playlist track selector to choose what to download?",
                icon="question"
            )
            if choice:
                self._fetch_and_open_playlist_selector()
                return

        output_dir = self.dest_entry.get().strip() or DEFAULT_CONVERTED_DIR
        if not self._validate_destination(output_dir):
            return
        settings = self._collect_settings()

        self.is_converting = True
        self.abort_requested.clear()
        self.abort_btn.configure(state="normal")
        self.start_conversion_time = time.time()
        self.convert_btn.configure(state="disabled", text="⏳ PROCESSING MEDIA...")
        self.playlist_btn.configure(state="disabled")
        self.progress_bar.set(0.02)
        self.status_label.configure(text="Initializing transcode pipeline...")

        threading.Thread(
            target=self._run_conversion_worker,
            args=(source, output_dir, settings),
            daemon=True
        ).start()

    def _run_conversion_worker(self, source, output_dir, settings):
        try:
            result_path = process_conversion(
                source=source,
                output_dir=output_dir,
                target_format=settings["format"],
                bitrate=settings["bitrate"],
                sample_rate=settings["sample_rate"],
                normalize_audio=settings["normalize_audio"],
                resolution=settings["resolution"],
                use_nvenc=settings["use_gpu"],
                use_gpu=settings["use_gpu"],
                save_cover_art=settings["save_cover_art"],
                save_metadata=settings["save_metadata"],
                abort_event=self.abort_requested,
                progress_callback=lambda f, m: self._post_ui(lambda: self._apply_progress(f, m))
            )
            self._post_ui(lambda: self._on_conversion_success(result_path))
        except KeyboardInterrupt:
            self._post_ui(self._on_conversion_aborted)
        except Exception as e:
            error_message = str(e)
            if self.abort_requested.is_set() or "aborted" in error_message.lower():
                self._post_ui(self._on_conversion_aborted)
            else:
                import traceback
                traceback.print_exc()
                self._post_ui(lambda: self._on_conversion_error(error_message))

    def _apply_progress(self, frac: float, msg: str):
        self.progress_bar.set(frac)
        self.status_label.configure(text=f"[{int(frac * 100)}%] {msg}")

    def _on_conversion_success(self, result_path: str):
        self.last_converted_file = result_path
        self.is_converting = False
        self.abort_requested.clear()
        self.abort_btn.configure(state="disabled")
        self.convert_btn.configure(state="normal", text="✨ CONVERT MEDIA")
        self.playlist_btn.configure(state="normal")
        self.progress_bar.set(1.0)
        self.status_label.configure(text=f"Exported: {os.path.basename(result_path)}")
        self._refresh_library()

        from tkinter import messagebox
        messagebox.showinfo(
            "Conversion Complete!",
            f"Successfully converted media!\nExported to:\n{result_path}"
        )

    def _on_conversion_error(self, err_msg: str):
        self.is_converting = False
        self.abort_requested.clear()
        self.abort_btn.configure(state="disabled")
        self.convert_btn.configure(state="normal", text="✨ CONVERT MEDIA")
        self.playlist_btn.configure(state="normal")
        self.progress_bar.set(0.0)
        self.status_label.configure(text="Conversion error encountered.")

        from tkinter import messagebox
        messagebox.showerror("Conversion Failed", f"An error occurred during transcode:\n{err_msg}")

    def _abort_conversion(self):
        if self.is_converting:
            self.abort_requested.set()
            self.status_label.configure(text="Aborting conversion...")
            self.abort_btn.configure(state="disabled")
            print("\n[!] Abort requested. Stopping pipeline...\n")

    def _on_conversion_aborted(self):
        self.is_converting = False
        self.abort_requested.clear()
        self.convert_btn.configure(state="normal", text="✨ CONVERT MEDIA")
        self.playlist_btn.configure(state="normal")
        self.abort_btn.configure(state="disabled")
        self.progress_bar.set(0.0)
        self.status_label.configure(text="Conversion aborted by user.")
        from tkinter import messagebox
        messagebox.showinfo("Aborted", "Conversion was aborted by user.")

def main():
    app = JaneConverterApp()
    app.mainloop()

if __name__ == "__main__":
    main()
