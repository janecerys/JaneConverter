mod access;
mod library;
mod model;
mod paths;
mod process;

use model::{
    AccessDiagnostic, AccessStatus, ConversionRequest, FetchedMedia, LibraryEntry, RuntimeInfo,
};
use paths::{
    command_available, data_root, detect_gpu, find_ffmpeg, find_python, packaged_engine,
    prepare_command, project_root, set_data_root, settings_get_internal, write_settings,
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
    active_job: Arc<Mutex<Option<String>>>,
    sequence: Arc<AtomicU64>,
    access: Arc<Mutex<Option<access::AccessServer>>>,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            active_child: Arc::new(Mutex::new(None)),
            active_cancel: Arc::new(Mutex::new(None)),
            active_job: Arc::new(Mutex::new(None)),
            sequence: Arc::new(AtomicU64::new(1)),
            access: Arc::new(Mutex::new(None)),
        }
    }
}

fn active_capture_path(
    state: &AppState,
    source: &str,
    requested_path: Option<&str>,
) -> Option<PathBuf> {
    let captured = state.access.lock().ok().and_then(|value| {
        value
            .as_ref()
            .and_then(|server| server.captured_media_path(source, requested_path))
    });
    if captured.is_some() || !source.trim().is_empty() {
        return captured;
    }

    let requested = requested_path?.trim();
    let root = fs::canonicalize(settings_get_internal().fetched_dir).ok()?;
    let target = fs::canonicalize(requested).ok()?;
    (target.starts_with(root) && target.is_file()).then_some(target)
}

fn job_is_active(active_job: Option<&str>, requested_job: &str) -> bool {
    active_job == Some(requested_job.trim())
}

#[tauri::command]
fn runtime_info() -> RuntimeInfo {
    let (gpu_available, gpu_label) = detect_gpu();
    let python = find_python();
    let ffmpeg = find_ffmpeg();
    let packaged = packaged_engine(&python);
    RuntimeInfo {
        mode: "tauri",
        python_ready: if python.is_file() {
            true
        } else {
            command_available(python.to_str().unwrap_or("python"))
        },
        ffmpeg_ready: command_available(ffmpeg.to_str().unwrap_or("ffmpeg")),
        ffmpeg_path: ffmpeg.display().to_string(),
        python_path: python.display().to_string(),
        data_root: data_root().display().to_string(),
        project_root: project_root().display().to_string(),
        gpu_available,
        gpu_label,
        packaged,
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
fn set_data_root_path(path: String) -> Result<String, String> {
    set_data_root(PathBuf::from(path.trim()).as_path())
        .map(|value| value.display().to_string())
        .map_err(|error| format!("Could not change the data root: {error}"))
}

#[tauri::command]
fn choose_file() -> Option<String> {
    FileDialog::new()
        .set_title("Choose media file")
        .pick_file()
        .map(|path| path.display().to_string())
}

#[tauri::command]
fn choose_files() -> Vec<String> {
    FileDialog::new()
        .set_title("Choose media files")
        .pick_files()
        .map(|paths| paths.into_iter().map(|path| path.display().to_string()).collect())
        .unwrap_or_default()
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
        let mut command = Command::new("explorer");
        if target.is_file() {
            command.arg("/select,").arg(&target);
        } else {
            command.arg(&target);
        }
        command.spawn().map_err(|error| error.to_string())?;
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
fn open_file(path: String) -> Result<(), String> {
    let target = PathBuf::from(path.trim());
    if !target.is_file() {
        return Err("That media file no longer exists.".into());
    }
    #[cfg(target_os = "windows")]
    {
        Command::new("cmd")
            .args(["/C", "start", "", target.to_string_lossy().as_ref()])
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
    let active_job_slot = Arc::clone(&state.active_job);
    let child_slot_for_worker = Arc::clone(&child_slot);
    let cancel_slot_for_worker = Arc::clone(&cancel_slot);
    let active_job_for_worker = Arc::clone(&active_job_slot);
    let completed_job_id = job_id.clone();
    let browser = request.browser_session.clone();
    let capture_path = active_capture_path(
        &state,
        &request.source,
        request.browser_capture_path.as_deref(),
    );
    {
        let mut active_job = active_job_slot
            .lock()
            .map_err(|_| "The conversion registry is unavailable.")?;
        if active_job.is_some() {
            return Err("A conversion is already running.".into());
        }
        *active_job = Some(job_id.clone());
    }
    if let Err(error) = start_engine_conversion(
        app,
        job_id.clone(),
        request,
        browser,
        capture_path,
        child_slot,
        cancel_slot,
        move |_code, _cancelled| {
            if let Ok(mut value) = child_slot_for_worker.lock() {
                *value = None;
            }
            if let Ok(mut value) = cancel_slot_for_worker.lock() {
                *value = None;
            }
            if let Ok(mut value) = active_job_for_worker.lock() {
                if value.as_deref() == Some(completed_job_id.as_str()) {
                    *value = None;
                }
            }
        },
    ) {
        if let Ok(mut active_job) = active_job_slot.lock() {
            if active_job.as_deref() == Some(job_id.as_str()) {
                *active_job = None;
            }
        }
        return Err(error);
    }
    Ok(job_id)
}

#[tauri::command]
fn cancel_conversion(state: State<'_, AppState>, job_id: String) -> Result<(), String> {
    if job_id.trim().is_empty() {
        return Err("The conversion id is missing.".into());
    }
    let active_job = state
        .active_job
        .lock()
        .map_err(|_| "The conversion registry is unavailable.")?
        .clone();
    if !job_is_active(active_job.as_deref(), &job_id) {
        return Err("That conversion is no longer active.".into());
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
    _state: State<'_, AppState>,
    source: String,
) -> Result<model::PlaylistCatalog, String> {
    load_playlist_engine(&source, None)
}

#[tauri::command]
fn scan_library(path: String) -> Result<Vec<LibraryEntry>, String> {
    library::scan(&path)
}

#[tauri::command]
fn recent_conversions(path: String, limit: usize) -> Result<Vec<LibraryEntry>, String> {
    library::recent(&path, limit)
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
fn move_fetched_folder(
    state: State<'_, AppState>,
    source: String,
    destination_parent: String,
) -> Result<String, String> {
    if state
        .access
        .lock()
        .map_err(|_| "The access registry is unavailable.")?
        .is_some()
    {
        return Err("Clear browser access before moving the fetched media folder.".into());
    }

    let mut settings = settings_get_internal();
    let configured = fs::canonicalize(settings.fetched_dir.trim())
        .map_err(|error| format!("The configured fetched media folder is unavailable: {error}"))?;
    let requested = fs::canonicalize(source.trim())
        .map_err(|error| format!("The current fetched media folder is unavailable: {error}"))?;
    if configured != requested {
        return Err("For safety, only the active fetched media folder can be moved.".into());
    }
    let destination = library::move_directory(&source, &destination_parent)?;
    settings.fetched_dir = destination.clone();
    write_settings(&settings).map_err(|error| {
        format!(
            "The fetched media folder moved to {destination}, but JaneConverter could not save the new location: {error}"
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
    let settings = settings_get_internal();
    let server = access::create_with_root(
        &source,
        paths::now_stamp(),
        PathBuf::from(settings.fetched_dir),
    )?;
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
            source: None,
            bridge_connected: false,
            capture_count: 0,
            captured_media_kind: None,
        })
}

#[tauri::command]
fn fetched_media(state: State<'_, AppState>) -> Vec<FetchedMedia> {
    let fallback_root = PathBuf::from(settings_get_internal().fetched_dir);
    state
        .access
        .lock()
        .ok()
        .and_then(|value| value.as_ref().map(access::AccessServer::fetched_media))
        .unwrap_or_else(|| access::scan_fetched_media(&fallback_root))
}

#[tauri::command]
fn access_diagnostics(state: State<'_, AppState>) -> Vec<AccessDiagnostic> {
    state
        .access
        .lock()
        .ok()
        .and_then(|value| value.as_ref().map(access::AccessServer::diagnostics))
        .unwrap_or_default()
}

#[tauri::command]
fn fetched_media_thumbnail(
    state: State<'_, AppState>,
    path: String,
) -> Result<Option<String>, String> {
    let fallback_root = settings_get_internal().fetched_dir;
    let access = state
        .access
        .lock()
        .map_err(|_| "The access registry is unavailable.".to_owned())?;
    match access.as_ref() {
        Some(server) => server.fetched_media_thumbnail(&path),
        None => library::thumbnail(&fallback_root, &path),
    }
}

#[tauri::command]
fn discard_fetched_media(state: State<'_, AppState>, path: String) -> Result<(), String> {
    let fallback_root = settings_get_internal().fetched_dir;
    let access = state
        .access
        .lock()
        .map_err(|_| "The access registry is unavailable.".to_owned())?;
    match access.as_ref() {
        Some(server) => server.discard_fetched_media(&path),
        None => library::delete_inside(&fallback_root, &path),
    }
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
fn relaunch(app: tauri::AppHandle) -> Result<(), String> {
    let root = project_root();
    let launcher = std::env::current_exe()
        .map_err(|error| format!("Could not locate JaneConverter: {error}"))?;
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
        let packaged_snapshot = !repo
            .get("is_git")
            .and_then(serde_json::Value::as_bool)
            .unwrap_or(true)
            && repo.get("current_version").is_some();
        if packaged_snapshot
            && repo
                .get("has_update")
                .and_then(serde_json::Value::as_bool)
                .unwrap_or(false)
        {
            let current = repo
                .get("current_version")
                .and_then(serde_json::Value::as_str)
                .unwrap_or("installed");
            let latest = repo
                .get("latest_version")
                .and_then(serde_json::Value::as_str)
                .unwrap_or("latest");
            let installer_note = if repo
                .get("installer_available")
                .and_then(serde_json::Value::as_bool)
                .unwrap_or(false)
            {
                " The latest consumer installer is available from GitHub."
            } else {
                " Open the published GitHub release to update this snapshot."
            };
            messages.push(format!(
                "JaneConverter update available: v{current} -> v{latest}.{installer_note}"
            ));
        } else if packaged_snapshot {
            if let Some(error) = repo.get("error").and_then(serde_json::Value::as_str) {
                if !error.trim().is_empty() {
                    messages.push(format!("JaneConverter release check unavailable: {error}"));
                } else {
                    let current = repo
                        .get("current_version")
                        .and_then(serde_json::Value::as_str)
                        .unwrap_or("installed");
                    messages.push(format!("JaneConverter is up to date (v{current})."));
                }
            } else {
                let current = repo
                    .get("current_version")
                    .and_then(serde_json::Value::as_str)
                    .unwrap_or("installed");
                messages.push(format!("JaneConverter is up to date (v{current})."));
            }
        } else if repo
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
        command.args(["run", "--locked", "janeconverter"]);
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
            set_data_root_path,
            choose_file,
            choose_files,
            choose_folder,
            open_path,
            open_file,
            open_url,
            start_conversion,
            cancel_conversion,
            load_playlist,
            scan_library,
            recent_conversions,
            get_thumbnail,
            move_library,
            move_fetched_folder,
            delete_library_entry,
            create_access_link,
            access_status,
            fetched_media,
            access_diagnostics,
            fetched_media_thumbnail,
            discard_fetched_media,
            clear_access_link,
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
    fn cancellation_only_matches_the_active_job() {
        assert!(job_is_active(Some("conversion-123"), " conversion-123 "));
        assert!(!job_is_active(Some("conversion-123"), "conversion-stale"));
        assert!(!job_is_active(None, "conversion-123"));
    }

    #[test]
    fn settings_default_is_project_local() {
        assert!(paths::default_output_dir().ends_with("converted"));
    }

    #[test]
    fn project_root_contains_converter_engine() {
        assert!(paths::project_root()
            .join("src")
            .join("janeconverter")
            .join("cli.py")
            .is_file());
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
    fn packaged_snapshot_reports_published_release() {
        let summary = format_update_summary(
            r#"{"engine":{"has_update":false,"current_version":"2026.08.30","latest_version":"2026.08.19","online":true},"repo":{"has_update":true,"is_git":false,"current_version":"1.2.0","latest_version":"1.3.0","installer_available":true,"error":null}}"#,
        );
        assert!(summary.contains("JaneConverter update available: v1.2.0 -> v1.3.0"));
        assert!(summary.contains("latest consumer installer"));
        assert!(!summary.contains("not a Git repository"));
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
            browser_capture_path: None,
        };
        assert!(crate::process::build_conversion_args(&request, None).is_err());
    }
}
