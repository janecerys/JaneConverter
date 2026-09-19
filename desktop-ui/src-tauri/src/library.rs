use crate::model::LibraryEntry;
use std::fs;
use std::path::Path;

pub fn media_extension(path: &Path) -> bool {
    matches!(
        path.extension()
            .and_then(|value| value.to_str())
            .unwrap_or_default()
            .to_ascii_lowercase()
            .as_str(),
        "mp3" | "flac" | "wav" | "aac" | "m4a" | "ogg" | "mp4" | "mkv" | "webm" | "mov" | "gif"
    )
}

fn directory_summary(path: &Path) -> (usize, u64) {
    let mut count = 0;
    let mut bytes = 0;
    let Ok(entries) = fs::read_dir(path) else {
        return (0, 0);
    };
    for entry in entries.flatten() {
        let child = entry.path();
        let Ok(kind) = entry.file_type() else {
            continue;
        };
        if kind.is_dir() {
            let (nested_count, nested_bytes) = directory_summary(&child);
            count += nested_count;
            bytes += nested_bytes;
        } else if kind.is_file() && media_extension(&child) {
            count += 1;
            bytes += entry
                .metadata()
                .map(|value| value.len())
                .unwrap_or_default();
        }
    }
    (count, bytes)
}

pub fn scan(path: &str) -> Result<Vec<LibraryEntry>, String> {
    let root = std::path::PathBuf::from(path.trim());
    if !root.exists() {
        return Ok(Vec::new());
    }
    let mut result = Vec::new();
    for entry in fs::read_dir(&root)
        .map_err(|error| format!("Could not read the converted library: {error}"))?
        .flatten()
    {
        let child = entry.path();
        let kind = entry.file_type().map_err(|error| error.to_string())?;
        let name = entry.file_name().to_string_lossy().into_owned();
        if kind.is_dir() {
            let (count, bytes) = directory_summary(&child);
            result.push(LibraryEntry {
                path: child.display().to_string(),
                name,
                is_directory: true,
                is_playlist: child
                    .join("metadata")
                    .join("playlist_credits.txt")
                    .is_file(),
                media_count: count,
                total_bytes: bytes,
                extension: String::new(),
            });
        } else if kind.is_file() && media_extension(&child) {
            result.push(LibraryEntry {
                path: child.display().to_string(),
                name,
                is_directory: false,
                is_playlist: false,
                media_count: 1,
                total_bytes: entry
                    .metadata()
                    .map(|value| value.len())
                    .unwrap_or_default(),
                extension: child
                    .extension()
                    .and_then(|value| value.to_str())
                    .unwrap_or_default()
                    .to_ascii_uppercase(),
            });
        }
    }
    result.sort_by(|left, right| {
        (!left.is_directory, left.name.to_ascii_lowercase())
            .cmp(&(!right.is_directory, right.name.to_ascii_lowercase()))
    });
    Ok(result)
}

pub fn delete_inside(root: &str, path: &str) -> Result<(), String> {
    let root = fs::canonicalize(root.trim())
        .map_err(|error| format!("The library root is unavailable: {error}"))?;
    let target = fs::canonicalize(path.trim())
        .map_err(|error| format!("That library item is unavailable: {error}"))?;
    if target == root || !target.starts_with(&root) {
        return Err(
            "For safety, JaneConverter can only delete items inside the active library.".into(),
        );
    }
    if target.is_dir() {
        fs::remove_dir_all(target).map_err(|error| format!("Could not delete the folder: {error}"))
    } else {
        fs::remove_file(target).map_err(|error| format!("Could not delete the file: {error}"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn media_extension_accepts_audio_and_video() {
        assert!(media_extension(Path::new("song.flac")));
        assert!(media_extension(Path::new("clip.MP4")));
        assert!(!media_extension(Path::new("notes.txt")));
    }
}
