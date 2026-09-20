use crate::model::AccessStatus;
use rand::{distr::Alphanumeric, Rng};
use serde::Deserialize;
use serde_json::json;
use std::io::{self, Read, Write};
use std::net::TcpListener;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;
use url::Url;

const MAX_BRIDGE_PAYLOAD_BYTES: usize = 256 * 1024;
const MAX_BRIDGE_COOKIES: usize = 500;
const MAX_COOKIE_FIELD_BYTES: usize = 8192;
const BRIDGE_HEADER: &str = "x-janecconverter-bridge";

pub struct AccessServer {
    pub link: String,
    source: String,
    browser: Arc<Mutex<Option<String>>>,
    bridge_payload: Arc<Mutex<Option<String>>>,
    stop: Arc<AtomicBool>,
    thread: Option<thread::JoinHandle<()>>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct BridgeCookie {
    name: String,
    value: String,
    domain: String,
    path: String,
    secure: bool,
}

#[derive(Debug, Deserialize)]
struct BridgePayload {
    cookies: Vec<BridgeCookie>,
}

impl Drop for AccessServer {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Relaxed);
        if let Some(handle) = self.thread.take() {
            let _ = handle.join();
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
            bridge_connected: self
                .bridge_payload
                .lock()
                .ok()
                .map(|value| value.is_some())
                .unwrap_or(false),
        }
    }

    pub fn bridge_payload_for(&self, source: &str) -> Option<String> {
        if self.source.trim() != source.trim() {
            return None;
        }
        self.bridge_payload
            .lock()
            .ok()
            .and_then(|value| value.clone())
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
                "Access-Control-Allow-Origin: {origin}\r\nVary: Origin\r\nAccess-Control-Allow-Headers: content-type, {BRIDGE_HEADER}\r\nAccess-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
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
        if bytes.len() > MAX_BRIDGE_PAYLOAD_BYTES + 16 * 1024 {
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
                if content_length > MAX_BRIDGE_PAYLOAD_BYTES {
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

fn serve(
    listener: TcpListener,
    token: String,
    source: String,
    default_browser: Option<String>,
    browser: Arc<Mutex<Option<String>>>,
    confirmed: Arc<AtomicBool>,
    bridge_payload: Arc<Mutex<Option<String>>>,
    bridge_nonce: String,
    bridge_received: Arc<AtomicBool>,
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
                    send_html(&mut stream, 200, "OK", &access_page("Access confirmed", &format!("<p>Browser detected: <strong>{}</strong>.</p><p>Return to JaneConverter. If the JaneConverter Browser Bridge extension is installed, click its toolbar button and choose <strong>Connect</strong>. Otherwise JaneConverter will use its regular browser-session fallback.</p><p class=\"note\">No cookie file is created or uploaded. The bridge keeps this session in memory for the current app session only.</p>", html_escape(&label))));
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
                        let response = if bridge_received.load(Ordering::Acquire) {
                            json!({"sourceUrl": source, "confirmed": true, "connected": true})
                        } else {
                            json!({"sourceUrl": source, "confirmed": true, "connected": false, "bridgeToken": bridge_nonce.clone()})
                        };
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
                if request.method == "POST" && request.path == format!("{base}/bridge") {
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
                        continue;
                    }
                    if bridge_received.load(Ordering::Acquire) {
                        send_json_cors_or_plain(
                            &mut stream,
                            409,
                            "Conflict",
                            origin.as_deref(),
                            &json!({"error": "A browser session is already connected. Clear access before connecting again."}).to_string(),
                        );
                        continue;
                    }
                    if header_value(&request.headers, BRIDGE_HEADER).unwrap_or_default()
                        != bridge_nonce
                    {
                        send_json_cors_or_plain(
                            &mut stream,
                            403,
                            "Forbidden",
                            origin.as_deref(),
                            &json!({"error": "The browser bridge challenge was invalid or expired."}).to_string(),
                        );
                        continue;
                    }
                    match validate_bridge_payload(&request.body, &source) {
                        Ok(payload) => {
                            if bridge_received.swap(true, Ordering::AcqRel) {
                                send_json_cors_or_plain(
                                    &mut stream,
                                    409,
                                    "Conflict",
                                    origin.as_deref(),
                                    &json!({"error": "A browser session is already connected. Clear access before connecting again."}).to_string(),
                                );
                                continue;
                            }
                            if let Ok(mut value) = bridge_payload.lock() {
                                *value = Some(payload);
                            }
                            send_json_cors_or_plain(
                                &mut stream,
                                200,
                                "OK",
                                origin.as_deref(),
                                &json!({"ok": true}).to_string(),
                            );
                        }
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
                if request.method == "GET"
                    && (request.path == base || request.path == format!("{base}/"))
                {
                    let signal = browser_signal_from_headers(&request.headers);
                    let detection = resolve_browser_label(&signal, default_browser.as_deref());
                    if let Ok(mut value) = browser.lock() {
                        *value = Some(detection.clone());
                    }
                    send_html(
                        &mut stream,
                        200,
                        "OK",
                        &access_page(
                            "JaneConverter account access",
                            &format!(
                                r#"<p>Use this temporary page in the browser whose session you want to use. The link only identifies that browser; JaneConverter never asks for or stores your password or copies or uploads your cookies.</p><ol><li>Open the source page below.</li><li>Sign in normally if needed.</li><li>Return here and confirm access.</li></ol><p><a class="primary" href="{}" target="_blank" rel="noreferrer">Open source link</a></p><p><a class="confirm" href="/access/{token}/ready">I am signed in - confirm access</a></p><p class="note">The link expires when JaneConverter closes or access is cleared.</p>"#,
                                html_escape(&source)
                            ),
                        ),
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

pub fn create(source: &str, _stamp: u128) -> Result<AccessServer, String> {
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
    let bridge_payload = Arc::new(Mutex::new(None));
    let bridge_nonce: String = rand::rng()
        .sample_iter(&Alphanumeric)
        .take(32)
        .map(char::from)
        .collect();
    let bridge_received = Arc::new(AtomicBool::new(false));
    let stop = Arc::new(AtomicBool::new(false));
    let thread_browser = Arc::clone(&browser);
    let thread_confirmed = Arc::clone(&confirmed);
    let thread_bridge_payload = Arc::clone(&bridge_payload);
    let thread_bridge_received = Arc::clone(&bridge_received);
    let thread_stop = Arc::clone(&stop);
    let source = source.trim().to_owned();
    let worker = thread::spawn({
        let source_for_thread = source.clone();
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
                thread_bridge_payload,
                bridge_nonce,
                thread_bridge_received,
                thread_stop,
            )
        }
    });
    Ok(AccessServer {
        link: format!("http://127.0.0.1:{port}/access/{token}"),
        source,
        browser,
        bridge_payload,
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

fn validate_bridge_payload(body: &[u8], source: &str) -> Result<String, String> {
    if body.is_empty() || body.len() > MAX_BRIDGE_PAYLOAD_BYTES {
        return Err("The browser bridge payload is too large or empty.".into());
    }
    let payload: BridgePayload = serde_json::from_slice(body)
        .map_err(|_| "The browser bridge payload was not valid JSON.")?;
    if payload.cookies.len() > MAX_BRIDGE_COOKIES {
        return Err("The browser bridge returned too many cookies.".into());
    }
    let parsed_source = Url::parse(source.trim()).map_err(|_| "The source URL is invalid.")?;
    let source_host = parsed_source
        .host_str()
        .ok_or_else(|| "The source URL has no host.".to_owned())?
        .to_ascii_lowercase();
    let source_path = parsed_source.path();
    let mut matching = 0usize;
    for cookie in &payload.cookies {
        if cookie.name.is_empty()
            || cookie.name.len() > MAX_COOKIE_FIELD_BYTES
            || cookie.value.len() > MAX_COOKIE_FIELD_BYTES
            || cookie.domain.len() > MAX_COOKIE_FIELD_BYTES
            || cookie.path.len() > MAX_COOKIE_FIELD_BYTES
            || cookie.path.is_empty()
            || !cookie.path.starts_with('/')
            || has_control_characters(&cookie.name)
            || has_control_characters(&cookie.value)
            || has_control_characters(&cookie.domain)
            || has_control_characters(&cookie.path)
        {
            return Err("The browser bridge returned an invalid cookie entry.".into());
        }
        let domain = cookie.domain.trim_start_matches('.').to_ascii_lowercase();
        let domain_matches = source_host == domain || source_host.ends_with(&format!(".{domain}"));
        let path_matches = cookie.path == "/"
            || source_path == cookie.path
            || source_path.starts_with(&format!("{}/", cookie.path.trim_end_matches('/')));
        if domain_matches && path_matches && (!cookie.secure || parsed_source.scheme() == "https") {
            matching += 1;
        }
    }
    if matching == 0 {
        return Err("The browser bridge returned no cookies for this source.".into());
    }
    String::from_utf8(body.to_vec()).map_err(|_| "The browser bridge payload was not UTF-8.".into())
}

fn has_control_characters(value: &str) -> bool {
    value.chars().any(|character| character.is_control())
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
        stream
            .read_to_string(&mut response)
            .expect("test response should be readable");
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
}
