use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ConverterSettings {
    pub output_dir: String,
    pub category: String,
    pub format: String,
    pub bitrate: String,
    pub sample_rate: u32,
    pub resolution: String,
    pub normalize: bool,
    pub use_gpu: bool,
    pub save_cover: bool,
    pub save_metadata: bool,
    pub retries: u8,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ConversionRequest {
    pub source: String,
    pub output_dir: String,
    pub category: String,
    pub format: String,
    pub bitrate: String,
    pub sample_rate: u32,
    pub resolution: String,
    pub normalize: bool,
    pub use_gpu: bool,
    pub save_cover: bool,
    pub save_metadata: bool,
    pub retries: u8,
    pub playlist_indexes: Option<String>,
    pub browser_session: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeInfo {
    pub mode: &'static str,
    pub python_ready: bool,
    pub ffmpeg_ready: bool,
    pub python_path: String,
    pub data_root: String,
    pub project_root: String,
    pub gpu_available: bool,
    pub gpu_label: String,
    pub packaged: bool,
    pub frontend_preference: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ConverterEvent {
    pub job_id: String,
    pub kind: String,
    pub message: String,
    pub progress: Option<f32>,
    pub output: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PlaylistItem {
    pub index: u32,
    pub title: String,
    pub artist: String,
    pub duration: String,
    pub url: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct PlaylistCatalog {
    pub title: String,
    pub items: Vec<PlaylistItem>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AccessStatus {
    pub active: bool,
    pub link: String,
    pub browser: String,
    pub bridge_connected: bool,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LibraryEntry {
    pub path: String,
    pub name: String,
    pub is_directory: bool,
    pub is_playlist: bool,
    pub media_count: usize,
    pub total_bytes: u64,
    pub extension: String,
}
