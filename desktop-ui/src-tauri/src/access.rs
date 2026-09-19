use crate::model::AccessStatus;
use std::io::{self, Read, Write};
use std::net::TcpListener;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

pub struct AccessServer {
    pub link: String,
    browser: Arc<Mutex<Option<String>>>,
    stop: Arc<AtomicBool>,
    thread: Option<thread::JoinHandle<()>>,
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
        }
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

fn browser_label(user_agent: &str) -> String {
    let value = user_agent.to_ascii_lowercase();
    if value.contains("edg/") {
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

fn access_response(body: &str) -> String {
    format!(
        r#"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nCache-Control: no-store\r\nContent-Security-Policy: default-src 'none'; style-src 'unsafe-inline'\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}"#,
        body.len(),
        body
    )
}

fn access_page(title: &str, content: &str) -> String {
    format!(
        r#"<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><title>{title}</title><style>body{{background:#080711;color:#ededed;font:16px Segoe UI,Arial,sans-serif;max-width:640px;margin:12vh auto;padding:0 24px;line-height:1.55}}h1{{font-size:28px}}a{{color:#93c5fd}}.primary,.confirm{{display:inline-block;padding:11px 16px;border-radius:8px;color:#fff;text-decoration:none;margin:4px 8px 4px 0}}.primary{{background:#1f5fae}}.confirm{{background:#b3265f}}.note{{color:#9ca3af;font-size:13px}}</style></head><body><h1>{title}</h1>{content}</body></html>"#
    )
}

fn serve(
    listener: TcpListener,
    token: String,
    source: String,
    browser: Arc<Mutex<Option<String>>>,
    stop: Arc<AtomicBool>,
) {
    let _ = listener.set_nonblocking(true);
    while !stop.load(Ordering::Relaxed) {
        match listener.accept() {
            Ok((mut stream, _)) => {
                let mut buffer = [0u8; 8192];
                let read = stream.read(&mut buffer).unwrap_or_default();
                let request = String::from_utf8_lossy(&buffer[..read]);
                let path = request
                    .lines()
                    .next()
                    .and_then(|line| line.split_whitespace().nth(1))
                    .unwrap_or("/");
                let user_agent = request
                    .lines()
                    .find_map(|line| {
                        line.strip_prefix("User-Agent:")
                            .or_else(|| line.strip_prefix("user-agent:"))
                    })
                    .unwrap_or_default()
                    .trim();
                let base = format!("/access/{token}");
                let body = if path == format!("{base}/ready") {
                    let label = browser_label(user_agent);
                    if let Ok(mut value) = browser.lock() {
                        *value = Some(label.clone());
                    }
                    access_page("Access confirmed", &format!("<p>Browser detected: <strong>{}</strong>.</p><p>Return to JaneConverter. This session is used only for the current app session.</p>", html_escape(&label)))
                } else if path == base || path == format!("{base}/") {
                    access_page(
                        "JaneConverter account access",
                        &format!(
                            r#"<p>Use this temporary page in the browser whose session you want to use. JaneConverter never asks for or stores your password or cookies.</p><ol><li>Open the source page below.</li><li>Sign in normally if needed.</li><li>Return here and confirm access.</li></ol><p><a class="primary" href="{}" target="_blank" rel="noreferrer">Open source link</a></p><p><a class="confirm" href="/access/{token}/ready">I am signed in - confirm access</a></p><p class="note">The link expires when JaneConverter closes or access is cleared.</p>"#,
                            html_escape(&source)
                        ),
                    )
                } else {
                    access_page("Link unavailable", "<p>This access link is not valid.</p>")
                };
                let _ = stream.write_all(access_response(&body).as_bytes());
            }
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                thread::sleep(Duration::from_millis(100))
            }
            Err(_) => break,
        }
    }
}

pub fn create(source: &str, stamp: u128) -> Result<AccessServer, String> {
    let listener = TcpListener::bind("127.0.0.1:0")
        .map_err(|error| format!("Could not create a local access link: {error}"))?;
    let port = listener
        .local_addr()
        .map_err(|error| error.to_string())?
        .port();
    let token = format!("{stamp:x}");
    let browser = Arc::new(Mutex::new(None));
    let stop = Arc::new(AtomicBool::new(false));
    let thread_browser = Arc::clone(&browser);
    let thread_stop = Arc::clone(&stop);
    let worker = thread::spawn({
        let source = source.trim().to_owned();
        let token = token.clone();
        move || serve(listener, token, source, thread_browser, thread_stop)
    });
    Ok(AccessServer {
        link: format!("http://127.0.0.1:{port}/access/{token}"),
        browser,
        stop,
        thread: Some(worker),
    })
}
