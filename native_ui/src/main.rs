#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use eframe::egui::{self, Color32, RichText, Stroke, Vec2};
use rand::{distributions::Alphanumeric, Rng};
use std::collections::{HashMap, VecDeque};
use std::fs;
use std::io::{self, BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use std::time::Duration;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

const MAGENTA: Color32 = Color32::from_rgb(232, 44, 117);
const BLUE: Color32 = Color32::from_rgb(59, 130, 246);
const SURFACE: Color32 = Color32::from_rgb(15, 14, 31);
const SURFACE_DARK: Color32 = Color32::from_rgb(5, 4, 13);
const BORDER: Color32 = Color32::from_rgb(40, 37, 64);
const TEXT: Color32 = Color32::from_rgb(237, 237, 237);
const MUTED: Color32 = Color32::from_rgb(156, 163, 175);
const SUCCESS: Color32 = Color32::from_rgb(16, 185, 129);
const AUDIO_FORMATS: &[&str] = &["mp3", "flac", "wav", "aac", "m4a", "ogg"];
const VIDEO_FORMATS: &[&str] = &["mp4", "mkv", "webm", "mov", "gif"];
const ALL_FORMATS: &[&str] = &[
    "mp3", "flac", "wav", "aac", "m4a", "ogg", "mp4", "mkv", "webm", "mov", "gif",
];
const AUDIO_BITRATES: &[&str] = &["320k", "256k", "192k", "128k"];
const WAV_QUALITY: &[&str] = &["16-bit", "24-bit", "32-bit float"];
const FLAC_QUALITY: &[&str] = &["16-bit", "24-bit"];
const OGG_QUALITY: &[&str] = &["q10", "q8", "q6", "q4"];
const VIDEO_QUALITY: &[&str] = &["best", "high", "balanced", "small"];
const MAX_LIBRARY_ROWS: usize = 500;
const ORIGINAL_ICON_PNG: &[u8] =
    include_bytes!(concat!(env!("CARGO_MANIFEST_DIR"), "/../assets/icon.png"));

#[derive(Clone, Copy, PartialEq, Eq)]
enum Page {
    Converter,
    Library,
}

#[derive(Clone)]
struct BrowserDetection {
    label: String,
    session_browser: Option<String>,
}

struct AccessEvent {
    generation: u64,
    browser: BrowserDetection,
}

struct AccessServer {
    link: String,
    stop: Arc<AtomicBool>,
}

#[derive(Clone)]
struct LibraryEntry {
    path: PathBuf,
    is_directory: bool,
    is_playlist: bool,
    media_count: usize,
    total_bytes: u64,
}

#[derive(Clone)]
struct PlaylistItem {
    index: usize,
    title: String,
    artist: String,
    duration: String,
}

impl AccessServer {
    fn start(
        source: &str,
        generation: u64,
        events: mpsc::Sender<AccessEvent>,
    ) -> std::io::Result<Self> {
        let listener = TcpListener::bind(("127.0.0.1", 0))?;
        listener.set_nonblocking(true)?;
        let port = listener.local_addr()?.port();
        let token: String = rand::thread_rng()
            .sample_iter(&Alphanumeric)
            .take(40)
            .map(char::from)
            .collect();
        let link = format!("http://127.0.0.1:{port}/access/{token}");
        let stop = Arc::new(AtomicBool::new(false));
        let stop_thread = Arc::clone(&stop);
        let source = source.to_owned();
        let token_thread = token.clone();
        thread::Builder::new()
            .name("account-access-server".to_owned())
            .spawn(move || {
                while !stop_thread.load(Ordering::Relaxed) {
                    match listener.accept() {
                        Ok((mut stream, _)) => handle_access_request(
                            &mut stream,
                            &source,
                            &token_thread,
                            generation,
                            &events,
                            &stop_thread,
                        ),
                        Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                            thread::sleep(Duration::from_millis(40))
                        }
                        Err(_) => break,
                    }
                }
            })?;
        Ok(Self { link, stop })
    }
}

impl Drop for AccessServer {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Relaxed);
    }
}

fn handle_access_request(
    stream: &mut TcpStream,
    source: &str,
    token: &str,
    generation: u64,
    events: &mpsc::Sender<AccessEvent>,
    stop: &AtomicBool,
) {
    let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
    let mut bytes = [0u8; 8192];
    let count = match stream.read(&mut bytes) {
        Ok(count) => count,
        Err(_) => return,
    };
    let request = String::from_utf8_lossy(&bytes[..count]);
    let mut lines = request.lines();
    let path = lines
        .next()
        .and_then(|line| line.split_whitespace().nth(1))
        .unwrap_or("");
    let mut user_agent = String::new();
    let mut client_hints = String::new();
    for line in lines {
        let lower = line.to_ascii_lowercase();
        if lower.starts_with("user-agent:") {
            user_agent = line
                .split_once(':')
                .map(|(_, value)| value.trim())
                .unwrap_or("")
                .to_owned();
        } else if lower.starts_with("sec-ch-ua:")
            || lower.starts_with("sec-ch-ua-full-version-list:")
        {
            client_hints.push_str(line);
            client_hints.push(' ');
        }
    }
    let detection = detect_browser(&user_agent, &client_hints);
    let base = format!("/access/{token}");
    if path == base {
        send_html(stream, 200, &landing_page(source, &detection, token));
    } else if path == format!("{base}/ready") {
        if stop.swap(true, Ordering::Relaxed) {
            send_html(stream, 410, &error_page("This access link has expired."));
            return;
        }
        send_html(stream, 200, &ready_page(&detection));
        let _ = events.send(AccessEvent {
            generation,
            browser: detection,
        });
    } else {
        send_html(stream, 404, &error_page("This access link is not valid."));
    }
}

fn detect_browser(user_agent: &str, client_hints: &str) -> BrowserDetection {
    let signal = format!("{} {}", user_agent, client_hints).to_ascii_lowercase();
    let candidates = [
        ("vivaldi", "Vivaldi", "vivaldi"),
        ("brave", "Brave", "brave"),
        ("edg/", "Microsoft Edge", "edge"),
        ("edga/", "Microsoft Edge", "edge"),
        ("edgios/", "Microsoft Edge", "edge"),
        ("opr/", "Opera", "opera"),
        ("opera", "Opera", "opera"),
        ("firefox", "Firefox", "firefox"),
        ("fxios", "Firefox", "firefox"),
        ("crios", "Google Chrome", "chrome"),
        ("chrome", "Google Chrome", "chrome"),
        ("chromium", "Chromium", "chromium"),
    ];
    for (marker, label, backend) in candidates {
        if signal.contains(marker) {
            return BrowserDetection {
                label: label.to_owned(),
                session_browser: Some(backend.to_owned()),
            };
        }
    }
    if signal.contains("safari") {
        return BrowserDetection {
            label: "Safari".to_owned(),
            session_browser: Some("safari".to_owned()),
        };
    }
    BrowserDetection {
        label: "Unrecognized browser".to_owned(),
        session_browser: None,
    }
}

fn landing_page(source: &str, detection: &BrowserDetection, token: &str) -> String {
    page("Account access", &format!("<h1>JaneConverter account access</h1><p>Use this temporary page in the browser whose session you want to use. JaneConverter never receives your password or cookies.</p><ol><li>Open the source link below.</li><li>Sign in normally if needed.</li><li>Return here and confirm access.</li></ol><p><a class=\"primary\" href=\"{}\" target=\"_blank\" rel=\"noreferrer\" referrerpolicy=\"no-referrer\">Open source link</a></p><p><a class=\"confirm\" href=\"/access/{token}/ready\">I’m signed in — confirm access</a></p><p class=\"note\">Browser detected: <strong>{}</strong>. The link expires after confirmation or when JaneConverter closes.</p>", html_escape(source), html_escape(&detection.label)))
}

fn is_supported_source_url(source: &str) -> bool {
    let trimmed = source.trim();
    let lower = trimmed.to_ascii_lowercase();
    let Some((scheme, authority)) = lower.split_once("://") else {
        return false;
    };
    (scheme == "http" || scheme == "https")
        && !authority.is_empty()
        && !authority.chars().any(|character| character.is_whitespace())
        && !trimmed
            .chars()
            .any(|character| character == '\r' || character == '\n')
}

fn parse_playlist_listing(output: &str) -> Result<(String, Vec<PlaylistItem>), String> {
    let mut title = None;
    let mut items = Vec::new();
    for line in output.lines() {
        if let Some(value) = line.strip_prefix("PLAYLIST\t") {
            title = Some(value.trim().to_owned());
            continue;
        }
        let Some(value) = line.strip_prefix("ENTRY\t") else {
            continue;
        };
        let mut fields = value.splitn(5, '\t');
        let index = fields
            .next()
            .and_then(|value| value.parse::<usize>().ok())
            .ok_or_else(|| "Playlist listing returned an invalid item index".to_owned())?;
        let item_title = fields.next().unwrap_or_default().to_owned();
        let artist = fields.next().unwrap_or_default().to_owned();
        let duration = fields.next().unwrap_or_default().to_owned();
        let has_url = !fields.next().unwrap_or_default().is_empty();
        if !item_title.is_empty() && has_url {
            items.push(PlaylistItem {
                index,
                title: item_title,
                artist,
                duration,
            });
        }
    }
    let title = title.ok_or_else(|| "Playlist loader returned no playlist title".to_owned())?;
    Ok((title, items))
}

fn ready_page(detection: &BrowserDetection) -> String {
    page("Access ready", &format!("<h1>Access confirmed</h1><p>Browser detected: <strong>{}</strong>.</p><p>Return to JaneConverter. The session will be used for the current app session only.</p>", html_escape(&detection.label)))
}
fn error_page(message: &str) -> String {
    page(
        "Access unavailable",
        &format!(
            "<h1>Access link unavailable</h1><p>{}</p>",
            html_escape(message)
        ),
    )
}
fn page(title: &str, body: &str) -> String {
    format!("<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"referrer\" content=\"no-referrer\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{}</title><style>body{{background:#0b0a14;color:#ededed;font:16px Segoe UI,Arial,sans-serif;max-width:650px;margin:12vh auto;padding:0 24px;line-height:1.55}}h1{{color:#f1f5f9}}a{{color:#93c5fd}}.primary,.confirm{{display:inline-block;padding:11px 16px;border-radius:8px;color:#fff;text-decoration:none;margin:4px 8px 4px 0}}.primary{{background:#2563eb}}.confirm{{background:#e82c75}}.note{{color:#9ca3af;font-size:13px}}</style></head><body>{}</body></html>", html_escape(title), body)
}
fn html_escape(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}
fn send_html(stream: &mut TcpStream, status: u16, body: &str) {
    let reason = if status == 200 {
        "OK"
    } else if status == 404 {
        "Not Found"
    } else {
        "Gone"
    };
    let response = format!("HTTP/1.1 {status} {reason}\r\nContent-Type: text/html; charset=utf-8\r\nCache-Control: no-store\r\nContent-Security-Policy: default-src 'none'; style-src 'unsafe-inline'\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}", body.len(), body);
    let _ = stream.write_all(response.as_bytes());
}

enum Event {
    Output(String),
    ConversionFinished(i32),
    UpdateFinished,
    LibraryLoaded(u64, Vec<LibraryEntry>),
    LibraryScanFailed(u64),
    PlaylistLoaded(u64, String, Vec<PlaylistItem>),
    PlaylistLoadFailed(u64, String),
}

type EventSender = mpsc::SyncSender<Event>;

struct JaneConverterApp {
    root: PathBuf,
    page: Page,
    sidebar_collapsed: bool,
    source: String,
    output_dir: String,
    category: String,
    format: String,
    bitrate: String,
    resolution: String,
    save_cover: bool,
    save_metadata: bool,
    use_gpu: bool,
    normalize: bool,
    status: String,
    progress: f32,
    logs: VecDeque<String>,
    running: bool,
    update_checking: bool,
    child: Option<Arc<Mutex<Option<Child>>>>,
    abort_requested: Option<Arc<AtomicBool>>,
    events: Option<mpsc::Receiver<Event>>,
    access_events: mpsc::Receiver<AccessEvent>,
    access_tx: mpsc::Sender<AccessEvent>,
    access_server: Option<AccessServer>,
    access_generation: u64,
    access_link: Option<String>,
    auth_browser: Option<String>,
    auth_label: Option<String>,
    library_path: PathBuf,
    library_entries: Vec<LibraryEntry>,
    library_scan_generation: u64,
    library_scanning: bool,
    pending_delete: Option<PathBuf>,
    logo_texture: Option<egui::TextureHandle>,
    theme_initialized: bool,
    frontend_preference: String,
    show_interface_settings: bool,
    playlist_items: Vec<PlaylistItem>,
    playlist_selected: Vec<bool>,
    playlist_title: String,
    playlist_generation: u64,
    playlist_loading: bool,
    selected_playlist_indexes: Option<String>,
}

impl JaneConverterApp {
    fn new(root: PathBuf) -> Self {
        let (access_tx, access_events) = mpsc::channel();
        let frontend_preference = read_frontend_preference(&root);
        let default_output = default_data_dir(&root).join("converted");
        let mut app = Self {
            output_dir: default_output.display().to_string(),
            root: root.clone(),
            page: Page::Converter,
            sidebar_collapsed: false,
            source: String::new(),
            category: "Music".to_owned(),
            format: "mp3".to_owned(),
            bitrate: "320k".to_owned(),
            resolution: "original".to_owned(),
            save_cover: true,
            save_metadata: true,
            use_gpu: true,
            normalize: false,
            status: "Ready for URL".to_owned(),
            progress: 0.0,
            logs: VecDeque::new(),
            running: false,
            update_checking: false,
            child: None,
            abort_requested: None,
            events: None,
            access_events,
            access_tx,
            access_server: None,
            access_generation: 0,
            access_link: None,
            auth_browser: None,
            auth_label: None,
            library_path: default_output,
            library_entries: Vec::new(),
            library_scan_generation: 0,
            library_scanning: false,
            pending_delete: None,
            logo_texture: None,
            theme_initialized: false,
            frontend_preference,
            show_interface_settings: false,
            playlist_items: Vec::new(),
            playlist_selected: Vec::new(),
            playlist_title: String::new(),
            playlist_generation: 0,
            playlist_loading: false,
            selected_playlist_indexes: None,
        };
        app.load_settings();
        app
    }

    fn load_settings(&mut self) {
        let settings = read_native_settings(&self.root);
        if let Some(value) = settings.get("output_dir") {
            if !value.trim().is_empty() {
                self.output_dir = value.clone();
                self.library_path = PathBuf::from(value);
            }
        }
        if let Some(value) = settings.get("category") {
            if ["Music", "Video", "Miscellaneous"].contains(&value.as_str()) {
                self.category = value.clone();
            }
        }
        if let Some(value) = settings.get("format") {
            if format_values_for_category(&self.category).contains(&value.as_str()) {
                self.format = value.clone();
            }
        }
        for (key, target) in [
            ("save_cover", &mut self.save_cover),
            ("save_metadata", &mut self.save_metadata),
            ("use_gpu", &mut self.use_gpu),
            ("normalize", &mut self.normalize),
            ("sidebar_collapsed", &mut self.sidebar_collapsed),
        ] {
            if let Some(value) = settings.get(key) {
                if let Ok(parsed) = value.parse::<bool>() {
                    *target = parsed;
                }
            }
        }
        if let Some(value) = settings.get("bitrate") {
            self.bitrate = value.clone();
        }
        if let Some(value) = settings.get("resolution") {
            self.resolution = value.clone();
        }
        self.sync_quality_for_format();
    }

    fn save_settings(&self) {
        let values = [
            ("output_dir", self.output_dir.as_str()),
            ("category", self.category.as_str()),
            ("format", self.format.as_str()),
            ("bitrate", self.bitrate.as_str()),
            ("resolution", self.resolution.as_str()),
            ("save_cover", if self.save_cover { "true" } else { "false" }),
            (
                "save_metadata",
                if self.save_metadata { "true" } else { "false" },
            ),
            ("use_gpu", if self.use_gpu { "true" } else { "false" }),
            ("normalize", if self.normalize { "true" } else { "false" }),
            (
                "sidebar_collapsed",
                if self.sidebar_collapsed {
                    "true"
                } else {
                    "false"
                },
            ),
        ];
        let content = values
            .iter()
            .map(|(key, value)| format!("{key}={value}\n"))
            .collect::<String>();
        let _ = fs::write(native_settings_path(&self.root), content);
    }

    fn poll_events(&mut self) {
        // Drain a small, fixed budget per frame. A conversion can produce
        // thousands of progress lines; draining an unbounded queue here was
        // the native UI's main source of input lag.
        for _ in 0..128 {
            let event = match self
                .events
                .as_ref()
                .and_then(|events| events.try_recv().ok())
            {
                Some(event) => event,
                None => break,
            };
            match event {
                Event::Output(line) => {
                    self.update_progress(&line);
                    self.logs.push_back(line);
                    while self.logs.len() > 5000 {
                        self.logs.pop_front();
                    }
                }
                Event::ConversionFinished(code) => {
                    let was_aborted = self
                        .abort_requested
                        .as_ref()
                        .map(|flag| flag.load(Ordering::Relaxed))
                        .unwrap_or(false);
                    self.running = false;
                    self.child = None;
                    self.abort_requested = None;
                    self.progress = if code == 0 { 1.0 } else { 0.0 };
                    self.status = if was_aborted {
                        "Conversion aborted".to_owned()
                    } else if code == 0 {
                        "Conversion complete".to_owned()
                    } else {
                        "Conversion failed — review Console".to_owned()
                    };
                }
                Event::UpdateFinished => {
                    self.update_checking = false;
                    self.status = "Update check complete — review Console".to_owned();
                }
                Event::LibraryLoaded(generation, entries) => {
                    if generation == self.library_scan_generation {
                        self.library_entries = entries;
                        self.library_scanning = false;
                    }
                }
                Event::LibraryScanFailed(generation) => {
                    if generation == self.library_scan_generation {
                        self.library_scanning = false;
                        self.status = "Could not read the converted library".to_owned();
                    }
                }
                Event::PlaylistLoaded(generation, title, items) => {
                    if generation == self.playlist_generation {
                        self.playlist_title = title;
                        self.playlist_selected = vec![true; items.len()];
                        self.playlist_items = items;
                        self.playlist_loading = false;
                        self.status = "Choose the playlist items to convert".to_owned();
                    }
                }
                Event::PlaylistLoadFailed(generation, message) => {
                    if generation == self.playlist_generation {
                        self.playlist_loading = false;
                        self.status = message;
                    }
                }
            }
        }
        while let Ok(event) = self.access_events.try_recv() {
            if event.generation != self.access_generation {
                continue;
            }
            self.auth_browser = event.browser.session_browser;
            self.auth_label = Some(event.browser.label.clone());
            self.access_server = None;
            self.access_link = None;
            self.status = if self.auth_browser.is_some() {
                format!("Account access confirmed through {}", event.browser.label)
            } else {
                format!(
                    "{} detected, but its session cannot be read automatically",
                    event.browser.label
                )
            };
        }
    }

    fn update_progress(&mut self, line: &str) {
        if let Some(end) = line.find('%') {
            if let Some(start) = line[..end].rfind('[').map(|index| index + 1) {
                if let Ok(value) = line[start..end].parse::<f32>() {
                    self.progress = (value / 100.0).clamp(0.0, 1.0);
                }
            }
        }
        let trimmed = line.trim();
        if !trimmed.is_empty() {
            self.status = trimmed.trim_matches('=').trim().to_owned();
        }
    }

    fn create_access_link(&mut self, ctx: &egui::Context) {
        if !is_supported_source_url(&self.source) {
            self.status = "Paste an online source URL first".to_owned();
            return;
        }
        self.access_server = None;
        self.access_generation += 1;
        self.auth_browser = None;
        self.auth_label = None;
        match AccessServer::start(&self.source, self.access_generation, self.access_tx.clone()) {
            Ok(server) => {
                self.access_link = Some(server.link.clone());
                ctx.copy_text(server.link.clone());
                open_url(&server.link);
                self.status = "Temporary access link copied and opened — paste it into any browser"
                    .to_owned();
                self.access_server = Some(server);
            }
            Err(error) => self.status = format!("Could not create access link: {error}"),
        }
    }

    fn paste_clipboard(&mut self) {
        match arboard::Clipboard::new().and_then(|mut clipboard| clipboard.get_text()) {
            Ok(text) => {
                self.source = text.trim().to_owned();
                self.selected_playlist_indexes = None;
                self.status = "Source link pasted".to_owned();
            }
            Err(_) => self.status = "Could not read the clipboard".to_owned(),
        }
    }

    fn browse_source(&mut self) {
        if let Some(path) = rfd::FileDialog::new()
            .set_title("Choose media file")
            .pick_file()
        {
            self.source = path.display().to_string();
            self.selected_playlist_indexes = None;
            self.status = "Local media file selected".to_owned();
        }
    }

    fn load_playlist_tracks(&mut self) {
        if self.running || self.playlist_loading {
            return;
        }
        if !is_supported_source_url(&self.source) {
            self.status = "Paste a playlist URL first".to_owned();
            return;
        }
        self.playlist_generation = self.playlist_generation.wrapping_add(1);
        let generation = self.playlist_generation;
        let python = find_python(&self.root);
        let root = self.root.clone();
        let mut args = vec![
            self.root.join("run_converter.py").display().to_string(),
            "--source".to_owned(),
            self.source.trim().to_owned(),
            "--list-playlist".to_owned(),
            "--no-update".to_owned(),
        ];
        if let Some(browser) = &self.auth_browser {
            args.extend(["--browser-session".to_owned(), browser.clone()]);
        }
        let (tx, rx) = mpsc::sync_channel(4);
        self.events = Some(rx);
        self.playlist_loading = true;
        self.playlist_items.clear();
        self.playlist_selected.clear();
        self.selected_playlist_indexes = None;
        self.status = "Loading playlist tracks...".to_owned();
        thread::spawn(move || {
            let mut command = Command::new(python);
            command.args(args).current_dir(root);
            #[cfg(target_os = "windows")]
            command.creation_flags(0x08000000);
            match command.output() {
                Ok(output) if output.status.success() => {
                    match parse_playlist_listing(&String::from_utf8_lossy(&output.stdout)) {
                        Ok((title, items)) if !items.is_empty() => {
                            let _ = tx.send(Event::PlaylistLoaded(generation, title, items));
                        }
                        Ok(_) => {
                            let _ = tx.send(Event::PlaylistLoadFailed(
                                generation,
                                "The playlist did not contain any usable tracks".to_owned(),
                            ));
                        }
                        Err(error) => {
                            let _ = tx.send(Event::PlaylistLoadFailed(generation, error));
                        }
                    }
                }
                Ok(output) => {
                    let detail = String::from_utf8_lossy(&output.stderr).trim().to_owned();
                    let message = if detail.is_empty() {
                        "Playlist loading failed — review Console".to_owned()
                    } else {
                        format!("Playlist loading failed: {detail}")
                    };
                    let _ = tx.send(Event::PlaylistLoadFailed(generation, message));
                }
                Err(error) => {
                    let _ = tx.send(Event::PlaylistLoadFailed(
                        generation,
                        format!("Could not start playlist loader: {error}"),
                    ));
                }
            }
        });
    }

    fn browse_output(&mut self) {
        if let Some(path) = rfd::FileDialog::new()
            .set_title("Choose export folder")
            .pick_folder()
        {
            self.output_dir = path.display().to_string();
        }
    }

    fn open_output_folder(&mut self) {
        let path = PathBuf::from(self.output_dir.trim());
        if path.is_dir() {
            open_folder_in_explorer(&path);
        } else {
            self.status = "The export folder does not exist yet".to_owned();
        }
    }

    fn set_category(&mut self, category: &str) {
        self.category = category.to_owned();
        let formats = format_values_for_category(&self.category);
        if !formats.contains(&self.format.as_str()) {
            self.format = formats[0].to_owned();
        }
        self.sync_quality_for_format();
    }

    fn sync_quality_for_format(&mut self) {
        let values = quality_values_for_format(&self.format);
        if !values.contains(&self.bitrate.as_str()) {
            self.bitrate = values[0].to_owned();
        }
    }

    fn start_conversion(&mut self) {
        if self.running {
            return;
        }
        if self.source.trim().is_empty() {
            self.status = "Paste a source URL or choose a local file first".to_owned();
            return;
        }
        self.sync_quality_for_format();
        self.save_settings();
        let python = find_python(&self.root);
        let root = self.root.clone();
        let mut args = vec![
            self.root.join("run_converter.py").display().to_string(),
            "--source".to_owned(),
            self.source.trim().to_owned(),
            "--format".to_owned(),
            self.format.clone(),
            "--output".to_owned(),
            self.output_dir.trim().to_owned(),
            "--bitrate".to_owned(),
            self.bitrate.clone(),
            "--sample-rate".to_owned(),
            "48000".to_owned(),
            "--resolution".to_owned(),
            self.resolution.clone(),
            "--category".to_owned(),
            self.category.clone(),
            "--no-update".to_owned(),
        ];
        if !self.use_gpu {
            args.push("--no-gpu".to_owned());
        }
        if !self.save_cover {
            args.push("--no-cover-art".to_owned());
        }
        if !self.save_metadata {
            args.push("--no-metadata".to_owned());
        }
        if self.normalize {
            args.push("--normalize".to_owned());
        }
        if let Some(browser) = &self.auth_browser {
            args.extend(["--browser-session".to_owned(), browser.clone()]);
        }
        if let Some(indexes) = &self.selected_playlist_indexes {
            args.extend([
                "--playlist".to_owned(),
                "--playlist-indexes".to_owned(),
                indexes.clone(),
            ]);
        }
        let (tx, rx) = mpsc::sync_channel(2048);
        let child_slot = Arc::new(Mutex::new(None));
        let abort = Arc::new(AtomicBool::new(false));
        let child_slot_thread = Arc::clone(&child_slot);
        let abort_thread = Arc::clone(&abort);
        thread::spawn(move || {
            let mut command = Command::new(&python);
            command
                .args(&args)
                .current_dir(root)
                .stdout(Stdio::piped())
                .stderr(Stdio::piped());
            #[cfg(target_os = "windows")]
            command.creation_flags(0x08000000);
            let mut child = match command.spawn() {
                Ok(child) => child,
                Err(error) => {
                    let _ = tx.send(Event::Output(format!(
                        "Could not start Python backend: {error}"
                    )));
                    let _ = tx.send(Event::ConversionFinished(1));
                    return;
                }
            };
            if let Some(stdout) = child.stdout.take() {
                spawn_reader(stdout, tx.clone());
            }
            if let Some(stderr) = child.stderr.take() {
                spawn_reader(stderr, tx.clone());
            }
            *child_slot_thread.lock().unwrap() = Some(child);
            let mut termination_requested = false;
            loop {
                let finished = {
                    let mut guard = child_slot_thread.lock().unwrap();
                    if let Some(child) = guard.as_mut() {
                        if abort_thread.load(Ordering::Relaxed) && !termination_requested {
                            terminate_process_tree(child);
                            termination_requested = true;
                        }
                        match child.try_wait() {
                            Ok(Some(status)) => Some(status.code().unwrap_or(1)),
                            Ok(None) => None,
                            Err(_) => Some(1),
                        }
                    } else {
                        Some(1)
                    }
                };
                if let Some(code) = finished {
                    child_slot_thread.lock().unwrap().take();
                    let _ = tx.send(Event::ConversionFinished(code));
                    break;
                }
                thread::sleep(Duration::from_millis(80));
            }
        });
        self.logs.push_back(format!(
            "Starting native conversion UI -> {}",
            self.format.to_uppercase()
        ));
        self.status = "Starting conversion...".to_owned();
        self.progress = 0.0;
        self.running = true;
        self.child = Some(child_slot);
        self.abort_requested = Some(abort);
        self.events = Some(rx);
    }

    fn abort(&mut self) {
        if let Some(abort) = &self.abort_requested {
            abort.store(true, Ordering::Relaxed);
        }
        if let Some(child) = &self.child {
            if let Ok(mut guard) = child.lock() {
                if let Some(child) = guard.as_mut() {
                    terminate_process_tree(child);
                }
            }
        }
        self.status = "Aborting conversion...".to_owned();
    }

    fn check_updates(&mut self) {
        if self.update_checking || self.running {
            return;
        }
        let python = find_python(&self.root);
        let root = self.root.clone();
        let (tx, rx) = mpsc::sync_channel(2048);
        self.events = Some(rx);
        self.update_checking = true;
        thread::spawn(move || {
            let script = "import json; from engine.updater import check_for_engine_updates, check_for_repo_updates; print(json.dumps({'engine': check_for_engine_updates(), 'repo': check_for_repo_updates()}))";
            let mut command = Command::new(python);
            command.arg("-c").arg(script).current_dir(root);
            #[cfg(target_os = "windows")]
            command.creation_flags(0x08000000);
            match command.output() {
                Ok(output) => {
                    for line in String::from_utf8_lossy(&output.stdout).lines() {
                        let _ = tx.send(Event::Output(line.to_owned()));
                    }
                    for line in String::from_utf8_lossy(&output.stderr).lines() {
                        let _ = tx.send(Event::Output(line.to_owned()));
                    }
                }
                Err(error) => {
                    let _ = tx.send(Event::Output(format!("Update check failed: {error}")));
                }
            }
            let _ = tx.send(Event::UpdateFinished);
        });
    }

    fn set_frontend_preference(&mut self, preference: &str) {
        match write_frontend_preference(&self.root, preference) {
            Ok(_) => {
                self.frontend_preference = preference.to_owned();
                self.status = format!(
                    "{} interface selected for the next launch",
                    if preference == "python" {
                        "Legacy Python"
                    } else {
                        "Rust"
                    }
                );
            }
            Err(error) => {
                self.status = format!("Could not save interface preference: {error}");
            }
        }
    }

    fn refresh_library(&mut self) {
        self.library_path = PathBuf::from(&self.output_dir);
        self.refresh_library_view();
    }

    fn refresh_library_view(&mut self) {
        self.library_scan_generation = self.library_scan_generation.wrapping_add(1);
        let generation = self.library_scan_generation;
        let path = self.library_path.clone();
        let (tx, rx) = mpsc::sync_channel(2);
        self.events = Some(rx);
        self.library_scanning = true;
        self.status = "Scanning converted library...".to_owned();
        thread::spawn(move || {
            if !path.exists() {
                let _ = tx.send(Event::LibraryScanFailed(generation));
                return;
            }
            let mut entries = Vec::new();
            collect_library_entries(&path, &mut entries);
            entries.sort_by(|left, right| {
                right.is_directory.cmp(&left.is_directory).then_with(|| {
                    left.path
                        .file_name()
                        .unwrap_or_default()
                        .to_string_lossy()
                        .to_ascii_lowercase()
                        .cmp(
                            &right
                                .path
                                .file_name()
                                .unwrap_or_default()
                                .to_string_lossy()
                                .to_ascii_lowercase(),
                        )
                })
            });
            if tx.send(Event::LibraryLoaded(generation, entries)).is_err() {
                return;
            }
        });
    }

    fn open_library_folder(&mut self, path: PathBuf) {
        let root = PathBuf::from(&self.output_dir);
        if path.starts_with(&root) && path.is_dir() {
            self.library_path = path;
            self.refresh_library_view();
        }
    }

    fn leave_library_folder(&mut self) {
        let root = PathBuf::from(&self.output_dir);
        if self.library_path != root {
            if let Some(parent) = self.library_path.parent() {
                if parent.starts_with(&root) || parent == root {
                    self.library_path = parent.to_owned();
                    self.refresh_library_view();
                }
            }
        }
    }

    fn render_sidebar(&mut self, ctx: &egui::Context) {
        let factor = ctx.animate_bool(egui::Id::new("native-sidebar"), !self.sidebar_collapsed);
        let width = 58.0 + factor * 132.0;
        egui::SidePanel::left("workspace-sidebar")
            .exact_width(width)
            .resizable(false)
            .frame(
                egui::Frame::none()
                    .fill(SURFACE_DARK)
                    .stroke(Stroke::new(1.0_f32, BORDER)),
            )
            .show(ctx, |ui| {
                ui.add_space(12.0);
                if sidebar_button(
                    ui,
                    self.sidebar_collapsed,
                    "⚡",
                    "Converter",
                    self.page == Page::Converter,
                ) {
                    self.page = Page::Converter;
                }
                if sidebar_button(
                    ui,
                    self.sidebar_collapsed,
                    "▣",
                    "Converted Library",
                    self.page == Page::Library,
                ) {
                    self.page = Page::Library;
                    self.refresh_library();
                }
                ui.add_space(18.0);
                if ui
                    .button(if self.sidebar_collapsed { "›" } else { "‹" })
                    .clicked()
                {
                    self.sidebar_collapsed = !self.sidebar_collapsed;
                }
                ui.with_layout(egui::Layout::bottom_up(egui::Align::Center), |ui| {
                    ui.add_space(10.0);
                    if self.sidebar_collapsed {
                        if ui.button("↻").on_hover_text("Check for Updates").clicked() {
                            self.check_updates();
                        }
                    } else if ui.button("↻  Check for Updates").clicked() {
                        self.check_updates();
                    }
                });
            });
    }

    fn render_converter(&mut self, ui: &mut egui::Ui, ctx: &egui::Context) {
        self.sync_quality_for_format();
        card(ui, |ui| {
            ui.horizontal(|ui| {
                ui.heading("Source Media URL or Local Path");
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    ui.label(RichText::new(source_label(&self.source)).color(BLUE));
                });
            });
            ui.add_space(8.0);
            ui.add(
                egui::TextEdit::singleline(&mut self.source)
                    .hint_text("Paste any media link or local path...")
                    .desired_width(f32::INFINITY),
            );
            ui.horizontal(|ui| {
                if ui.button("📋 Paste").clicked() {
                    self.paste_clipboard();
                }
                if ui.button("📁 Browse").clicked() {
                    self.browse_source();
                }
                if ui.button("📑 Playlist Tracks").clicked() {
                    self.load_playlist_tracks();
                }
            });
            ui.separator();
            ui.horizontal(|ui| {
                ui.label(
                    RichText::new("Account access (optional)")
                        .strong()
                        .color(MUTED),
                );
                if let Some(label) = &self.auth_label {
                    ui.label(
                        RichText::new(format!("Connected ({label}) — current session only"))
                            .color(SUCCESS),
                    );
                } else {
                    ui.label(RichText::new("Public only").color(BLUE));
                }
            });
            ui.label(RichText::new("Create a temporary link and open it in the browser whose session you want to use. No passwords or cookies are stored.").small().color(MUTED));
            ui.horizontal(|ui| {
                if self.auth_label.is_some() {
                    if ui.button("🔒 Clear Account Access").clicked() {
                        self.auth_label = None;
                        self.auth_browser = None;
                        self.access_server = None;
                        self.access_link = None;
                    }
                } else if ui.button("🔐 Create Access Link").clicked() {
                    self.create_access_link(ctx);
                }
                if let Some(link) = &self.access_link {
                    let mut display_link = link.clone();
                    ui.add(
                        egui::TextEdit::singleline(&mut display_link)
                            .desired_width(380.0)
                            .interactive(false),
                    );
                    if ui.button("Copy").clicked() {
                        ctx.copy_text(link.clone());
                    }
                }
            });
        });
        ui.add_space(10.0);
        card(ui, |ui| {
            ui.horizontal_wrapped(|ui| {
                ui.heading("Output Format & Transcode Parameters");
                ui.separator();
                ui.label("Save as");
                let format_values = format_values_for_category(&self.category);
                egui::ComboBox::from_id_salt("format")
                    .selected_text(self.format.to_uppercase())
                    .show_ui(ui, |ui| {
                        for value in format_values {
                            ui.selectable_value(
                                &mut self.format,
                                (*value).to_owned(),
                                value.to_uppercase(),
                            );
                        }
                    });
                ui.add_space(10.0);
                ui.label("Category");
                for (value, label) in [
                    ("Music", "Music"),
                    ("Video", "Video"),
                    ("Miscellaneous", "Misc"),
                ] {
                    let selected = self.category == value;
                    if ui
                        .add_sized(
                            Vec2::new(if value == "Miscellaneous" { 74.0 } else { 62.0 }, 26.0),
                            egui::Button::new(label).fill(if selected {
                                MAGENTA
                            } else {
                                SURFACE_DARK
                            }),
                        )
                        .clicked()
                    {
                        self.set_category(value);
                    }
                }
            });
            ui.add_space(8.0);
            ui.horizontal(|ui| {
                ui.label("Quality");
                let quality_values = quality_values_for_format(&self.format);
                egui::ComboBox::from_id_salt("bitrate")
                    .selected_text(quality_label(&self.bitrate))
                    .show_ui(ui, |ui| {
                        for value in quality_values {
                            ui.selectable_value(
                                &mut self.bitrate,
                                (*value).to_owned(),
                                quality_label(value),
                            );
                        }
                    });
                ui.label("Resolution");
                egui::ComboBox::from_id_salt("resolution")
                    .selected_text(&self.resolution)
                    .show_ui(ui, |ui| {
                        for value in ["original", "4k", "1440p", "1080p", "720p", "480p"] {
                            ui.selectable_value(&mut self.resolution, value.to_owned(), value);
                        }
                    });
            });
            ui.add_space(4.0);
            ui.checkbox(&mut self.use_gpu, "Hardware acceleration");
            ui.checkbox(&mut self.normalize, "Loudness Normalization");
            ui.checkbox(&mut self.save_cover, "Cover Art");
            ui.checkbox(&mut self.save_metadata, "Export metadata");
            ui.horizontal(|ui| {
                ui.label("Export folder");
                let browse_width = 78.0;
                let open_width = 62.0;
                let text_width =
                    (ui.available_width() - browse_width - open_width - 16.0).max(160.0);
                ui.add_sized(
                    Vec2::new(text_width, 24.0),
                    egui::TextEdit::singleline(&mut self.output_dir),
                );
                if ui
                    .add_sized(Vec2::new(browse_width, 24.0), egui::Button::new("Browse"))
                    .clicked()
                {
                    self.browse_output();
                }
                if ui
                    .add_sized(Vec2::new(open_width, 24.0), egui::Button::new("Open"))
                    .clicked()
                {
                    self.open_output_folder();
                }
            });
        });
        ui.add_space(10.0);
        ui.horizontal(|ui| {
            let button = egui::Button::new(
                RichText::new(if self.running {
                    "⏳ PROCESSING MEDIA..."
                } else {
                    "✨ CONVERT MEDIA"
                })
                .strong(),
            )
            .fill(if self.running { BLUE } else { MAGENTA });
            if ui
                .add_sized(Vec2::new(ui.available_width() - 100.0, 42.0), button)
                .clicked()
            {
                self.start_conversion();
            }
            if self.running && ui.button("Abort").clicked() {
                self.abort();
            }
        });
        ui.add(egui::ProgressBar::new(self.progress).show_percentage());
        ui.label(RichText::new(&self.status).color(MUTED));
        if !self.playlist_items.is_empty() {
            egui::Window::new("Playlist Tracks")
                .collapsible(false)
                .resizable(true)
                .default_size([620.0, 460.0])
                .show(ctx, |ui| {
                    ui.label(RichText::new(&self.playlist_title).strong().color(BLUE));
                    ui.horizontal(|ui| {
                        if ui.button("Select all").clicked() {
                            self.playlist_selected.fill(true);
                        }
                        if ui.button("Clear all").clicked() {
                            self.playlist_selected.fill(false);
                        }
                        ui.label(format!("{} item(s)", self.playlist_items.len()));
                    });
                    ui.separator();
                    egui::ScrollArea::vertical()
                        .max_height(330.0)
                        .show(ui, |ui| {
                            for (selected, item) in self
                                .playlist_selected
                                .iter_mut()
                                .zip(self.playlist_items.iter())
                            {
                                let suffix = if item.artist.is_empty() {
                                    String::new()
                                } else {
                                    format!(" — {}", item.artist)
                                };
                                ui.checkbox(
                                    selected,
                                    format!(
                                        "{}  {}{}  {}",
                                        item.index, item.title, suffix, item.duration
                                    ),
                                );
                            }
                        });
                    ui.separator();
                    ui.horizontal(|ui| {
                        if ui.button("Use selected tracks").clicked() {
                            let indexes = self
                                .playlist_selected
                                .iter()
                                .zip(self.playlist_items.iter())
                                .filter_map(|(selected, item)| {
                                    selected.then_some(item.index.to_string())
                                })
                                .collect::<Vec<_>>();
                            if indexes.is_empty() {
                                self.status = "Select at least one playlist track".to_owned();
                            } else {
                                self.selected_playlist_indexes = Some(indexes.join(","));
                                self.playlist_items.clear();
                                self.playlist_selected.clear();
                                self.status = "Playlist selection saved".to_owned();
                            }
                        }
                        if ui.button("Cancel").clicked() {
                            self.playlist_items.clear();
                            self.playlist_selected.clear();
                        }
                    });
                });
        }
    }

    fn render_library(&mut self, ui: &mut egui::Ui) {
        ui.heading("Converted Library");
        ui.label(
            RichText::new("Browse categories and playlists inside JaneConverter. Media actions stay beside each format tag.")
                .small()
                .color(MUTED),
        );
        ui.add_space(8.0);
        ui.horizontal(|ui| {
            if ui.button("‹ Back").clicked() {
                self.leave_library_folder();
            }
            if ui.button("↻ Refresh Library").clicked() {
                self.refresh_library_view();
            }
            ui.label(
                RichText::new(format!("Location: {}", self.library_path.display()))
                    .small()
                    .color(MUTED),
            );
        });
        ui.add_space(6.0);
        egui::ScrollArea::vertical().show(ui, |ui| {
            if self.library_entries.is_empty() {
                ui.label(
                    RichText::new(if self.library_scanning {
                        "Scanning converted media..."
                    } else {
                        "No converted media found in this folder."
                    })
                    .color(MUTED),
                );
            }
            let visible_entries = self
                .library_entries
                .iter()
                .take(MAX_LIBRARY_ROWS)
                .cloned()
                .collect::<Vec<_>>();
            for entry in visible_entries {
                if entry.is_directory {
                    ui.horizontal(|ui| {
                        let tag = if entry.is_playlist {
                            "📁 PLAYLIST"
                        } else {
                            "📁 FOLDER"
                        };
                        let tag_color = if entry.is_playlist { MAGENTA } else { BLUE };
                        ui.add_sized(
                            Vec2::new(92.0, 24.0),
                            egui::Button::new(RichText::new(tag).strong()).fill(tag_color),
                        );
                        if ui.button("Open").clicked() {
                            self.open_library_folder(entry.path.clone());
                        }
                        if ui.button("🗑").on_hover_text("Delete folder").clicked() {
                            self.pending_delete = Some(entry.path.clone());
                        }
                        let name = entry
                            .path
                            .file_name()
                            .map(|value| value.to_string_lossy().into_owned())
                            .unwrap_or_else(|| "Unnamed folder".to_owned());
                        ui.label(RichText::new(name).strong());
                        ui.label(
                            RichText::new(format!(
                                "{} item{} · {:.1} MB",
                                entry.media_count,
                                if entry.media_count == 1 { "" } else { "s" },
                                entry.total_bytes as f64 / (1024.0 * 1024.0)
                            ))
                            .small()
                            .color(MUTED),
                        );
                    });
                } else {
                    ui.horizontal(|ui| {
                        let extension = entry
                            .path
                            .extension()
                            .map(|value| value.to_string_lossy().to_uppercase())
                            .unwrap_or_else(|| "FILE".to_owned());
                        let tag_color =
                            if VIDEO_FORMATS.contains(&extension.to_ascii_lowercase().as_str()) {
                                MAGENTA
                            } else {
                                BLUE
                            };
                        ui.add_sized(
                            Vec2::new(64.0, 24.0),
                            egui::Button::new(RichText::new(extension).strong()).fill(tag_color),
                        );
                        if ui
                            .button("📁")
                            .on_hover_text("Open containing folder")
                            .clicked()
                        {
                            open_in_explorer(&entry.path);
                        }
                        if ui.button("🗑").on_hover_text("Delete").clicked() {
                            self.pending_delete = Some(entry.path.clone());
                        }
                        ui.label(
                            RichText::new(
                                entry
                                    .path
                                    .file_name()
                                    .map(|value| value.to_string_lossy().into_owned())
                                    .unwrap_or_else(|| "Unnamed media".to_owned()),
                            )
                            .strong(),
                        );
                        ui.label(
                            RichText::new(format!(
                                "{:.1} MB",
                                entry.total_bytes as f64 / (1024.0 * 1024.0)
                            ))
                            .small()
                            .color(MUTED),
                        );
                    });
                }
                ui.separator();
            }
            if self.library_entries.len() > MAX_LIBRARY_ROWS {
                ui.label(
                    RichText::new(format!(
                        "Showing the first {MAX_LIBRARY_ROWS} items to keep the library responsive."
                    ))
                    .small()
                    .color(MUTED),
                );
            }
        });
        if let Some(file) = self.pending_delete.clone() {
            egui::Window::new("Confirm deletion")
                .collapsible(false)
                .resizable(false)
                .show(ui.ctx(), |ui| {
                    ui.label(format!(
                        "Delete {}?",
                        file.file_name()
                            .and_then(|n| n.to_str())
                            .unwrap_or("this file")
                    ));
                    ui.horizontal(|ui| {
                        if ui.button("Cancel").clicked() {
                            self.pending_delete = None;
                        }
                        if ui.button("Delete").clicked() {
                            let result = if file.is_dir() {
                                fs::remove_dir_all(&file)
                            } else {
                                fs::remove_file(&file)
                            };
                            if let Err(error) = result {
                                self.status = format!("Could not delete item: {error}");
                            } else {
                                self.status = "Item deleted".to_owned();
                            }
                            self.pending_delete = None;
                            self.refresh_library_view();
                        }
                    });
                });
        }
    }
    fn render_console_panel(&mut self, ui: &mut egui::Ui, ctx: &egui::Context) {
        ui.horizontal(|ui| {
            ui.heading("Live Console");
            ui.label(
                RichText::new("Conversion and update activity")
                    .small()
                    .color(MUTED),
            );
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                if ui.button("Clear").clicked() {
                    self.logs.clear();
                }
                if ui.button("Copy Logs").clicked() {
                    ctx.copy_text(self.logs.iter().cloned().collect::<Vec<_>>().join("\n"));
                }
            });
        });
        ui.separator();
        egui::Frame::none()
            .fill(SURFACE_DARK)
            .stroke(Stroke::new(1.0_f32, BORDER))
            .rounding(egui::Rounding::same(8.0))
            .inner_margin(8.0)
            .show(ui, |ui| {
                ui.spacing_mut().item_spacing.y = 1.0;
                egui::ScrollArea::vertical()
                    .auto_shrink([false, false])
                    .stick_to_bottom(true)
                    .show(ui, |ui| {
                        if self.logs.is_empty() {
                            ui.label(
                                RichText::new("Ready — conversion output will appear here.")
                                    .monospace()
                                    .color(MUTED),
                            );
                        } else {
                            for line in &self.logs {
                                ui.add(
                                    egui::Label::new(RichText::new(line).monospace().color(MUTED))
                                        .wrap(),
                                );
                            }
                        }
                    });
            });
    }
}

impl eframe::App for JaneConverterApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        if !self.theme_initialized {
            apply_native_theme(ctx);
            self.logo_texture = load_logo_texture(ctx);
            self.theme_initialized = true;
        }
        self.poll_events();
        self.render_sidebar(ctx);
        egui::TopBottomPanel::top("header")
            .frame(
                egui::Frame::none()
                    .fill(Color32::from_rgb(2, 0, 10))
                    .inner_margin(egui::Margin::symmetric(18.0, 13.0)),
            )
            .show(ctx, |ui| {
                ui.horizontal(|ui| {
                    if let Some(logo) = &self.logo_texture {
                        ui.image((logo.id(), Vec2::splat(34.0)));
                    }
                    ui.heading(RichText::new("JaneConverter").color(TEXT));
                    ui.label(RichText::new("Universal Media Studio").color(MAGENTA));
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if ui.button("⚙ Interface").clicked() {
                            self.show_interface_settings = true;
                        }
                    });
                });
            });
        if self.page == Page::Converter {
            egui::TopBottomPanel::bottom("live-console")
                .exact_height(320.0)
                .frame(
                    egui::Frame::none()
                        .fill(SURFACE)
                        .stroke(Stroke::new(1.0_f32, BORDER))
                        .inner_margin(egui::Margin::symmetric(16.0, 10.0)),
                )
                .show(ctx, |ui| self.render_console_panel(ui, ctx));
        }
        egui::CentralPanel::default()
            .frame(
                egui::Frame::none()
                    .fill(Color32::from_rgb(2, 0, 10))
                    .inner_margin(24.0),
            )
            .show(ctx, |ui| {
                egui::ScrollArea::vertical()
                    .auto_shrink([false, false])
                    .show(ui, |ui| match self.page {
                        Page::Converter => self.render_converter(ui, ctx),
                        Page::Library => self.render_library(ui),
                    });
            });
        if self.show_interface_settings {
            let mut window_open = self.show_interface_settings;
            egui::Window::new("Interface preference")
                .open(&mut window_open)
                .resizable(false)
                .show(ctx, |ui| {
                    ui.label("Choose which interface opens from JaneConverter.exe next time.");
                    ui.add_space(6.0);
                    ui.label(
                        RichText::new(format!(
                            "Current preference: {}",
                            if self.frontend_preference == "python" {
                                "Legacy Python"
                            } else {
                                "Rust"
                            }
                        ))
                        .color(BLUE),
                    );
                    ui.add_space(8.0);
                    if ui.button("Use Rust interface").clicked() {
                        self.set_frontend_preference("rust");
                    }
                    if ui.button("Use legacy Python interface").clicked() {
                        self.set_frontend_preference("python");
                    }
                    ui.add_space(6.0);
                    ui.label(
                        RichText::new("Restart JaneConverter to apply the preference.")
                            .small()
                            .color(MUTED),
                    );
                });
            self.show_interface_settings = window_open;
        }
        if self.running
            || self.update_checking
            || self.access_server.is_some()
            || self.library_scanning
            || self.playlist_loading
        {
            ctx.request_repaint_after(Duration::from_millis(80));
        }
    }

    fn on_exit(&mut self, _gl: Option<&eframe::glow::Context>) {
        self.save_settings();
        if self.running || self.child.is_some() {
            self.abort();
        }
        self.access_server = None;
    }
}

fn apply_native_theme(ctx: &egui::Context) {
    apply_unicode_fonts(ctx);
    let mut visuals = egui::Visuals::dark();
    visuals.panel_fill = Color32::from_rgb(2, 0, 10);
    visuals.window_fill = SURFACE;
    visuals.faint_bg_color = SURFACE;
    visuals.extreme_bg_color = SURFACE_DARK;
    visuals.code_bg_color = SURFACE_DARK;
    visuals.hyperlink_color = BLUE;
    visuals.selection.bg_fill = MAGENTA;
    visuals.selection.stroke = Stroke::new(1.0_f32, TEXT);
    visuals.window_stroke = Stroke::new(1.0_f32, BORDER);
    for widget in [
        &mut visuals.widgets.noninteractive,
        &mut visuals.widgets.inactive,
        &mut visuals.widgets.hovered,
        &mut visuals.widgets.active,
        &mut visuals.widgets.open,
    ] {
        widget.bg_fill = SURFACE;
        widget.weak_bg_fill = SURFACE_DARK;
        widget.bg_stroke = Stroke::new(1.0_f32, BORDER);
        widget.fg_stroke = Stroke::new(1.0_f32, TEXT);
        widget.rounding = egui::Rounding::same(7.0);
    }
    visuals.widgets.hovered.bg_fill = Color32::from_rgb(40, 37, 64);
    visuals.widgets.active.bg_fill = MAGENTA;
    visuals.widgets.open.bg_fill = BLUE;
    ctx.set_visuals(visuals);
}

fn load_logo_texture(ctx: &egui::Context) -> Option<egui::TextureHandle> {
    let icon = eframe::icon_data::from_png_bytes(ORIGINAL_ICON_PNG).ok()?;
    let image = egui::ColorImage::from_rgba_unmultiplied(
        [icon.width as usize, icon.height as usize],
        &icon.rgba,
    );
    Some(ctx.load_texture(
        "janecoverter-original-icon",
        image,
        egui::TextureOptions::LINEAR,
    ))
}

fn apply_unicode_fonts(ctx: &egui::Context) {
    #[cfg(target_os = "windows")]
    {
        // These fonts ship with supported Windows installations and include
        // Japanese glyphs while preserving the native UI's normal font fallback.
        for font_path in [
            r"C:\Windows\Fonts\meiryo.ttc",
            r"C:\Windows\Fonts\YuGothM.ttc",
            r"C:\Windows\Fonts\msgothic.ttc",
        ] {
            if let Ok(bytes) = fs::read(font_path) {
                let mut fonts = egui::FontDefinitions::default();
                fonts.font_data.insert(
                    "windows-unicode".to_owned(),
                    egui::FontData::from_owned(bytes).into(),
                );
                for family in [egui::FontFamily::Proportional, egui::FontFamily::Monospace] {
                    fonts
                        .families
                        .entry(family)
                        .or_default()
                        // Keep the bundled UI font first so Windows path
                        // separators render as backslashes, not the Yen-shaped
                        // glyph used by some Japanese font faces. The Windows
                        // font remains available for Japanese filename fallback.
                        .push("windows-unicode".to_owned());
                }
                ctx.set_fonts(fonts);
                break;
            }
        }
    }
}

fn card(ui: &mut egui::Ui, content: impl FnOnce(&mut egui::Ui)) {
    egui::Frame::none()
        .fill(SURFACE)
        .stroke(Stroke::new(1.0_f32, BORDER))
        .rounding(egui::Rounding::same(10.0))
        .inner_margin(14.0)
        .show(ui, content);
}
fn sidebar_button(
    ui: &mut egui::Ui,
    collapsed: bool,
    icon: &str,
    label: &str,
    selected: bool,
) -> bool {
    let text = if collapsed {
        icon.to_owned()
    } else {
        format!("{icon}  {label}")
    };
    ui.add_sized(
        Vec2::new(ui.available_width(), 36.0),
        egui::Button::new(RichText::new(text).strong()).fill(if selected {
            MAGENTA
        } else {
            SURFACE_DARK
        }),
    )
    .clicked()
}
fn source_label(source: &str) -> &'static str {
    let source = source.to_ascii_lowercase();
    if source.is_empty() {
        "Ready for URL"
    } else if source.contains("facebook") {
        "Facebook Video"
    } else if source.contains("youtube") || source.contains("youtu.be") {
        "YouTube Video / Stream"
    } else if source.contains("soundcloud") {
        "SoundCloud Audio"
    } else {
        "Online Media"
    }
}

fn format_values_for_category(category: &str) -> &'static [&'static str] {
    match category {
        "Music" => AUDIO_FORMATS,
        "Video" => VIDEO_FORMATS,
        _ => ALL_FORMATS,
    }
}

fn quality_values_for_format(format: &str) -> &'static [&'static str] {
    match format {
        "wav" => WAV_QUALITY,
        "flac" => FLAC_QUALITY,
        "ogg" => OGG_QUALITY,
        "mp4" | "mkv" | "webm" | "mov" | "gif" => VIDEO_QUALITY,
        _ => AUDIO_BITRATES,
    }
}

fn quality_label(value: &str) -> &'static str {
    match value {
        "320k" => "320 kbps (Highest)",
        "256k" => "256 kbps (High)",
        "192k" => "192 kbps (Standard)",
        "128k" => "128 kbps (Compact)",
        "16-bit" => "16-bit",
        "24-bit" => "24-bit",
        "32-bit float" => "32-bit float",
        "q10" => "Quality 10 (Highest)",
        "q8" => "Quality 8 (High)",
        "q6" => "Quality 6 (Standard)",
        "q4" => "Quality 4 (Compact)",
        "best" => "Best quality",
        "high" => "High quality",
        "balanced" => "Balanced",
        "small" => "Smaller file",
        _ => "Default",
    }
}

fn is_supported_media(path: &Path) -> bool {
    let extension = path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    AUDIO_FORMATS.contains(&extension.as_str()) || VIDEO_FORMATS.contains(&extension.as_str())
}

fn collect_media_files(root: &Path, output: &mut Vec<PathBuf>) {
    let entries = match fs::read_dir(root) {
        Ok(entries) => entries,
        Err(_) => return,
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            collect_media_files(&path, output);
        } else if is_supported_media(&path) {
            output.push(path);
        }
    }
}

fn collect_library_entries(root: &Path, output: &mut Vec<LibraryEntry>) {
    let entries = match fs::read_dir(root) {
        Ok(entries) => entries,
        Err(_) => return,
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            if path
                .file_name()
                .map(|name| name.to_string_lossy().eq_ignore_ascii_case("metadata"))
                .unwrap_or(false)
            {
                continue;
            }
            let mut media_files = Vec::new();
            collect_media_files(&path, &mut media_files);
            if !media_files.is_empty() {
                let total_bytes = media_files
                    .iter()
                    .filter_map(|file| fs::metadata(file).ok().map(|metadata| metadata.len()))
                    .sum();
                let is_playlist = path.join("metadata").join("playlist_credits.txt").is_file();
                output.push(LibraryEntry {
                    path,
                    is_directory: true,
                    is_playlist,
                    media_count: media_files.len(),
                    total_bytes,
                });
            }
        } else if is_supported_media(&path) {
            let total_bytes = fs::metadata(&path)
                .map(|metadata| metadata.len())
                .unwrap_or(0);
            output.push(LibraryEntry {
                path,
                is_directory: false,
                is_playlist: false,
                media_count: 1,
                total_bytes,
            });
        }
    }
}
fn open_in_explorer(path: &Path) {
    #[cfg(target_os = "windows")]
    {
        let target = fs::canonicalize(path).unwrap_or_else(|_| path.to_path_buf());
        let explorer = std::env::var_os("WINDIR")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from(r"C:\Windows"))
            .join("explorer.exe");
        // Explorer expects /select,"full path" as one raw command-line
        // argument. Passing an unquoted path makes it truncate at spaces and
        // can fall back to the user's Documents folder.
        let argument = explorer_selection_argument(&target);
        let _ = Command::new(explorer).raw_arg(argument).spawn();
    }
}

fn explorer_selection_argument(path: &Path) -> String {
    format!("/select,\"{}\"", path.display())
}
fn open_folder_in_explorer(path: &Path) {
    #[cfg(target_os = "windows")]
    {
        let _ = Command::new("explorer.exe").arg(path).spawn();
    }
}
fn open_url(url: &str) {
    #[cfg(target_os = "windows")]
    {
        let _ = Command::new("cmd").args(["/C", "start", "", url]).spawn();
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = Command::new("xdg-open").arg(url).spawn();
    }
}
fn terminate_process_tree(child: &mut Child) {
    #[cfg(target_os = "windows")]
    {
        // Python launches ffmpeg as a descendant. Killing only Python leaves
        // that worker alive, so terminate the complete process tree on abort
        // and on application shutdown.
        let pid = child.id().to_string();
        let _ = Command::new("taskkill")
            .args(["/PID", &pid, "/T", "/F"])
            .creation_flags(0x08000000)
            .status();
    }
    let _ = child.kill();
}

fn spawn_reader<R: Read + Send + 'static>(reader: R, tx: EventSender) {
    thread::spawn(move || {
        for line in BufReader::new(reader).lines().map_while(Result::ok) {
            // Ordinary progress output is lossy by design. The UI remains
            // responsive under noisy ffmpeg output, while terminal events use
            // the reliable sender in the process supervisor.
            let _ = tx.try_send(Event::Output(line));
        }
    });
}
fn find_python(root: &Path) -> String {
    for candidate in [
        root.join(".venv/Scripts/python.exe"),
        root.join("venv/Scripts/python.exe"),
    ] {
        if candidate.exists() {
            return candidate.display().to_string();
        }
    }
    "python.exe".to_owned()
}

fn read_native_settings(root: &Path) -> HashMap<String, String> {
    let path = native_settings_path(root);
    let mut settings = HashMap::new();
    if let Ok(content) = fs::read_to_string(path) {
        for line in content.lines() {
            if let Some((key, value)) = line.split_once('=') {
                settings.insert(key.trim().to_owned(), value.trim().to_owned());
            }
        }
    }
    settings
}

fn native_settings_path(root: &Path) -> PathBuf {
    std::env::var_os("JANECONVERTER_DATA_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| root.to_owned())
        .join("native.settings")
}

fn default_data_dir(root: &Path) -> PathBuf {
    std::env::var_os("JANECONVERTER_DATA_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| root.to_owned())
}

fn frontend_preference_candidates(root: &Path) -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    if let Some(data_dir) = std::env::var_os("JANECONVERTER_DATA_DIR") {
        candidates.push(PathBuf::from(data_dir).join("frontend.preference"));
    }
    candidates.push(root.join("frontend.preference"));
    if let Some(local_app_data) = std::env::var_os("LOCALAPPDATA") {
        candidates.push(
            PathBuf::from(local_app_data)
                .join("JaneConverter")
                .join("frontend.preference"),
        );
    }
    candidates
}

fn read_frontend_preference(root: &Path) -> String {
    for candidate in frontend_preference_candidates(root) {
        if let Ok(value) = fs::read_to_string(candidate) {
            let value = value.trim().to_ascii_lowercase();
            if value == "python" || value == "rust" {
                return value;
            }
        }
    }
    "rust".to_owned()
}

fn write_frontend_preference(root: &Path, preference: &str) -> io::Result<PathBuf> {
    let mut last_error = None;
    for candidate in frontend_preference_candidates(root) {
        if let Some(parent) = candidate.parent() {
            if let Err(error) = fs::create_dir_all(parent) {
                last_error = Some(error);
                continue;
            }
        }
        match fs::write(&candidate, format!("{preference}\n")) {
            Ok(()) => return Ok(candidate),
            Err(error) => last_error = Some(error),
        }
    }
    Err(last_error.unwrap_or_else(|| {
        io::Error::new(
            io::ErrorKind::PermissionDenied,
            "no writable interface-preference location was available",
        )
    }))
}

fn app_root() -> PathBuf {
    let exe = std::env::current_exe().unwrap_or_else(|_| PathBuf::from("."));
    if let Some(parent) = exe.parent() {
        if parent.join("run_converter.py").exists() {
            return parent.to_owned();
        }
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap_or(Path::new("."))
        .to_owned()
}

fn main() -> eframe::Result {
    let window_icon = eframe::icon_data::from_png_bytes(ORIGINAL_ICON_PNG).unwrap_or_default();
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1180.0, 900.0])
            .with_min_inner_size([920.0, 760.0])
            .with_icon(Arc::new(window_icon)),
        ..Default::default()
    };
    eframe::run_native(
        "JaneConverter - Universal Media Studio",
        options,
        Box::new(|_cc| Ok(Box::new(JaneConverterApp::new(app_root())))),
    )
}

#[cfg(test)]
mod tests {
    use super::{
        detect_browser, explorer_selection_argument, html_escape, is_supported_source_url,
        parse_playlist_listing,
    };

    #[test]
    fn detects_known_browser_brands_before_generic_chromium_markers() {
        let detection =
            detect_browser("Mozilla/5.0 Chrome/138.0.0.0 Safari/537.36 Vivaldi/7.0", "");
        assert_eq!(detection.label, "Vivaldi");
        assert_eq!(detection.session_browser.as_deref(), Some("vivaldi"));
    }

    #[test]
    fn unknown_browsers_are_not_guessed() {
        let detection = detect_browser("CustomBrowser/1.0", "");
        assert_eq!(detection.label, "Unrecognized browser");
        assert!(detection.session_browser.is_none());
    }

    #[test]
    fn account_access_accepts_only_http_urls() {
        assert!(is_supported_source_url("https://example.com/video?id=1"));
        assert!(is_supported_source_url("HTTP://example.com"));
        assert!(!is_supported_source_url("javascript:alert(1)"));
        assert!(!is_supported_source_url("file:///C:/private.txt"));
        assert!(!is_supported_source_url("https://example.com\n<script>"));
    }

    #[test]
    fn html_escape_protects_account_access_page_markup() {
        assert_eq!(
            html_escape("<script a=\"b\">&"),
            "&lt;script a=&quot;b&quot;&gt;&amp;"
        );
    }

    #[test]
    fn playlist_listing_parser_preserves_unicode_and_indexes() {
        let listing = "PLAYLIST\t編集用素材\nENTRY\t2\t日本語のタイトル\t作曲者\t03:12\thttps://example.test/track\n";
        let (title, items) = parse_playlist_listing(listing).expect("listing should parse");
        assert_eq!(title, "編集用素材");
        assert_eq!(items[0].index, 2);
        assert_eq!(items[0].title, "日本語のタイトル");
    }

    #[test]
    fn explorer_selection_keeps_paths_with_spaces_together() {
        assert_eq!(
            explorer_selection_argument(std::path::Path::new(
                r"D:\Documents\GitHub Repo\JaneConverter\converted\file.mp4",
            )),
            r#"/select,"D:\Documents\GitHub Repo\JaneConverter\converted\file.mp4""#
        );
    }
}
