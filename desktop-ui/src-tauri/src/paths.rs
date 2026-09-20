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
    (directory.join("run_converter.py").is_file() && directory.join("engine").is_dir())
        || directory.join("JaneConverterEngine.exe").is_file()
}

pub fn data_root() -> PathBuf {
    std::env::var_os("JANECONVERTER_DATA_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(project_root)
}

pub fn settings_path() -> PathBuf {
    data_root().join("native.settings")
}

pub fn preference_path() -> PathBuf {
    data_root().join("frontend.preference")
}

pub fn default_output_dir() -> PathBuf {
    data_root().join("converted")
}

pub fn now_stamp() -> u128 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|value| value.as_millis())
        .unwrap_or_default()
}

pub fn prepare_command(command: &mut Command) {
    #[cfg(target_os = "windows")]
    command.creation_flags(CREATE_NO_WINDOW);
}

pub fn run_command(program: &str, args: &[&str]) -> io::Result<Output> {
    let mut command = Command::new(program);
    command.args(args);
    prepare_command(&mut command);
    command.output()
}

pub fn command_available(program: &str) -> bool {
    run_command(program, &["--version"]).is_ok()
}

pub fn find_ffmpeg() -> PathBuf {
    let root = project_root();
    #[cfg(target_os = "windows")]
    let candidates = [
        root.join("ffmpeg.exe"),
        root.join("bin").join("ffmpeg.exe"),
        root.join("engine").join("ffmpeg.exe"),
        root.join("resources").join("runtime").join("ffmpeg.exe"),
    ];
    #[cfg(not(target_os = "windows"))]
    let candidates = [
        root.join("ffmpeg"),
        root.join("bin").join("ffmpeg"),
        root.join("engine").join("ffmpeg"),
    ];
    for candidate in candidates {
        if candidate.is_file() {
            return candidate;
        }
    }
    #[cfg(target_os = "windows")]
    return PathBuf::from("ffmpeg.exe");
    #[cfg(not(target_os = "windows"))]
    PathBuf::from("ffmpeg")
}

pub fn find_python() -> PathBuf {
    let root = project_root();
    #[cfg(target_os = "windows")]
    let candidates = [
        root.join("JaneConverterEngine.exe"),
        root.join(".venv").join("Scripts").join("python.exe"),
        root.join("venv").join("Scripts").join("python.exe"),
    ];
    #[cfg(not(target_os = "windows"))]
    let candidates = [
        root.join(".venv").join("bin").join("python3"),
        root.join("venv").join("bin").join("python3"),
    ];
    for candidate in candidates {
        if candidate.is_file() {
            return candidate;
        }
    }
    #[cfg(target_os = "windows")]
    return PathBuf::from("python.exe");
    #[cfg(not(target_os = "windows"))]
    return PathBuf::from("python3");
}

pub fn packaged_engine(path: &Path) -> bool {
    path.file_name()
        .and_then(|value| value.to_str())
        .map(|value| value.eq_ignore_ascii_case("JaneConverterEngine.exe"))
        .unwrap_or(false)
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
    let output = run_command(ffmpeg.to_str().unwrap_or("ffmpeg"), &["-hide_banner", "-encoders"]);
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
    let category = match values.get("category").map(String::as_str) {
        Some("Video") => "Video",
        Some("Miscellaneous") => "Miscellaneous",
        _ => "Music",
    };
    let (gpu_available, _) = detect_gpu();
    ConverterSettings {
        output_dir,
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

pub fn read_preference() -> String {
    match fs::read_to_string(preference_path())
        .ok()
        .map(|value| value.trim().to_ascii_lowercase())
    {
        Some(value) if ["tauri", "rust", "python"].contains(&value.as_str()) => value,
        _ => "tauri".into(),
    }
}

pub fn write_preference(preference: &str) -> io::Result<()> {
    if !["tauri", "rust", "python"].contains(&preference) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "Unknown interface preference.",
        ));
    }
    if let Some(parent) = preference_path().parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(preference_path(), format!("{preference}\n"))
}
