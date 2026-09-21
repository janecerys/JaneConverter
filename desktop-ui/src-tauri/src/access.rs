use crate::model::{AccessDiagnostic, AccessStatus, FetchedMedia};
use rand::{distr::Alphanumeric, Rng};
use serde::Deserialize;
use serde_json::json;
use std::fs::{self, File};
use std::io::{self, Read, Write};
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;
use url::Url;

const MAX_METADATA_BYTES: usize = 64 * 1024;
const MAX_CHUNK_BYTES: usize = 8 * 1024 * 1024;
const MAX_MEDIA_BYTES: u64 = 1024 * 1024 * 1024;
const MAX_CAPTURE_ITEMS: usize = 24;
const MAX_TOTAL_CAPTURE_BYTES: u64 = 2 * 1024 * 1024 * 1024;
const BRIDGE_HEADER: &str = "x-janeconverter-bridge";
const CAPTURE_ID_HEADER: &str = "x-janeconverter-capture-id";
const CAPTURE_OFFSET_HEADER: &str = "x-janeconverter-capture-offset";

pub struct AccessServer {
    pub link: String,
    source: Arc<Mutex<Option<String>>>,
    browser: Arc<Mutex<Option<String>>>,
    capture_state: Arc<Mutex<CaptureState>>,
    capture_root: PathBuf,
    stop: Arc<AtomicBool>,
    thread: Option<thread::JoinHandle<()>>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct CaptureMetadata {
    file_name: String,
    media_kind: String,
    mime_type: String,
    capture_mode: String,
    page_url: String,
    expected_bytes: Option<u64>,
    title: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct DiagnosticPayload {
    event: String,
    platform: Option<String>,
    host: Option<String>,
    media_kind: Option<String>,
    status: Option<u16>,
    bytes: Option<u64>,
    reason: Option<String>,
}

struct PendingCapture {
    id: String,
    path: PathBuf,
    file: File,
    bytes_written: u64,
    expected_bytes: Option<u64>,
    file_name: String,
    media_kind: String,
    mime_type: String,
    capture_mode: String,
    title: String,
}

struct CaptureState {
    pending: Option<PendingCapture>,
    paths: Vec<PathBuf>,
    fetched: Vec<FetchedMedia>,
    total_bytes: u64,
    diagnostics: Vec<AccessDiagnostic>,
    next_diagnostic_id: u64,
}

fn media_descriptor(path: &Path) -> Option<(&'static str, &'static str)> {
    match path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase()
        .as_str()
    {
        "mp4" => Some(("video", "video/mp4")),
        "mkv" => Some(("video", "video/x-matroska")),
        "webm" => Some(("video", "video/webm")),
        "mov" => Some(("video", "video/quicktime")),
        "gif" => Some(("video", "image/gif")),
        "mp3" => Some(("audio", "audio/mpeg")),
        "m4a" => Some(("audio", "audio/mp4")),
        "aac" => Some(("audio", "audio/aac")),
        "flac" => Some(("audio", "audio/flac")),
        "wav" => Some(("audio", "audio/wav")),
        "ogg" => Some(("audio", "audio/ogg")),
        "jpg" | "jpeg" => Some(("image", "image/jpeg")),
        "png" => Some(("image", "image/png")),
        "webp" => Some(("image", "image/webp")),
        _ => None,
    }
}

pub fn scan_fetched_media(root: &Path) -> Vec<FetchedMedia> {
    let Ok(entries) = fs::read_dir(root) else {
        return Vec::new();
    };
    let mut items = entries
        .flatten()
        .filter_map(|entry| {
            let path = entry.path();
            if !entry.file_type().ok()?.is_file() {
                return None;
            }
            let (media_kind, mime_type) = media_descriptor(&path)?;
            let size = entry.metadata().ok()?.len();
            let name = path.file_name()?.to_string_lossy().into_owned();
            let title = path.file_stem()?.to_string_lossy().into_owned();
            Some(FetchedMedia {
                path: path.to_string_lossy().into_owned(),
                name,
                media_kind: media_kind.into(),
                mime_type: mime_type.into(),
                capture_mode: "saved".into(),
                title,
                size,
            })
        })
        .collect::<Vec<_>>();
    items.sort_by(|left, right| {
        left.name
            .to_ascii_lowercase()
            .cmp(&right.name.to_ascii_lowercase())
    });
    items
}

impl Drop for AccessServer {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Relaxed);
        if let Some(handle) = self.thread.take() {
            let _ = handle.join();
        }
        if let Ok(mut state) = self.capture_state.lock() {
            if let Some(pending) = state.pending.take() {
                let _ = fs::remove_file(pending.path);
            }
        }
    }
}

impl AccessServer {
    pub fn status(&self) -> AccessStatus {
        AccessStatus {
            active: true,
            link: self.link.clone(),
            browser: self
                .browser
                .lock()
                .ok()
                .and_then(|value| value.clone())
                .unwrap_or_default(),
            source: self.source.lock().ok().and_then(|value| value.clone()),
            bridge_connected: self
                .capture_state
                .lock()
                .map(|value| !value.paths.is_empty())
                .unwrap_or(false),
            capture_count: self
                .capture_state
                .lock()
                .map(|value| value.fetched.len())
                .unwrap_or(0),
            captured_media_kind: self
                .capture_state
                .lock()
                .ok()
                .and_then(|value| value.fetched.last().map(|item| item.media_kind.clone())),
        }
    }

    pub fn fetched_media(&self) -> Vec<FetchedMedia> {
        let mut items = scan_fetched_media(&self.capture_root);
        if let Ok(state) = self.capture_state.lock() {
            for captured in &state.fetched {
                if let Some(item) = items.iter_mut().find(|item| item.path == captured.path) {
                    *item = captured.clone();
                }
            }
        }
        items
    }

    pub fn diagnostics(&self) -> Vec<AccessDiagnostic> {
        self.capture_state
            .lock()
            .map(|value| value.diagnostics.clone())
            .unwrap_or_default()
    }

    fn validated_capture_path(&self, requested: &str) -> Result<PathBuf, String> {
        let root = fs::canonicalize(&self.capture_root)
            .map_err(|error| format!("The capture workspace is unavailable: {error}"))?;
        let target = fs::canonicalize(requested.trim())
            .map_err(|error| format!("That fetched media file no longer exists: {error}"))?;
        if !target.starts_with(&root) || !target.is_file() {
            return Err("That fetched media file is outside the active capture session.".into());
        }
        Ok(target)
    }

    pub fn fetched_media_thumbnail(&self, path: &str) -> Result<Option<String>, String> {
        let target = self.validated_capture_path(path)?;
        crate::library::thumbnail(
            self.capture_root.to_string_lossy().as_ref(),
            target.to_string_lossy().as_ref(),
        )
    }

    pub fn discard_fetched_media(&self, path: &str) -> Result<(), String> {
        let target = self.validated_capture_path(path)?;
        match fs::remove_file(&target) {
            Ok(()) => {}
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(error) => return Err(format!("Could not discard the fetched media: {error}")),
        }
        let mut state = self
            .capture_state
            .lock()
            .map_err(|_| "The capture registry is unavailable.".to_owned())?;
        state
            .paths
            .retain(|candidate| fs::canonicalize(candidate).ok().as_ref() != Some(&target));
        if let Some(item_index) = state
            .fetched
            .iter()
            .position(|item| item.path == path.trim() || item.path == target.to_string_lossy())
        {
            let item = state.fetched.remove(item_index);
            state.total_bytes = state.total_bytes.saturating_sub(item.size);
        }
        Ok(())
    }
    pub fn captured_media_path(
        &self,
        source: &str,
        requested_path: Option<&str>,
    ) -> Option<PathBuf> {
        if let Ok(bound_source) = self.source.lock() {
            if let Some(bound_source) = bound_source.as_deref() {
                if !source.trim().is_empty() && bound_source.trim() != source.trim() {
                    return None;
                }
            }
        }
        self.capture_state
            .lock()
            .ok()
            .and_then(|value| {
                requested_path
                    .and_then(|requested| {
                        value
                            .paths
                            .iter()
                            .find(|path| path.to_string_lossy() == requested)
                            .cloned()
                    })
                    .or_else(|| value.paths.last().cloned())
            })
            .filter(|path| path.is_file())
    }
}

fn html_escape(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace(char::from(39), "&#39;")
}

fn browser_label_from_signal(signal: &str) -> String {
    let value = signal.to_ascii_lowercase();
    if value.contains("vivaldi") {
        "Vivaldi".into()
    } else if value.contains("brave") {
        "Brave".into()
    } else if value.contains("edg/") {
        "Edge".into()
    } else if value.contains("firefox/") {
        "Firefox".into()
    } else if value.contains("chrome/") {
        "Chrome".into()
    } else if value.contains("safari/") {
        "Safari".into()
    } else {
        "Unknown browser".into()
    }
}

fn http_response(
    status: u16,
    reason: &str,
    content_type: &str,
    body: &str,
    cors_origin: Option<&str>,
) -> String {
    let cors_headers = cors_origin
        .map(|origin| {
            format!(
                "Access-Control-Allow-Origin: {origin}\r\nVary: Origin\r\nAccess-Control-Allow-Headers: content-type, {BRIDGE_HEADER}, {CAPTURE_ID_HEADER}, {CAPTURE_OFFSET_HEADER}\r\nAccess-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
            )
        })
        .unwrap_or_default();
    format!(
        "HTTP/1.1 {status} {reason}\r\nContent-Type: {content_type}\r\nCache-Control: no-store\r\nContent-Security-Policy: default-src 'none'; style-src 'unsafe-inline'\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\n{cors_headers}Content-Length: {}\r\nConnection: close\r\n\r\n{}",
        body.as_bytes().len(),
        body,
    )
}

fn access_page(title: &str, content: &str) -> String {
    format!(
        r#"<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><title>{title}</title><style>body{{background:#080711;color:#ededed;font:16px Segoe UI,Arial,sans-serif;max-width:640px;margin:12vh auto;padding:0 24px;line-height:1.55}}h1{{font-size:28px}}a{{color:#93c5fd}}.primary,.confirm{{display:inline-block;padding:11px 16px;border-radius:8px;color:#fff;text-decoration:none;margin:4px 8px 4px 0}}.primary{{background:#1f5fae}}.confirm{{background:#b3265f}}.note{{color:#9ca3af;font-size:13px}}</style></head><body><h1>{title}</h1>{content}</body></html>"#
    )
}

struct HttpRequest {
    method: String,
    path: String,
    headers: String,
    body: Vec<u8>,
}

fn read_request(stream: &mut std::net::TcpStream) -> Result<HttpRequest, String> {
    stream
        .set_read_timeout(Some(Duration::from_secs(2)))
        .map_err(|error| error.to_string())?;
    let mut bytes = Vec::new();
    let mut header_end = None;
    let mut content_length = 0usize;
    loop {
        let mut chunk = [0u8; 8192];
        let read = stream.read(&mut chunk).map_err(|error| error.to_string())?;
        if read == 0 {
            break;
        }
        bytes.extend_from_slice(&chunk[..read]);
        if bytes.len() > MAX_CHUNK_BYTES + MAX_METADATA_BYTES + 16 * 1024 {
            return Err("The browser bridge request is too large.".into());
        }
        if header_end.is_none() {
            if let Some(position) = bytes.windows(4).position(|window| window == b"\r\n\r\n") {
                let end = position + 4;
                let headers = String::from_utf8_lossy(&bytes[..position]);
                content_length = headers
                    .lines()
                    .find_map(|line| {
                        let (name, value) = line.split_once(':')?;
                        name.trim()
                            .eq_ignore_ascii_case("content-length")
                            .then(|| value.trim().parse::<usize>().ok())
                            .flatten()
                    })
                    .unwrap_or(0);
                if content_length > MAX_CHUNK_BYTES {
                    return Err("The browser bridge request is too large.".into());
                }
                header_end = Some(end);
            }
        }
        if let Some(end) = header_end {
            if bytes.len() >= end + content_length {
                let headers = String::from_utf8_lossy(&bytes[..end - 4]).into_owned();
                let request_line = headers.lines().next().unwrap_or_default();
                let mut fields = request_line.split_whitespace();
                let method = fields.next().unwrap_or_default().to_owned();
                let path = fields.next().unwrap_or_default().to_owned();
                return Ok(HttpRequest {
                    method,
                    path,
                    headers,
                    body: bytes[end..end + content_length].to_vec(),
                });
            }
        }
    }
    Err("The browser bridge request was incomplete.".into())
}

fn send_html(stream: &mut std::net::TcpStream, status: u16, reason: &str, body: &str) {
    let _ = stream.write_all(
        http_response(status, reason, "text/html; charset=utf-8", body, None).as_bytes(),
    );
}

fn send_json(stream: &mut std::net::TcpStream, status: u16, reason: &str, body: &str) {
    let _ = stream.write_all(
        http_response(
            status,
            reason,
            "application/json; charset=utf-8",
            body,
            None,
        )
        .as_bytes(),
    );
}

fn send_json_cors(
    stream: &mut std::net::TcpStream,
    status: u16,
    reason: &str,
    origin: &str,
    body: &str,
) {
    let _ = stream.write_all(
        http_response(
            status,
            reason,
            "application/json; charset=utf-8",
            body,
            Some(origin),
        )
        .as_bytes(),
    );
}

fn diagnostic_value(value: Option<&str>, label: &str, max_len: usize) -> Result<String, String> {
    let value = value.unwrap_or_default().trim().to_ascii_lowercase();
    if value.is_empty()
        || value.len() > max_len
        || !value.chars().all(|character| {
            character.is_ascii_lowercase()
                || character.is_ascii_digit()
                || matches!(character, '.' | '-')
        })
    {
        return Err(format!("The browser diagnostic {label} was invalid."));
    }
    Ok(value)
}

fn diagnostic_reason(value: Option<&str>) -> Result<String, String> {
    let value = value.unwrap_or_default().trim().to_ascii_lowercase();
    if value.is_empty()
        || value.len() > 64
        || !value.chars().all(|character| {
            character.is_ascii_lowercase()
                || character.is_ascii_digit()
                || matches!(character, ' ' | '.' | '-')
        })
    {
        return Err("The browser diagnostic reason was invalid.".into());
    }
    Ok(value)
}

fn diagnostic_message(payload: &DiagnosticPayload) -> Result<String, String> {
    let host = || diagnostic_value(payload.host.as_deref(), "host", 253);
    let kind = || {
        let value = diagnostic_value(payload.media_kind.as_deref(), "media type", 12)?;
        matches!(value.as_str(), "video" | "audio" | "image")
            .then_some(value)
            .ok_or_else(|| "The browser diagnostic media type was invalid.".to_owned())
    };
    let bytes = || {
        payload
            .bytes
            .filter(|value| *value <= MAX_MEDIA_BYTES)
            .ok_or_else(|| "The browser diagnostic size was invalid.".to_owned())
    };
    let byte_label = |value: u64| {
        if value < 1024 * 1024 {
            format!("{} KB", value / 1024)
        } else {
            format!("{:.1} MB", value as f64 / (1024.0 * 1024.0))
        }
    };
    match payload.event.as_str() {
        "session_fetch_started" => {
            let platform = diagnostic_value(payload.platform.as_deref(), "platform", 32)?;
            if !matches!(platform.as_str(), "facebook" | "instagram" | "x" | "tiktok" | "youtube" | "reddit" | "vimeo" | "twitch" | "dailymotion" | "soundcloud" | "rumble") {
                return Err("The browser diagnostic platform was invalid.".into());
            }
            Ok(format!("Browser session fetch started: {platform} via {} ({}).", host()?, kind()?))
        }
        "media_response" => {
            let status = payload.status.filter(|value| (100..=599).contains(value)).ok_or_else(|| "The browser diagnostic status was invalid.".to_owned())?;
            let size = payload.bytes.map(byte_label).unwrap_or_else(|| "unknown size".into());
            Ok(format!("Media response accepted: {} returned HTTP {status} ({size}).", host()?))
        }
        "candidate_rejected" => Ok(format!("Media candidate rejected: {} was not the requested {} response.", host()?, kind()?)),
        "upload_progress" => Ok(format!("Temporary media upload progress: {} received.", byte_label(bytes()?))),
        "upload_complete" => Ok(format!("Temporary media upload complete: {} received.", byte_label(bytes()?))),
        "session_fetch_failed" => Ok(format!("Browser session fetch failed for {} ({}); JaneConverter will use its safe rendered fallback if available.", host()?, kind()?)),
        "network_mode_enabled" => {
            let platform = diagnostic_value(payload.platform.as_deref(), "platform", 32)?;
            Ok(format!("Network Compatibility Mode attached to {} for {}.", host()?, platform))
        }
        "network_probe" => {
            let status = payload.status.filter(|value| (100..=599).contains(value)).ok_or_else(|| "The browser diagnostic status was invalid.".to_owned())?;
            let size = payload.bytes.map(byte_label).unwrap_or_else(|| "unknown size".into());
            Ok(format!("Network media probe: {} returned HTTP {status} ({size}).", host()?))
        }
        "network_body_ready" => Ok(format!("Network media body accepted from {} ({}).", host()?, byte_label(bytes()?))),
        "network_discarded" => {
            let reason = diagnostic_reason(payload.reason.as_deref())?;
            Ok(format!("Network media discarded from {}: {reason}.", host()?))
        }
        "network_capture_failed" => {
            let reason = diagnostic_reason(payload.reason.as_deref())?;
            Ok(format!("Network media capture failed for {}: {reason}.", host()?))
        }
        _ => Err("The browser diagnostic event was not allowed.".into()),
    }
}

fn record_diagnostic(
    capture_state: &Arc<Mutex<CaptureState>>,
    payload: DiagnosticPayload,
) -> Result<(), String> {
    let message = diagnostic_message(&payload)?;
    let mut state = capture_state
        .lock()
        .map_err(|_| "The capture registry is unavailable.".to_owned())?;
    let id = state.next_diagnostic_id;
    state.next_diagnostic_id = state.next_diagnostic_id.saturating_add(1);
    if state.diagnostics.len() >= 256 {
        state.diagnostics.remove(0);
    }
    state.diagnostics.push(AccessDiagnostic { id, message });
    Ok(())
}

fn serve(
    listener: TcpListener,
    token: String,
    source: Arc<Mutex<Option<String>>>,
    default_browser: Option<String>,
    browser: Arc<Mutex<Option<String>>>,
    confirmed: Arc<AtomicBool>,
    bridge_nonce: String,
    capture_state: Arc<Mutex<CaptureState>>,
    capture_root: PathBuf,
    stop: Arc<AtomicBool>,
) {
    let _ = listener.set_nonblocking(true);
    while !stop.load(Ordering::Relaxed) {
        match listener.accept() {
            Ok((mut stream, _)) => {
                let request = match read_request(&mut stream) {
                    Ok(request) => request,
                    Err(error) => {
                        send_json(
                            &mut stream,
                            413,
                            "Payload Too Large",
                            &json!({"error": error}).to_string(),
                        );
                        continue;
                    }
                };
                let base = format!("/access/{token}");
                if request.method == "OPTIONS" && request.path.starts_with(&base) {
                    match bridge_origin(&request.headers) {
                        Ok(Some(origin)) => send_json_cors(&mut stream, 200, "OK", &origin, "{}"),
                        Ok(None) => send_json(&mut stream, 200, "OK", "{}"),
                        Err(error) => send_json(
                            &mut stream,
                            403,
                            "Forbidden",
                            &json!({"error": error}).to_string(),
                        ),
                    }
                    continue;
                }
                if request.method == "GET" && request.path == format!("{base}/ready") {
                    let signal = browser_signal_from_headers(&request.headers);
                    let label = resolve_browser_label(&signal, default_browser.as_deref());
                    if let Ok(mut value) = browser.lock() {
                        *value = Some(label.clone());
                    }
                    confirmed.store(true, Ordering::Relaxed);
                    send_html(&mut stream, 200, "OK", &access_page("Access confirmed", &format!("<p>Browser detected: <strong>{}</strong>.</p><p>Return to JaneConverter, open the Browser Capture extension, and choose <strong>Capture current media</strong> or <strong>Capture story sequence</strong>.</p><p class=\"note\">Only selected media bytes are sent to this app. No password, cookie, cache, or browser profile data is read or uploaded.</p>", html_escape(&label))));
                    continue;
                }
                if request.method == "GET" && request.path == format!("{base}/bridge/challenge") {
                    let origin = match bridge_origin(&request.headers) {
                        Ok(origin) => origin,
                        Err(error) => {
                            send_json(
                                &mut stream,
                                403,
                                "Forbidden",
                                &json!({"error": error}).to_string(),
                            );
                            continue;
                        }
                    };
                    if !confirmed.load(Ordering::Relaxed) {
                        send_json_cors_or_plain(
                            &mut stream,
                            409,
                            "Conflict",
                            origin.as_deref(),
                            &json!({"error": "Confirm account access in the browser first."})
                                .to_string(),
                        );
                    } else {
                        let count = capture_state
                            .lock()
                            .map(|value| value.paths.len())
                            .unwrap_or(0);
                        let source_url = source
                            .lock()
                            .ok()
                            .and_then(|value| value.clone())
                            .unwrap_or_default();
                        let response = json!({
                            "sourceUrl": source_url,
                            "confirmed": true,
                            "connected": count > 0,
                            "captureCount": count,
                            "bridgeToken": bridge_nonce.clone()
                        });
                        send_json_cors_or_plain(
                            &mut stream,
                            200,
                            "OK",
                            origin.as_deref(),
                            &response.to_string(),
                        );
                    }
                    continue;
                }
                if request.method == "POST" && request.path == format!("{base}/bridge/diagnostic") {
                    let origin = match bridge_ready(&request.headers, &bridge_nonce, &confirmed) {
                        Ok(origin) => origin,
                        Err((status, error, origin)) => {
                            send_json_cors_or_plain(
                                &mut stream,
                                status,
                                "Request rejected",
                                origin.as_deref(),
                                &json!({"error": error}).to_string(),
                            );
                            continue;
                        }
                    };
                    if request.body.is_empty() || request.body.len() > MAX_METADATA_BYTES {
                        send_json_cors_or_plain(
                            &mut stream,
                            413,
                            "Payload Too Large",
                            origin.as_deref(),
                            &json!({"error": "The browser diagnostic was empty or too large."})
                                .to_string(),
                        );
                        continue;
                    }
                    let payload = match serde_json::from_slice::<DiagnosticPayload>(&request.body) {
                        Ok(payload) => payload,
                        Err(_) => {
                            send_json_cors_or_plain(
                                &mut stream,
                                400,
                                "Bad Request",
                                origin.as_deref(),
                                &json!({"error": "The browser diagnostic was not valid JSON."})
                                    .to_string(),
                            );
                            continue;
                        }
                    };
                    match record_diagnostic(&capture_state, payload) {
                        Ok(()) => send_json_cors_or_plain(
                            &mut stream,
                            200,
                            "OK",
                            origin.as_deref(),
                            "{\"ok\":true}",
                        ),
                        Err(error) => send_json_cors_or_plain(
                            &mut stream,
                            400,
                            "Bad Request",
                            origin.as_deref(),
                            &json!({"error": error}).to_string(),
                        ),
                    }
                    continue;
                }
                if request.method == "POST"
                    && request.path == format!("{base}/bridge/capture/start")
                {
                    let origin = match bridge_ready(&request.headers, &bridge_nonce, &confirmed) {
                        Ok(origin) => origin,
                        Err((status, error, origin)) => {
                            send_json_cors_or_plain(
                                &mut stream,
                                status,
                                "Request rejected",
                                origin.as_deref(),
                                &json!({"error": error}).to_string(),
                            );
                            continue;
                        }
                    };
                    if request.body.len() > MAX_METADATA_BYTES {
                        send_json_cors_or_plain(
                            &mut stream,
                            413,
                            "Payload Too Large",
                            origin.as_deref(),
                            &json!({"error": "The browser capture metadata is too large."})
                                .to_string(),
                        );
                        continue;
                    }
                    let current_source = source.lock().ok().and_then(|value| value.clone());
                    let metadata =
                        match validate_capture_metadata(&request.body, current_source.as_deref()) {
                            Ok(metadata) => metadata,
                            Err(error) => {
                                send_json_cors_or_plain(
                                    &mut stream,
                                    400,
                                    "Bad Request",
                                    origin.as_deref(),
                                    &json!({"error": error}).to_string(),
                                );
                                continue;
                            }
                        };
                    if current_source.is_none() {
                        if let Ok(mut bound_source) = source.lock() {
                            if bound_source.is_none() {
                                *bound_source = Some(metadata.page_url.clone());
                            }
                        }
                    }
                    let mut state = match capture_state.lock() {
                        Ok(state) => state,
                        Err(_) => {
                            send_json_cors_or_plain(
                                &mut stream,
                                500,
                                "Internal Server Error",
                                origin.as_deref(),
                                &json!({"error": "The capture registry is unavailable."})
                                    .to_string(),
                            );
                            continue;
                        }
                    };
                    if state.paths.len() + usize::from(state.pending.is_some()) >= MAX_CAPTURE_ITEMS
                        || state.pending.is_some()
                    {
                        send_json_cors_or_plain(&mut stream, 409, "Conflict", origin.as_deref(), &json!({"error": "Another browser capture is already uploading or the session is full."}).to_string());
                        continue;
                    }
                    let id: String = rand::rng()
                        .sample_iter(&Alphanumeric)
                        .take(24)
                        .map(char::from)
                        .collect();
                    let file_name = PathBuf::from(&metadata.file_name);
                    let suffix = file_name
                        .extension()
                        .and_then(|value| value.to_str())
                        .unwrap_or("bin");
                    let path = capture_root.join(format!("{id}.{suffix}"));
                    let file = match File::create(&path) {
                        Ok(file) => file,
                        Err(error) => {
                            send_json_cors_or_plain(&mut stream, 500, "Internal Server Error", origin.as_deref(), &json!({"error": format!("Could not create the fetched media file: {error}")}).to_string());
                            continue;
                        }
                    };
                    state.pending = Some(PendingCapture {
                        id: id.clone(),
                        path,
                        file,
                        bytes_written: 0,
                        expected_bytes: metadata.expected_bytes,
                        file_name: metadata.file_name.clone(),
                        media_kind: metadata.media_kind.clone(),
                        mime_type: metadata.mime_type.clone(),
                        capture_mode: metadata.capture_mode.clone(),
                        title: metadata.title.clone(),
                    });
                    send_json_cors_or_plain(
                        &mut stream,
                        200,
                        "OK",
                        origin.as_deref(),
                        &json!({"captureId": id}).to_string(),
                    );
                    continue;
                }
                if request.method == "POST"
                    && request.path == format!("{base}/bridge/capture/chunk")
                {
                    let origin = match bridge_ready(&request.headers, &bridge_nonce, &confirmed) {
                        Ok(origin) => origin,
                        Err((status, error, origin)) => {
                            send_json_cors_or_plain(
                                &mut stream,
                                status,
                                "Request rejected",
                                origin.as_deref(),
                                &json!({"error": error}).to_string(),
                            );
                            continue;
                        }
                    };
                    let capture_id =
                        header_value(&request.headers, CAPTURE_ID_HEADER).unwrap_or_default();
                    let offset = header_value(&request.headers, CAPTURE_OFFSET_HEADER)
                        .and_then(|value| value.parse::<u64>().ok());
                    let mut state = match capture_state.lock() {
                        Ok(state) => state,
                        Err(_) => {
                            send_json_cors_or_plain(
                                &mut stream,
                                500,
                                "Internal Server Error",
                                origin.as_deref(),
                                &json!({"error": "The capture registry is unavailable."})
                                    .to_string(),
                            );
                            continue;
                        }
                    };
                    let total_bytes = state.total_bytes;
                    let Some(current) = state.pending.as_mut() else {
                        send_json_cors_or_plain(
                            &mut stream,
                            400,
                            "Bad Request",
                            origin.as_deref(),
                            &json!({"error": "The browser capture upload is not active."})
                                .to_string(),
                        );
                        continue;
                    };
                    let next_size = current
                        .bytes_written
                        .saturating_add(request.body.len() as u64);
                    if capture_id != current.id || offset != Some(current.bytes_written) {
                        send_json_cors_or_plain(
                            &mut stream,
                            400,
                            "Bad Request",
                            origin.as_deref(),
                            &json!({"error": "The browser capture chunk offset was out of order."})
                                .to_string(),
                        );
                        continue;
                    }
                    if request.body.is_empty()
                        || request.body.len() > MAX_CHUNK_BYTES
                        || next_size > MAX_MEDIA_BYTES
                        || total_bytes.saturating_add(next_size) > MAX_TOTAL_CAPTURE_BYTES
                    {
                        send_json_cors_or_plain(
                            &mut stream,
                            413,
                            "Payload Too Large",
                            origin.as_deref(),
                            &json!({"error": "The browser capture is too large or empty."})
                                .to_string(),
                        );
                        continue;
                    }
                    if let Err(error) = current.file.write_all(&request.body) {
                        send_json_cors_or_plain(&mut stream, 500, "Internal Server Error", origin.as_deref(), &json!({"error": format!("Could not store the browser capture: {error}")}).to_string());
                        continue;
                    }
                    current.bytes_written = next_size;
                    send_json_cors_or_plain(
                        &mut stream,
                        200,
                        "OK",
                        origin.as_deref(),
                        &json!({"ok": true, "offset": next_size}).to_string(),
                    );
                    continue;
                }
                if request.method == "POST"
                    && request.path == format!("{base}/bridge/capture/finish")
                {
                    let origin = match bridge_ready(&request.headers, &bridge_nonce, &confirmed) {
                        Ok(origin) => origin,
                        Err((status, error, origin)) => {
                            send_json_cors_or_plain(
                                &mut stream,
                                status,
                                "Request rejected",
                                origin.as_deref(),
                                &json!({"error": error}).to_string(),
                            );
                            continue;
                        }
                    };
                    let requested_id = serde_json::from_slice::<serde_json::Value>(&request.body)
                        .ok()
                        .and_then(|value| {
                            value
                                .get("captureId")
                                .and_then(|value| value.as_str())
                                .map(str::to_owned)
                        })
                        .or_else(|| {
                            header_value(&request.headers, CAPTURE_ID_HEADER).map(str::to_owned)
                        });
                    let mut state = match capture_state.lock() {
                        Ok(state) => state,
                        Err(_) => {
                            send_json_cors_or_plain(
                                &mut stream,
                                500,
                                "Internal Server Error",
                                origin.as_deref(),
                                &json!({"error": "The capture registry is unavailable."})
                                    .to_string(),
                            );
                            continue;
                        }
                    };
                    let Some(mut current) = state.pending.take() else {
                        send_json_cors_or_plain(
                            &mut stream,
                            400,
                            "Bad Request",
                            origin.as_deref(),
                            &json!({"error": "The browser capture upload is not active."})
                                .to_string(),
                        );
                        continue;
                    };
                    if requested_id.as_deref() != Some(current.id.as_str())
                        || current
                            .expected_bytes
                            .map(|expected| expected != current.bytes_written)
                            .unwrap_or(false)
                    {
                        let _ = fs::remove_file(&current.path);
                        send_json_cors_or_plain(
                            &mut stream,
                            400,
                            "Bad Request",
                            origin.as_deref(),
                            &json!({"error": "The browser capture id or size was invalid."})
                                .to_string(),
                        );
                        continue;
                    }
                    let _ = current.file.flush();
                    let path = current.path.clone();
                    let capture_id = current.id.clone();
                    let count = state.paths.len() + 1;
                    state.fetched.push(FetchedMedia {
                        path: path.to_string_lossy().into_owned(),
                        name: current.file_name,
                        media_kind: current.media_kind,
                        mime_type: current.mime_type,
                        capture_mode: current.capture_mode,
                        title: current.title,
                        size: current.bytes_written,
                    });
                    state.total_bytes = state.total_bytes.saturating_add(current.bytes_written);
                    state.paths.push(path);
                    send_json_cors_or_plain(
                        &mut stream,
                        200,
                        "OK",
                        origin.as_deref(),
                        &json!({"ok": true, "captureId": capture_id, "captureCount": count})
                            .to_string(),
                    );
                    continue;
                }
                if request.method == "GET"
                    && (request.path == base || request.path == format!("{base}/"))
                {
                    let signal = browser_signal_from_headers(&request.headers);
                    let detection = resolve_browser_label(&signal, default_browser.as_deref());
                    if let Ok(mut value) = browser.lock() {
                        *value = Some(detection.clone());
                    }
                    let source_url = source.lock().ok().and_then(|value| value.clone());
                    let content = if let Some(source_url) = source_url {
                        format!(
                            r#"<p>Use this temporary page in the browser whose session you want to use. JaneConverter only receives media you explicitly capture with the Browser Capture extension. It never reads or stores passwords, cookies, cache, or browser profile data.</p><ol><li>Open the source page below.</li><li>Sign in normally if needed.</li><li>Return here and confirm access.</li></ol><p><a class="primary" href="{}" target="_blank" rel="noreferrer">Open source link</a></p><p><a class="confirm" href="/access/{token}/ready">I am signed in - confirm access</a></p><p class="note">The link expires when JaneConverter closes or access is cleared.</p>"#,
                            html_escape(&source_url)
                        )
                    } else {
                        format!(
                            r#"<p>Use this temporary page in the browser whose session you want to use. JaneConverter only receives media you explicitly capture with the Browser Capture extension. It never reads or stores passwords, cookies, cache, or browser profile data.</p><ol><li>Open the media page you want to capture in this browser.</li><li>Sign in normally if needed.</li><li>Return here and confirm access, then use the Browser Capture extension on the media page.</li></ol><p><a class="confirm" href="/access/{token}/ready">I am signed in - confirm access</a></p><p class="note">The first capture binds this temporary session to the media page's site. The link expires when JaneConverter closes or access is cleared.</p>"#
                        )
                    };
                    send_html(
                        &mut stream,
                        200,
                        "OK",
                        &access_page("JaneConverter account access", &content),
                    );
                    continue;
                }
                send_html(
                    &mut stream,
                    404,
                    "Not Found",
                    &access_page("Link unavailable", "<p>This access link is not valid.</p>"),
                );
            }
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                thread::sleep(Duration::from_millis(100))
            }
            Err(_) => break,
        }
    }
}

pub fn create(source: &str, stamp: u128) -> Result<AccessServer, String> {
    create_with_root(source, stamp, crate::paths::default_fetched_dir())
}

pub fn create_with_root(
    source: &str,
    _stamp: u128,
    capture_root: PathBuf,
) -> Result<AccessServer, String> {
    let source = source.trim().to_owned();
    if !source.is_empty() {
        let parsed_source =
            Url::parse(&source).map_err(|_| "The source URL is invalid.".to_owned())?;
        if !matches!(parsed_source.scheme(), "http" | "https") || parsed_source.host_str().is_none()
        {
            return Err("Account access requires a valid HTTP or HTTPS source URL.".into());
        }
    }
    let source = Arc::new(Mutex::new((!source.is_empty()).then_some(source)));
    let listener = TcpListener::bind("127.0.0.1:0")
        .map_err(|error| format!("Could not create a local access link: {error}"))?;
    let port = listener
        .local_addr()
        .map_err(|error| error.to_string())?
        .port();
    let token: String = rand::rng()
        .sample_iter(&Alphanumeric)
        .take(48)
        .map(char::from)
        .collect();
    let default_browser = registered_default_browser();
    let browser = Arc::new(Mutex::new(None));
    let confirmed = Arc::new(AtomicBool::new(false));
    let bridge_nonce: String = rand::rng()
        .sample_iter(&Alphanumeric)
        .take(32)
        .map(char::from)
        .collect();
    fs::create_dir_all(&capture_root)
        .map_err(|error| format!("Could not create the capture workspace: {error}"))?;
    let capture_state = Arc::new(Mutex::new(CaptureState {
        pending: None,
        paths: Vec::new(),
        fetched: Vec::new(),
        total_bytes: 0,
        diagnostics: Vec::new(),
        next_diagnostic_id: 1,
    }));
    let stop = Arc::new(AtomicBool::new(false));
    let thread_browser = Arc::clone(&browser);
    let thread_confirmed = Arc::clone(&confirmed);
    let thread_capture_state = Arc::clone(&capture_state);
    let thread_capture_root = capture_root.clone();
    let thread_stop = Arc::clone(&stop);
    let worker = thread::spawn({
        let source_for_thread = Arc::clone(&source);
        let token = token.clone();
        let bridge_nonce = bridge_nonce.clone();
        move || {
            serve(
                listener,
                token,
                source_for_thread,
                default_browser,
                thread_browser,
                thread_confirmed,
                bridge_nonce,
                thread_capture_state,
                thread_capture_root,
                thread_stop,
            )
        }
    });
    Ok(AccessServer {
        link: format!("http://127.0.0.1:{port}/access/{token}"),
        source,
        browser,
        capture_state,
        capture_root,
        stop,
        thread: Some(worker),
    })
}

fn send_json_cors_or_plain(
    stream: &mut std::net::TcpStream,
    status: u16,
    reason: &str,
    origin: Option<&str>,
    body: &str,
) {
    if let Some(origin) = origin {
        send_json_cors(stream, status, reason, origin, body);
    } else {
        send_json(stream, status, reason, body);
    }
}

fn header_value<'a>(headers: &'a str, name: &str) -> Option<&'a str> {
    headers.lines().find_map(|line| {
        let (key, value) = line.split_once(':')?;
        key.trim()
            .eq_ignore_ascii_case(name)
            .then_some(value.trim())
    })
}

fn bridge_origin(headers: &str) -> Result<Option<String>, String> {
    let Some(origin) = header_value(headers, "origin") else {
        return Ok(None);
    };
    let parsed =
        Url::parse(origin).map_err(|_| "The browser bridge origin was invalid.".to_owned())?;
    if !matches!(
        parsed.scheme(),
        "chrome-extension" | "edge-extension" | "moz-extension" | "safari-web-extension"
    ) || parsed.host_str().is_none()
        || (!parsed.path().is_empty() && parsed.path() != "/")
        || parsed.query().is_some()
        || parsed.fragment().is_some()
    {
        return Err("The browser bridge origin was not allowed.".into());
    }
    Ok(Some(origin.to_owned()))
}

fn bridge_ready(
    headers: &str,
    bridge_nonce: &str,
    confirmed: &AtomicBool,
) -> Result<Option<String>, (u16, String, Option<String>)> {
    let origin = bridge_origin(headers).map_err(|error| (403, error, None))?;
    if !confirmed.load(Ordering::Acquire) {
        return Err((
            409,
            "Confirm account access in the browser first.".into(),
            origin,
        ));
    }
    if header_value(headers, BRIDGE_HEADER) != Some(bridge_nonce) {
        return Err((
            403,
            "The browser capture challenge was invalid or expired.".into(),
            origin,
        ));
    }
    Ok(origin)
}

fn validate_capture_metadata(body: &[u8], source: Option<&str>) -> Result<CaptureMetadata, String> {
    if body.is_empty() || body.len() > MAX_METADATA_BYTES {
        return Err("The browser capture metadata is empty or too large.".into());
    }
    let metadata: CaptureMetadata = serde_json::from_slice(body)
        .map_err(|_| "The browser capture metadata was not valid JSON.".to_owned())?;
    let page_url = Url::parse(metadata.page_url.trim())
        .map_err(|_| "The captured page URL is invalid.".to_owned())?;
    let page_host = page_url.host_str().unwrap_or_default().to_ascii_lowercase();
    if !matches!(page_url.scheme(), "http" | "https") || page_url.host_str().is_none() {
        return Err("The captured page is not part of the confirmed source site.".into());
    }
    if let Some(source) = source {
        let source_url = Url::parse(source.trim())
            .map_err(|_| "The confirmed source URL is invalid.".to_owned())?;
        let source_host = source_url
            .host_str()
            .unwrap_or_default()
            .to_ascii_lowercase();
        if !matches!(source_url.scheme(), "http" | "https") || !same_site(&source_host, &page_host)
        {
            return Err("The captured page is not part of the confirmed source site.".into());
        }
    }
    if metadata.file_name.is_empty()
        || metadata.file_name.len() > 512
        || metadata.file_name == "."
        || metadata.file_name == ".."
        || metadata
            .file_name
            .chars()
            .any(|value| matches!(value, '/' | '\\' | ':'))
        || metadata.file_name.chars().any(|value| value.is_control())
    {
        return Err("The browser capture returned an unsafe file name.".into());
    }
    if !matches!(metadata.media_kind.as_str(), "video" | "audio" | "image")
        || !matches!(
            metadata.capture_mode.as_str(),
            "current" | "sequence" | "network"
        )
        || !metadata.mime_type.contains('/')
        || metadata.title.is_empty()
    {
        return Err("The browser capture metadata was invalid.".into());
    }
    if let Some(expected) = metadata.expected_bytes {
        if expected == 0 || expected > MAX_MEDIA_BYTES {
            return Err("The expected media size is outside the allowed range.".into());
        }
    }
    Ok(metadata)
}

fn same_site(left: &str, right: &str) -> bool {
    left == right || left.ends_with(&format!(".{right}")) || right.ends_with(&format!(".{left}"))
}

#[cfg(test)]
fn browser_label_from_headers(request: &str) -> String {
    browser_label_from_signal(&browser_signal_from_headers(request))
}

fn browser_signal_from_headers(request: &str) -> String {
    request
        .lines()
        .filter_map(|line| {
            let (name, value) = line.split_once(':')?;
            let name = name.trim().to_ascii_lowercase();
            matches!(
                name.as_str(),
                "user-agent" | "sec-ch-ua" | "sec-ch-ua-full-version-list"
            )
            .then_some(value.trim())
        })
        .collect::<Vec<_>>()
        .join(" ")
}

fn resolve_browser_label(signal: &str, default_browser: Option<&str>) -> String {
    let detected = browser_label_from_signal(signal);
    if matches!(detected.as_str(), "Chrome" | "Unknown browser")
        && default_browser == Some("Vivaldi")
    {
        return "Vivaldi".into();
    }
    detected
}

fn browser_association_label(signal: &str) -> Option<&'static str> {
    let value = signal.to_ascii_lowercase();
    if value.contains("vivaldi") {
        Some("Vivaldi")
    } else if value.contains("brave") {
        Some("Brave")
    } else if value.contains("edge") || value.contains("msedge") {
        Some("Edge")
    } else if value.contains("firefox") {
        Some("Firefox")
    } else if value.contains("chrome") {
        Some("Chrome")
    } else if value.contains("opera") {
        Some("Opera")
    } else {
        None
    }
}

#[cfg(target_os = "windows")]
fn registered_default_browser() -> Option<String> {
    use winreg::enums::HKEY_CURRENT_USER;
    use winreg::RegKey;

    let current_user = RegKey::predef(HKEY_CURRENT_USER);
    for scheme in ["https", "http"] {
        let path = format!(
            r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\{scheme}\UserChoice"
        );
        let Ok(key) = current_user.open_subkey(path) else {
            continue;
        };
        let Ok(prog_id) = key.get_value::<String, _>("ProgId") else {
            continue;
        };
        if let Some(label) = browser_association_label(&prog_id) {
            return Some(label.to_owned());
        }
    }
    None
}

#[cfg(not(target_os = "windows"))]
fn registered_default_browser() -> Option<String> {
    None
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpStream;
    use std::time::Duration;

    #[test]
    fn access_server_returns_valid_http_line_endings() {
        let server =
            create("https://example.com/video", 42).expect("loopback access server should start");
        let address = server
            .link
            .strip_prefix("http://")
            .and_then(|value| value.split('/').next())
            .expect("access link should contain a host and port");
        let mut stream =
            TcpStream::connect(address).expect("loopback access server should accept connections");
        let request_path = server
            .link
            .split_once("/access/")
            .map(|(_, path)| format!("/access/{path}"))
            .expect("access link should contain a token");
        stream
            .set_read_timeout(Some(Duration::from_secs(2)))
            .expect("test socket should have a bounded read timeout");
        stream
            .write_all(
                format!(
                    "GET {request_path} HTTP/1.1\r\nHost: {address}\r\nUser-Agent: Mozilla/5.0 Chrome/1.0\r\nConnection: close\r\n\r\n"
                )
                .as_bytes(),
            )
            .expect("test request should be written");

        let mut response = String::new();
        if let Err(error) = stream.read_to_string(&mut response) {
            assert_eq!(
                error.kind(),
                std::io::ErrorKind::ConnectionReset,
                "test response should be readable"
            );
            assert!(
                !response.is_empty(),
                "a reset connection should still contain the response"
            );
        }
        assert!(response.starts_with("HTTP/1.1 200 OK\r\n"));
        assert!(response.contains("\r\n\r\n"));
        assert!(!response.contains(r"\r\n"));
        assert!(response.contains("JaneConverter account access"));
    }

    #[test]
    fn browser_label_detects_vivaldi_before_chrome_marker() {
        assert_eq!(
            browser_label_from_signal("Mozilla/5.0 Chrome/140.0.0.0 Safari/537.36 Vivaldi/7.0"),
            "Vivaldi"
        );
    }

    #[test]
    fn browser_label_uses_vivaldi_client_hint_when_user_agent_is_chromium_only() {
        let request = concat!(
            "GET /access/test/ready HTTP/1.1\r\n",
            "Sec-CH-UA: \"Chromium\";v=\"140\", \"Vivaldi\";v=\"7\"\r\n",
            "User-Agent: Mozilla/5.0 Chrome/140.0.0.0 Safari/537.36\r\n",
            "\r\n"
        );
        assert_eq!(browser_label_from_headers(request), "Vivaldi");
    }

    #[test]
    fn browser_label_falls_back_to_registered_vivaldi_for_masked_chromium_headers() {
        assert_eq!(
            resolve_browser_label(
                "Mozilla/5.0 Chrome/140.0.0.0 Safari/537.36",
                Some("Vivaldi")
            ),
            "Vivaldi"
        );
    }

    #[test]
    fn browser_association_maps_vivaldi_progids() {
        assert_eq!(browser_association_label("VivaldiHTM"), Some("Vivaldi"));
        assert_eq!(browser_association_label("ChromeHTML"), Some("Chrome"));
    }

    #[test]
    fn scans_saved_fetched_media_without_an_active_session() {
        let root =
            std::env::temp_dir().join(format!("janec-fetched-scan-{}", crate::paths::now_stamp()));
        fs::create_dir_all(&root).expect("scan root should be writable");
        fs::write(root.join("saved.jpg"), b"image").expect("saved image should be writable");
        fs::write(root.join("ignored.txt"), b"text").expect("ignored file should be writable");

        let items = scan_fetched_media(&root);
        assert_eq!(items.len(), 1);
        assert_eq!(items[0].media_kind, "image");
        assert_eq!(items[0].capture_mode, "saved");

        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn diagnostic_schema_only_accepts_redacted_known_events() {
        let valid = DiagnosticPayload {
            event: "media_response".into(),
            platform: None,
            host: Some("scontent.fhan2-4.fna.fbcdn.net".into()),
            media_kind: Some("video".into()),
            status: Some(200),
            bytes: Some(1_048_576),
            reason: None,
        };
        assert!(diagnostic_message(&valid)
            .expect("known diagnostic should be accepted")
            .contains("HTTP 200"));

        let unsafe_host = DiagnosticPayload {
            event: "session_fetch_started".into(),
            platform: Some("facebook".into()),
            host: Some("https://example.invalid/?token=secret".into()),
            media_kind: Some("video".into()),
            status: None,
            bytes: None,
            reason: None,
        };
        assert!(diagnostic_message(&unsafe_host).is_err());
    }
}
