use crate::model::ConverterSettings;
use std::collections::HashMap;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

pub const CREATE_NO_WINDOW: u32 = 0x08000000;

pub fn project_root() -> PathBuf {
    if let Ok(executable) = std::env::current_exe() {
        if let Some(directory) = executable.parent() {
            let candidates = [
                directory.to_path_buf(),
                directory.join("resources").join("runtime"),
                directory.join("runtime"),
                directory.join("resources"),
            ];
            for candidate in candidates {
                if is_runtime_root(&candidate) {
                    return candidate;
                }
            }
        }
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .map(Path::to_path_buf)
        .unwrap_or_else(|| PathBuf::from("."))
}

fn is_runtime_root(directory: &Path) -> bool {
    is_source_checkout(directory)
        || directory
            .join("engine")
            .join(packaged_engine_name())
            .is_file()
        || directory.join("bin").join(ffmpeg_name()).is_file()
}

fn is_source_checkout(directory: &Path) -> bool {
    directory.join("pyproject.toml").is_file()
        && directory.join("uv.lock").is_file()
        && directory
            .join("src")
            .join("janeconverter")
            .join("cli.py")
            .is_file()
}

fn packaged_engine_name() -> &'static str {
    if cfg!(target_os = "windows") {
        "JaneConverterEngine.exe"
    } else {
        "JaneConverterEngine"
    }
}

fn ffmpeg_name() -> &'static str {
    if cfg!(target_os = "windows") {
        "ffmpeg.exe"
    } else {
        "ffmpeg"
    }
}

fn user_data_root() -> PathBuf {
    #[cfg(target_os = "windows")]
    if let Some(root) = std::env::var_os("LOCALAPPDATA").or_else(|| std::env::var_os("APPDATA")) {
        return PathBuf::from(root).join("JaneConverter");
    }

    #[cfg(not(target_os = "windows"))]
    {
        if let Some(root) = std::env::var_os("XDG_DATA_HOME") {
            return PathBuf::from(root).join("JaneConverter");
        }
        if let Some(home) = std::env::var_os("HOME") {
            return PathBuf::from(home)
                .join(".local")
                .join("share")
                .join("JaneConverter");
        }
    }

    std::env::temp_dir().join("JaneConverter")
}

fn data_root_override_path() -> PathBuf {
    user_data_root()
        .parent()
        .unwrap_or_else(|| Path::new("."))
        .join("JaneConverter.data-root")
}

pub fn data_root() -> PathBuf {
    if let Some(configured) = std::env::var_os("JANECONVERTER_DATA_DIR") {
        if !configured.is_empty() {
            return PathBuf::from(configured);
        }
    }
    if let Ok(configured) = fs::read_to_string(data_root_override_path()) {
        let configured = configured.trim();
        if !configured.is_empty() {
            return PathBuf::from(configured);
        }
    }
    let root = project_root();
    if is_source_checkout(&root) {
        root
    } else {
        user_data_root()
    }
}

pub fn set_data_root(path: &Path) -> io::Result<PathBuf> {
    let target = fs::canonicalize(path)?;
    if !target.is_dir() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "The data root must be a folder.",
        ));
    }
    if let Some(parent) = data_root_override_path().parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(data_root_override_path(), target.to_string_lossy().as_bytes())?;
    Ok(target)
}

pub fn settings_path() -> PathBuf {
    data_root().join("native.settings")
}

pub fn default_output_dir() -> PathBuf {
    data_root().join("converted")
}

pub fn default_fetched_dir() -> PathBuf {
    data_root().join("fetched")
}

pub fn now_stamp() -> u128 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|value| value.as_millis())
        .unwrap_or_default()
}

pub fn prepare_command(command: &mut Command) {
    let runtime_bins = runtime_bin_candidates()
        .into_iter()
        .filter(|path| path.is_dir())
        .collect::<Vec<_>>();
    if !runtime_bins.is_empty() {
        let mut paths = runtime_bins;
        if let Some(existing) = std::env::var_os("PATH") {
            paths.extend(std::env::split_paths(&existing));
        }
        if let Ok(path) = std::env::join_paths(paths) {
            command.env("PATH", path);
        }
    }
    command.env("JANECONVERTER_DATA_DIR", data_root());
    #[cfg(target_os = "windows")]
    command.creation_flags(CREATE_NO_WINDOW);
}

fn runtime_bin_candidates() -> Vec<PathBuf> {
    let mut candidates = vec![project_root().join("bin")];
    if let Ok(executable) = std::env::current_exe() {
        if let Some(directory) = executable.parent() {
            candidates.extend([
                directory.join("bin"),
                directory.join("resources").join("runtime").join("bin"),
                directory.join("runtime").join("bin"),
                directory.join("resources").join("bin"),
            ]);
        }
    }
    candidates
}

pub fn run_command(program: &str, args: &[&str]) -> io::Result<Output> {
    let mut command = Command::new(program);
    command.args(args);
    prepare_command(&mut command);
    command.output()
}

pub fn command_available(program: &str) -> bool {
    run_command(program, &["--version"])
        .map(|output| output.status.success())
        .unwrap_or(false)
}

pub fn find_ffmpeg() -> PathBuf {
    let root = project_root();
    let mut candidates = vec![
        root.join("bin").join(ffmpeg_name()),
        root.join(ffmpeg_name()),
    ];
    if let Ok(executable) = std::env::current_exe() {
        if let Some(directory) = executable.parent() {
            candidates.extend([
                directory.join(ffmpeg_name()),
                directory.join("bin").join(ffmpeg_name()),
                directory
                    .join("resources")
                    .join("runtime")
                    .join("bin")
                    .join(ffmpeg_name()),
                directory.join("runtime").join("bin").join(ffmpeg_name()),
                directory.join("resources").join("bin").join(ffmpeg_name()),
            ]);
        }
    }
    for candidate in candidates {
        if candidate.is_file() {
            return candidate;
        }
    }
    PathBuf::from(ffmpeg_name())
}

pub fn find_python() -> PathBuf {
    let root = project_root();
    if is_source_checkout(&root) {
        #[cfg(target_os = "windows")]
        return PathBuf::from("uv.exe");
        #[cfg(not(target_os = "windows"))]
        return PathBuf::from("uv");
    }
    root.join("engine").join(packaged_engine_name())
}

pub fn packaged_engine(path: &Path) -> bool {
    path.file_name()
        .and_then(|value| value.to_str())
        .map(|value| {
            value.eq_ignore_ascii_case("JaneConverterEngine.exe") || value == "JaneConverterEngine"
        })
        .unwrap_or(false)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn recognizes_packaged_engine_names_on_both_release_platforms() {
        assert!(packaged_engine(Path::new(
            "runtime/engine/JaneConverterEngine"
        )));
        assert!(packaged_engine(Path::new(
            "runtime/engine/JaneConverterEngine.exe"
        )));
        assert!(!packaged_engine(Path::new("uv")));
    }

    #[test]
    fn packaged_engine_lives_in_the_private_engine_directory() {
        let root = Path::new("resources/runtime");
        assert_eq!(
            root.join("engine").join(packaged_engine_name()),
            root.join("engine").join(if cfg!(target_os = "windows") {
                "JaneConverterEngine.exe"
            } else {
                "JaneConverterEngine"
            })
        );
    }
}

pub fn read_kv() -> HashMap<String, String> {
    let mut values = HashMap::new();
    if let Ok(content) = fs::read_to_string(settings_path()) {
        for line in content.lines() {
            if let Some((key, value)) = line.split_once('=') {
                values.insert(key.trim().to_owned(), value.trim().to_owned());
            }
        }
    }
    values
}

fn parse_bool(values: &HashMap<String, String>, key: &str, default: bool) -> bool {
    values
        .get(key)
        .and_then(|value| value.parse().ok())
        .unwrap_or(default)
}

pub fn detect_gpu() -> (bool, String) {
    let ffmpeg = find_ffmpeg();
    let output = run_command(
        ffmpeg.to_str().unwrap_or("ffmpeg"),
        &["-hide_banner", "-encoders"],
    );
    let text = output
        .ok()
        .map(|value| String::from_utf8_lossy(&value.stdout).to_ascii_lowercase())
        .unwrap_or_default();
    if text.contains("h264_nvenc") {
        return (true, "NVIDIA NVENC".into());
    }
    if text.contains("h264_amf") {
        return (true, "AMD AMF".into());
    }
    if text.contains("h264_qsv") {
        return (true, "Intel Quick Sync".into());
    }
    if text.contains("h264_videotoolbox") {
        return (true, "Apple VideoToolbox".into());
    }
    (false, "CPU mode".into())
}

pub fn settings_get_internal() -> ConverterSettings {
    let values = read_kv();
    let output_dir = values
        .get("output_dir")
        .filter(|value| !value.trim().is_empty())
        .cloned()
        .unwrap_or_else(|| default_output_dir().display().to_string());
    let fetched_dir = values
        .get("fetched_dir")
        .filter(|value| !value.trim().is_empty())
        .cloned()
        .unwrap_or_else(|| default_fetched_dir().display().to_string());
    let category = match values.get("category").map(String::as_str) {
        Some("Video") => "Video",
        Some("Image") => "Image",
        Some("Miscellaneous") => "Miscellaneous",
        _ => "Music",
    };
    let (gpu_available, _) = detect_gpu();
    ConverterSettings {
        output_dir,
        fetched_dir,
        category: category.into(),
        format: values
            .get("format")
            .cloned()
            .unwrap_or_else(|| "mp3".into()),
        bitrate: values
            .get("bitrate")
            .cloned()
            .unwrap_or_else(|| "320k".into()),
        sample_rate: values
            .get("sample_rate")
            .and_then(|value| value.parse().ok())
            .unwrap_or(48000),
        resolution: values
            .get("resolution")
            .cloned()
            .unwrap_or_else(|| "original".into()),
        normalize: parse_bool(&values, "normalize", false),
        use_gpu: parse_bool(&values, "use_gpu", gpu_available),
        save_cover: parse_bool(&values, "save_cover", true),
        save_metadata: parse_bool(&values, "save_metadata", true),
        retries: values
            .get("retries")
            .and_then(|value| value.parse().ok())
            .unwrap_or(2)
            .min(5),
    }
}

pub fn write_settings(settings: &ConverterSettings) -> io::Result<()> {
    if let Some(parent) = settings_path().parent() {
        fs::create_dir_all(parent)?;
    }
    let sample_rate = settings.sample_rate.to_string();
    let retries = settings.retries.min(5).to_string();
    let body = [
        ("output_dir", settings.output_dir.as_str()),
        ("fetched_dir", settings.fetched_dir.as_str()),
        ("category", settings.category.as_str()),
        ("format", settings.format.as_str()),
        ("bitrate", settings.bitrate.as_str()),
        ("sample_rate", sample_rate.as_str()),
        ("resolution", settings.resolution.as_str()),
        (
            "normalize",
            if settings.normalize { "true" } else { "false" },
        ),
        ("use_gpu", if settings.use_gpu { "true" } else { "false" }),
        (
            "save_cover",
            if settings.save_cover { "true" } else { "false" },
        ),
        (
            "save_metadata",
            if settings.save_metadata {
                "true"
            } else {
                "false"
            },
        ),
        ("retries", retries.as_str()),
    ]
    .iter()
    .map(|(key, value)| format!("{key}={value}\n"))
    .collect::<String>();
    fs::write(settings_path(), body)
}
