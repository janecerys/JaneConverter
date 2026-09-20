mod access;
mod library;
mod model;
mod paths;
mod process;

use model::{AccessStatus, ConversionRequest, LibraryEntry, RuntimeInfo};
use paths::{
    command_available, data_root, detect_gpu, find_python, packaged_engine, prepare_command,
    project_root, read_preference, settings_get_internal, write_preference, write_settings,
};
use process::{
    load_playlist as load_playlist_engine, start_conversion as start_engine_conversion,
    terminate_child,
};
use rfd::FileDialog;
use std::fs;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use tauri::State;

#[derive(Clone)]
pub struct AppState {
    active_child: Arc<Mutex<Option<Arc<Mutex<std::process::Child>>>>>,
    active_cancel: Arc<Mutex<Option<Arc<AtomicBool>>>>,
    sequence: Arc<AtomicU64>,
    access: Arc<Mutex<Option<access::AccessServer>>>,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            active_child: Arc::new(Mutex::new(None)),
            active_cancel: Arc::new(Mutex::new(None)),
            sequence: Arc::new(AtomicU64::new(1)),
            access: Arc::new(Mutex::new(None)),
        }
    }
}

fn active_browser(state: &AppState) -> Option<String> {
    state.access.lock().ok().and_then(|value| {
        value.as_ref().and_then(|server| {
            let status = server.status();
            (!status.browser.trim().is_empty()).then_some(status.browser)
        })
    })
}

fn active_bridge_payload(state: &AppState, source: &str) -> Option<String> {
    state.access.lock().ok().and_then(|value| {
        value
            .as_ref()
            .and_then(|server| server.bridge_payload_for(source))
    })
}

#[tauri::command]
fn runtime_info() -> RuntimeInfo {
    let (gpu_available, gpu_label) = detect_gpu();
    let python = find_python();
    RuntimeInfo {
        mode: "tauri",
        python_ready: if python.is_file() {
            true
        } else {
            command_available(python.to_str().unwrap_or("python"))
        },
        ffmpeg_ready: command_available("ffmpeg"),
        python_path: python.display().to_string(),
        data_root: data_root().display().to_string(),
        project_root: project_root().display().to_string(),
        gpu_available,
        gpu_label,
        frontend_preference: read_preference(),
    }
}

#[tauri::command]
fn settings_get() -> model::ConverterSettings {
    settings_get_internal()
}

#[tauri::command]
fn settings_save(settings: model::ConverterSettings) -> Result<(), String> {
    write_settings(&settings).map_err(|error| format!("Could not save settings: {error}"))
}

#[tauri::command]
fn choose_file() -> Option<String> {
    FileDialog::new()
        .set_title("Choose media file")
        .pick_file()
        .map(|path| path.display().to_string())
}

#[tauri::command]
fn choose_folder() -> Option<String> {
    FileDialog::new()
        .set_title("Choose export folder")
        .pick_folder()
        .map(|path| path.display().to_string())
}

#[tauri::command]
fn open_path(path: String) -> Result<(), String> {
    let target = PathBuf::from(path.trim());
    if !target.exists() {
        return Err("That file or folder no longer exists.".into());
    }
    #[cfg(target_os = "windows")]
    {
        Command::new("explorer")
            .arg(&target)
            .spawn()
            .map_err(|error| error.to_string())?;
    }
    #[cfg(target_os = "macos")]
    {
        Command::new("open")
            .arg(&target)
            .spawn()
            .map_err(|error| error.to_string())?;
    }
    #[cfg(all(unix, not(target_os = "macos")))]
    {
        Command::new("xdg-open")
            .arg(&target)
            .spawn()
            .map_err(|error| error.to_string())?;
    }
    Ok(())
}

#[tauri::command]
fn open_url(url: String) -> Result<(), String> {
    let value = url.trim();
    if !(value.starts_with("http://") || value.starts_with("https://")) {
        return Err("Only http and https URLs can be opened.".into());
    }
    #[cfg(target_os = "windows")]
    {
        Command::new("rundll32")
            .args(["url.dll,FileProtocolHandler", value])
            .spawn()
            .map_err(|error| error.to_string())?;
    }
    #[cfg(target_os = "macos")]
    {
        Command::new("open")
            .arg(value)
            .spawn()
            .map_err(|error| error.to_string())?;
    }
    #[cfg(all(unix, not(target_os = "macos")))]
    {
        Command::new("xdg-open")
            .arg(value)
            .spawn()
            .map_err(|error| error.to_string())?;
    }
    Ok(())
}

#[tauri::command]
fn start_conversion(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
    request: ConversionRequest,
) -> Result<String, String> {
    if state
        .active_child
        .lock()
        .map_err(|_| "The conversion registry is unavailable.")?
        .is_some()
    {
        return Err("A conversion is already running.".into());
    }
    let job_id = format!(
        "conversion-{}-{}",
        paths::now_stamp(),
        state.sequence.fetch_add(1, Ordering::Relaxed)
    );
    let child_slot = Arc::clone(&state.active_child);
    let cancel_slot = Arc::clone(&state.active_cancel);
    let child_slot_for_worker = Arc::clone(&child_slot);
    let cancel_slot_for_worker = Arc::clone(&cancel_slot);
    let browser = active_browser(&state);
    let bridge_payload = active_bridge_payload(&state, &request.source);
    start_engine_conversion(
        app,
        job_id.clone(),
        request,
        browser,
        bridge_payload,
        child_slot,
        cancel_slot,
        move |_code, _cancelled| {
            if let Ok(mut value) = child_slot_for_worker.lock() {
                *value = None;
            }
            if let Ok(mut value) = cancel_slot_for_worker.lock() {
                *value = None;
            }
        },
    )?;
    Ok(job_id)
}

#[tauri::command]
fn cancel_conversion(state: State<'_, AppState>, job_id: String) -> Result<(), String> {
    if job_id.trim().is_empty() {
        return Err("The conversion id is missing.".into());
    }
    let cancel = state
        .active_cancel
        .lock()
        .map_err(|_| "The cancellation registry is unavailable.")?
        .clone();
    let child = state
        .active_child
        .lock()
        .map_err(|_| "The conversion registry is unavailable.")?
        .clone();
    let Some(cancel) = cancel else {
        return Err("No conversion is running.".into());
    };
    cancel.store(true, Ordering::Relaxed);
    if let Some(child) = child {
        if let Ok(mut value) = child.lock() {
            terminate_child(&mut value);
        }
    }
    Ok(())
}

#[tauri::command]
fn load_playlist(
    state: State<'_, AppState>,
    source: String,
) -> Result<model::PlaylistCatalog, String> {
    let bridge_payload = active_bridge_payload(&state, &source);
    load_playlist_engine(&source, active_browser(&state), bridge_payload)
}

#[tauri::command]
fn scan_library(path: String) -> Result<Vec<LibraryEntry>, String> {
    library::scan(&path)
}

#[tauri::command]
fn get_thumbnail(root: String, path: String) -> Result<Option<String>, String> {
    library::thumbnail(&root, &path)
}

#[tauri::command]
fn move_library(source: String, destination_parent: String) -> Result<String, String> {
    let mut settings = settings_get_internal();
    let configured = fs::canonicalize(settings.output_dir.trim())
        .map_err(|error| format!("The configured library is unavailable: {error}"))?;
    let requested = fs::canonicalize(source.trim())
        .map_err(|error| format!("The current library is unavailable: {error}"))?;
    if configured != requested {
        return Err("For safety, only the active converted library can be moved.".into());
    }
    let destination = library::move_directory(&source, &destination_parent)?;
    settings.output_dir = destination.clone();
    write_settings(&settings).map_err(|error| {
        format!(
            "The library moved to {destination}, but JaneConverter could not save the new location: {error}"
        )
    })?;
    Ok(destination)
}

#[tauri::command]
fn delete_library_entry(root: String, path: String) -> Result<(), String> {
    library::delete_inside(&root, &path)
}

#[tauri::command]
fn create_access_link(state: State<'_, AppState>, source: String) -> Result<AccessStatus, String> {
    if !(source.trim().starts_with("http://") || source.trim().starts_with("https://")) {
        return Err("Account access is available for online media URLs only.".into());
    }
    let server = access::create(&source, paths::now_stamp())?;
    let status = server.status();
    let mut access = state
        .access
        .lock()
        .map_err(|_| "The access registry is unavailable.")?;
    *access = Some(server);
    Ok(status)
}

#[tauri::command]
fn access_status(state: State<'_, AppState>) -> AccessStatus {
    state
        .access
        .lock()
        .ok()
        .and_then(|value| value.as_ref().map(access::AccessServer::status))
        .unwrap_or(AccessStatus {
            active: false,
            link: String::new(),
            browser: String::new(),
            bridge_connected: false,
        })
}

#[tauri::command]
fn clear_access_link(state: State<'_, AppState>) -> Result<(), String> {
    let mut access = state
        .access
        .lock()
        .map_err(|_| "The access registry is unavailable.")?;
    *access = None;
    Ok(())
}

#[tauri::command]
fn set_frontend_preference(preference: String) -> Result<(), String> {
    write_preference(preference.trim())
        .map_err(|error| format!("Could not save interface preference: {error}"))
}

#[tauri::command]
fn relaunch(app: tauri::AppHandle) -> Result<(), String> {
    let root = project_root();
    #[cfg(target_os = "windows")]
    let preferred_launcher = root.join("JaneConverter.exe");
    #[cfg(not(target_os = "windows"))]
    let preferred_launcher = root.join("run_converter.sh");

    let launcher = if preferred_launcher.is_file() {
        preferred_launcher
    } else {
        std::env::current_exe()
            .map_err(|error| format!("Could not locate JaneConverter: {error}"))?
    };
    let mut command = Command::new(&launcher);
    command
        .current_dir(&root)
        .env("JANECONVERTER_DATA_DIR", data_root());
    prepare_command(&mut command);
    command
        .spawn()
        .map_err(|error| format!("Could not relaunch JaneConverter: {error}"))?;
    app.exit(0);
    Ok(())
}

fn format_update_summary(stdout: &str) -> String {
    let Ok(payload) = serde_json::from_str::<serde_json::Value>(stdout) else {
        return if stdout.trim().is_empty() {
            "Update check completed, but no result was returned.".into()
        } else {
            stdout.trim().into()
        };
    };

    let mut messages = Vec::new();
    if let Some(engine) = payload.get("engine") {
        if engine
            .get("has_update")
            .and_then(serde_json::Value::as_bool)
            .unwrap_or(false)
        {
            let current = engine
                .get("current_version")
                .and_then(serde_json::Value::as_str)
                .unwrap_or("installed");
            let latest = engine
                .get("latest_version")
                .and_then(serde_json::Value::as_str)
                .unwrap_or("latest");
            messages.push(format!(
                "Extractor engine update available: v{current} -> v{latest}."
            ));
        } else if !engine
            .get("online")
            .and_then(serde_json::Value::as_bool)
            .unwrap_or(true)
        {
            messages.push("Extractor engine check unavailable.".to_owned());
        } else {
            messages.push("Extractor engine is up to date.".to_owned());
        }
    }

    if let Some(repo) = payload.get("repo") {
        if repo
            .get("has_update")
            .and_then(serde_json::Value::as_bool)
            .unwrap_or(false)
        {
            let commits = repo
                .get("commits_behind")
                .and_then(serde_json::Value::as_u64)
                .unwrap_or(1);
            let noun = if commits == 1 { "commit" } else { "commits" };
            messages.push(format!(
                "JaneConverter has {commits} newer repository {noun}."
            ));
        } else if let Some(error) = repo.get("error").and_then(serde_json::Value::as_str) {
            if !error.trim().is_empty() {
                messages.push(format!(
                    "JaneConverter repository check unavailable: {error}"
                ));
            }
        } else {
            messages.push("JaneConverter is up to date.".to_owned());
        }
    }

    if messages.is_empty() {
        "Update check completed, but no update details were returned.".into()
    } else {
        format!("Update check complete. {}", messages.join(" "))
    }
}
#[tauri::command]
fn check_updates() -> Result<String, String> {
    let engine = find_python();
    let mut command = Command::new(&engine);
    if !packaged_engine(&engine) {
        command.arg(project_root().join("run_converter.py"));
    }
    command
        .arg("--check-updates")
        .current_dir(project_root())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    prepare_command(&mut command);
    let output = command
        .output()
        .map_err(|error| format!("Could not start update check: {error}"))?;
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_owned();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_owned();
    if !output.status.success() {
        return Err(if stderr.is_empty() { stdout } else { stderr });
    }
    Ok(format_update_summary(&stdout))
}

pub fn run() {
    tauri::Builder::default()
        .manage(AppState::default())
        .invoke_handler(tauri::generate_handler![
            runtime_info,
            settings_get,
            settings_save,
            choose_file,
            choose_folder,
            open_path,
            open_url,
            start_conversion,
            cancel_conversion,
            load_playlist,
            scan_library,
            get_thumbnail,
            move_library,
            delete_library_entry,
            create_access_link,
            access_status,
            clear_access_link,
            set_frontend_preference,
            relaunch,
            check_updates
        ])
        .run(tauri::generate_context!())
        .expect("error while running JaneConverter Desktop");
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::ConversionRequest;

    #[test]
    fn settings_default_is_project_local() {
        assert!(paths::default_output_dir().ends_with("converted"));
    }

    #[test]
    fn project_root_contains_converter_engine() {
        assert!(paths::project_root().join("engine").is_dir());
    }

    #[test]
    fn update_summary_is_human_readable() {
        let summary = format_update_summary(
            r#"{"engine":{"has_update":false,"current_version":"2026.08.30","latest_version":"2026.08.19","online":true},"repo":{"has_update":false,"is_git":false,"current_commit":"unknown","latest_commit":"unknown","commits_behind":0,"error":"Not a Git repository"}}"#,
        );
        assert!(summary.contains("Extractor engine is up to date"));
        assert!(summary.contains("repository check unavailable"));
        assert!(!summary.contains("\"engine\""));
    }

    #[test]
    fn conversion_request_rejects_empty_source() {
        let request = ConversionRequest {
            source: " ".into(),
            output_dir: "out".into(),
            category: "Music".into(),
            format: "mp3".into(),
            bitrate: "320k".into(),
            sample_rate: 48000,
            resolution: "original".into(),
            normalize: false,
            use_gpu: false,
            save_cover: true,
            save_metadata: true,
            retries: 2,
            playlist_indexes: None,
            browser_session: None,
        };
        assert!(crate::process::build_conversion_args(&request, None).is_err());
    }
}
