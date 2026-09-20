use crate::model::{ConversionRequest, ConverterEvent, PlaylistCatalog, PlaylistItem};
use crate::paths::{find_python, prepare_command, project_root};
use std::io::{BufRead, BufReader, Read, Write};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::sync::Mutex;
use std::thread;
use std::time::Duration;
use tauri::Emitter;

pub fn progress_from_line(line: &str) -> Option<f32> {
    let start = line.find('[')?;
    let end = line[start + 1..].find('%')? + start + 1;
    line[start + 1..end]
        .trim()
        .parse::<f32>()
        .ok()
        .map(|value| (value / 100.0).clamp(0.0, 1.0))
}

pub fn emit_event(app: &tauri::AppHandle, event: ConverterEvent) {
    let _ = app.emit("converter-event", event);
}

pub fn forward_output<R: Read + Send + 'static>(reader: R, app: tauri::AppHandle, job_id: String) {
    thread::spawn(move || {
        for line in BufReader::new(reader).lines().map_while(Result::ok) {
            let message = line.trim_end().to_owned();
            let progress = progress_from_line(&message);
            emit_event(
                &app,
                ConverterEvent {
                    job_id: job_id.clone(),
                    kind: if progress.is_some() {
                        "progress"
                    } else {
                        "log"
                    }
                    .into(),
                    message,
                    progress,
                    output: None,
                },
            );
        }
    });
}

pub fn terminate_child(child: &mut Child) {
    #[cfg(target_os = "windows")]
    {
        let pid_text = child.id().to_string();
        let _ = Command::new("taskkill")
            .args(["/PID", &pid_text, "/T", "/F"])
            .status();
    }
    let _ = child.kill();
}

pub fn build_conversion_args(
    request: &ConversionRequest,
    browser: Option<String>,
) -> Result<Vec<String>, String> {
    if request.source.trim().is_empty() {
        return Err("Paste a media URL or choose a local file first.".into());
    }
    if request.output_dir.trim().is_empty() {
        return Err("Choose an export folder first.".into());
    }
    if ![44100, 48000, 96000].contains(&request.sample_rate) {
        return Err("Unsupported sample rate.".into());
    }
    let mut args = vec![
        project_root()
            .join("run_converter.py")
            .display()
            .to_string(),
        "--source".into(),
        request.source.trim().into(),
        "--format".into(),
        request.format.trim().into(),
        "--output".into(),
        request.output_dir.trim().into(),
        "--bitrate".into(),
        request.bitrate.trim().into(),
        "--sample-rate".into(),
        request.sample_rate.to_string(),
        "--resolution".into(),
        request.resolution.trim().into(),
        "--category".into(),
        request.category.trim().into(),
        "--retries".into(),
        request.retries.min(5).to_string(),
        "--no-update".into(),
    ];
    if !request.use_gpu {
        args.push("--no-gpu".into());
    }
    if !request.save_cover {
        args.push("--no-cover-art".into());
    }
    if !request.save_metadata {
        args.push("--no-metadata".into());
    }
    if request.normalize {
        args.push("--normalize".into());
    }
    if let Some(browser) = browser
        .or_else(|| request.browser_session.clone())
        .filter(|value| !value.trim().is_empty())
    {
        args.extend([
            "--browser-session".into(),
            normalize_browser_session_arg(&browser)?,
        ]);
    }
    if let Some(indexes) = &request.playlist_indexes {
        if !indexes.trim().is_empty() {
            args.extend([
                "--playlist".into(),
                "--playlist-indexes".into(),
                indexes.trim().into(),
            ]);
        }
    }
    Ok(args)
}

fn normalize_browser_session_arg(value: &str) -> Result<String, String> {
    let normalized = value.trim().to_ascii_lowercase();
    if matches!(
        normalized.as_str(),
        "none"
            | "chrome"
            | "edge"
            | "firefox"
            | "brave"
            | "vivaldi"
            | "opera"
            | "chromium"
            | "safari"
    ) {
        return Ok(normalized);
    }
    Err(format!(
        "Unsupported browser session '{value}'. Choose Chrome, Edge, Firefox, Brave, Vivaldi, Opera, Chromium, Safari, or Public only."
    ))
}

pub fn start_conversion(
    app: tauri::AppHandle,
    job_id: String,
    request: ConversionRequest,
    browser: Option<String>,
    bridge_payload: Option<String>,
    child_slot: Arc<Mutex<Option<Arc<Mutex<Child>>>>>,
    cancel_slot: Arc<Mutex<Option<Arc<AtomicBool>>>>,
    output: impl FnOnce(i32, bool) + Send + 'static,
) -> Result<(), String> {
    let mut args = build_conversion_args(&request, browser)?;
    if bridge_payload.is_some() {
        args.push("--browser-bridge-stdin".into());
    }
    std::fs::create_dir_all(&request.output_dir)
        .map_err(|error| format!("Could not use the export folder: {error}"))?;
    let mut command = Command::new(find_python());
    command
        .args(&args)
        .current_dir(project_root())
        .env("PYTHONUNBUFFERED", "1")
        .stdin(if bridge_payload.is_some() {
            Stdio::piped()
        } else {
            Stdio::null()
        })
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    prepare_command(&mut command);
    let mut child = command
        .spawn()
        .map_err(|error| format!("Could not start the Python engine: {error}"))?;
    if let Some(payload) = bridge_payload {
        let mut stdin = child
            .stdin
            .take()
            .ok_or_else(|| "Could not open the browser bridge handoff.".to_owned())?;
        if let Err(error) = stdin.write_all(payload.as_bytes()) {
            terminate_child(&mut child);
            return Err(format!("Could not send the browser bridge handoff: {error}"));
        }
    }
    let stdout = child.stdout.take();
    let stderr = child.stderr.take();
    let child = Arc::new(Mutex::new(child));
    let cancel = Arc::new(AtomicBool::new(false));
    *child_slot
        .lock()
        .map_err(|_| "The conversion process slot is unavailable.")? = Some(Arc::clone(&child));
    *cancel_slot
        .lock()
        .map_err(|_| "The cancellation slot is unavailable.")? = Some(Arc::clone(&cancel));
    if let Some(reader) = stdout {
        forward_output(reader, app.clone(), job_id.clone());
    }
    if let Some(reader) = stderr {
        forward_output(reader, app.clone(), job_id.clone());
    }
    emit_event(
        &app,
        ConverterEvent {
            job_id: job_id.clone(),
            kind: "started".into(),
            message: "The local conversion engine is working.".into(),
            progress: Some(0.02),
            output: None,
        },
    );
    let app_for_thread = app.clone();
    thread::spawn(move || {
        let status = loop {
            let result = child
                .lock()
                .ok()
                .and_then(|mut value| value.try_wait().ok())
                .flatten();
            if let Some(status) = result {
                break status;
            }
            thread::sleep(Duration::from_millis(80));
        };
        let cancelled = cancel.load(Ordering::Relaxed);
        let code = status.code().unwrap_or(1);
        let _ = output(code, cancelled);
        let (kind, message, progress) = if cancelled {
            ("cancelled", "Conversion cancelled.", None)
        } else if status.success() {
            (
                "finished",
                "Conversion finished. Your media is ready.",
                Some(1.0),
            )
        } else {
            (
                "failed",
                "The Python engine reported a conversion failure. Review Console for details.",
                None,
            )
        };
        emit_event(
            &app_for_thread,
            ConverterEvent {
                job_id,
                kind: kind.into(),
                message: message.into(),
                progress,
                output: None,
            },
        );
    });
    Ok(())
}

pub fn parse_playlist_output(output: &str) -> Result<PlaylistCatalog, String> {
    let mut title = None;
    let mut items = Vec::new();
    for line in output.lines() {
        let mut fields = line.splitn(6, '\t');
        match fields.next() {
            Some("PLAYLIST") => title = fields.next().map(str::to_owned),
            Some("ENTRY") => {
                let index = fields
                    .next()
                    .and_then(|value| value.parse().ok())
                    .ok_or("Playlist item index was invalid.")?;
                let item_title = fields.next().unwrap_or_default().to_owned();
                let artist = fields.next().unwrap_or_default().to_owned();
                let duration = fields.next().unwrap_or_default().to_owned();
                let url = fields.next().unwrap_or_default().to_owned();
                items.push(PlaylistItem {
                    index,
                    title: item_title,
                    artist,
                    duration,
                    url,
                });
            }
            _ => {}
        }
    }
    let title =
        title.ok_or_else(|| "The playlist loader returned no playlist title.".to_owned())?;
    if items.is_empty() {
        return Err("The source contained no usable tracks.".into());
    }
    Ok(PlaylistCatalog { title, items })
}

pub fn load_playlist(
    source: &str,
    browser: Option<String>,
    bridge_payload: Option<String>,
) -> Result<PlaylistCatalog, String> {
    let script = project_root().join("run_converter.py");
    let script_text = script.display().to_string();
    let mut command = Command::new(find_python());
    command
        .arg(script_text)
        .args(["--source", source.trim(), "--list-playlist", "--no-update"]);
    if let Some(browser) = browser.filter(|value| !value.trim().is_empty()) {
        let browser = normalize_browser_session_arg(&browser)?;
        command.args(["--browser-session", browser.as_str()]);
    }
    if bridge_payload.is_some() {
        command.arg("--browser-bridge-stdin");
    }
    command
        .current_dir(project_root())
        .env("PYTHONUNBUFFERED", "1")
        .stdin(if bridge_payload.is_some() {
            Stdio::piped()
        } else {
            Stdio::null()
        })
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    prepare_command(&mut command);
    let mut child = command
        .spawn()
        .map_err(|error| format!("Could not start playlist loading: {error}"))?;
    if let Some(payload) = bridge_payload {
        let mut stdin = child
            .stdin
            .take()
            .ok_or_else(|| "Could not open the browser bridge handoff.".to_owned())?;
        if let Err(error) = stdin.write_all(payload.as_bytes()) {
            terminate_child(&mut child);
            return Err(format!("Could not send the browser bridge handoff: {error}"));
        }
    }
    let output = child
        .wait_with_output()
        .map_err(|error| format!("Could not wait for playlist loading: {error}"))?;
    if !output.status.success() {
        let detail = String::from_utf8_lossy(&output.stderr).trim().to_owned();
        return Err(if detail.is_empty() {
            "Playlist loading failed. Review Console for details.".into()
        } else {
            detail
        });
    }
    let mut catalog = parse_playlist_output(&String::from_utf8_lossy(&output.stdout))?;
    let _ = browser;
    catalog.items.shrink_to_fit();
    Ok(catalog)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn progress_parser_is_bounded() {
        assert_eq!(progress_from_line("[105%] done"), Some(1.0));
        assert_eq!(progress_from_line("plain output"), None);
    }

    #[test]
    fn parses_playlist_output_with_unicode_fields() {
        let catalog = parse_playlist_output(
            "PLAYLIST\tSongs\nENTRY\t1\tBeyonce\tArtist\t03:20\thttps://example.test/1\n",
        )
        .unwrap();
        assert_eq!(catalog.title, "Songs");
        assert_eq!(catalog.items[0].duration, "03:20");
    }

    #[test]
    fn normalizes_display_browser_label_for_python_cli() {
        let request = ConversionRequest {
            source: "https://example.com/private-media".into(),
            output_dir: "out".into(),
            category: "Video".into(),
            format: "mp4".into(),
            bitrate: "original".into(),
            sample_rate: 48000,
            resolution: "original".into(),
            normalize: false,
            use_gpu: false,
            save_cover: true,
            save_metadata: true,
            retries: 2,
            playlist_indexes: None,
            browser_session: Some("Chrome".into()),
        };
        let args =
            build_conversion_args(&request, None).expect("display labels should be accepted");
        let flag = args
            .iter()
            .position(|value| value == "--browser-session")
            .expect("browser session flag should be forwarded");
        assert_eq!(args[flag + 1], "chrome");
    }
}
