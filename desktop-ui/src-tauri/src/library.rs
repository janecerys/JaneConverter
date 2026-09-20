use crate::model::LibraryEntry;
use crate::paths::{find_ffmpeg, now_stamp, prepare_command};
use base64::Engine;
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

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

fn image_extension(path: &Path) -> bool {
    matches!(
        path.extension()
            .and_then(|value| value.to_str())
            .unwrap_or_default()
            .to_ascii_lowercase()
            .as_str(),
        "jpg" | "jpeg" | "png" | "webp"
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

fn media_file_entry(path: &Path, bytes: u64) -> LibraryEntry {
    LibraryEntry {
        path: path.display().to_string(),
        name: path
            .file_name()
            .map(|value| value.to_string_lossy().into_owned())
            .unwrap_or_default(),
        is_directory: false,
        is_playlist: false,
        media_count: 1,
        total_bytes: bytes,
        extension: path
            .extension()
            .and_then(|value| value.to_str())
            .unwrap_or_default()
            .to_ascii_uppercase(),
    }
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
            result.push(media_file_entry(
                &child,
                entry
                    .metadata()
                    .map(|value| value.len())
                    .unwrap_or_default(),
            ));
        }
    }
    result.sort_by(|left, right| {
        (!left.is_directory, left.name.to_ascii_lowercase())
            .cmp(&(!right.is_directory, right.name.to_ascii_lowercase()))
    });
    Ok(result)
}

const MAX_RECENT_DEPTH: usize = 32;

fn collect_recent(
    path: &Path,
    depth: usize,
    result: &mut Vec<(SystemTime, LibraryEntry)>,
) -> Result<(), String> {
    if depth > MAX_RECENT_DEPTH {
        return Ok(());
    }
    for entry in fs::read_dir(path)
        .map_err(|error| format!("Could not read the converted library: {error}"))?
        .flatten()
    {
        let child = entry.path();
        let kind = entry.file_type().map_err(|error| error.to_string())?;
        if kind.is_symlink() {
            continue;
        }
        if kind.is_dir() {
            collect_recent(&child, depth + 1, result)?;
        } else if kind.is_file() && media_extension(&child) {
            let metadata = entry.metadata().map_err(|error| error.to_string())?;
            let modified = metadata.modified().unwrap_or(UNIX_EPOCH);
            result.push((modified, media_file_entry(&child, metadata.len())));
        }
    }
    Ok(())
}

pub fn recent(path: &str, limit: usize) -> Result<Vec<LibraryEntry>, String> {
    let input = PathBuf::from(path.trim());
    if !input.exists() {
        return Ok(Vec::new());
    }
    let root = fs::canonicalize(&input)
        .map_err(|error| format!("Could not read the converted library: {error}"))?;
    if !root.is_dir() {
        return Err("The converted library path is not a folder.".into());
    }

    let mut candidates = Vec::new();
    collect_recent(&root, 0, &mut candidates)?;
    candidates.sort_by(|left, right| {
        right.0.cmp(&left.0).then_with(|| {
            left.1
                .name
                .to_ascii_lowercase()
                .cmp(&right.1.name.to_ascii_lowercase())
        })
    });
    Ok(candidates
        .into_iter()
        .take(limit.clamp(1, 200))
        .map(|(_, entry)| entry)
        .collect())
}

fn canonical_library_item(root: &str, path: &str) -> Result<(PathBuf, PathBuf), String> {
    let root = fs::canonicalize(root.trim())
        .map_err(|error| format!("The library root is unavailable: {error}"))?;
    let target = fs::canonicalize(path.trim())
        .map_err(|error| format!("That library item is unavailable: {error}"))?;
    if target == root || !target.starts_with(&root) {
        return Err(
            "For safety, JaneConverter can only access items inside the active library.".into(),
        );
    }
    Ok((root, target))
}

pub fn delete_inside(root: &str, path: &str) -> Result<(), String> {
    let (_root, target) = canonical_library_item(root, path)?;
    if target.is_dir() {
        fs::remove_dir_all(target).map_err(|error| format!("Could not delete the folder: {error}"))
    } else {
        fs::remove_file(target).map_err(|error| format!("Could not delete the file: {error}"))
    }
}

fn copy_directory(source: &Path, destination: &Path) -> std::io::Result<()> {
    fs::create_dir(destination)?;
    for entry in fs::read_dir(source)? {
        let entry = entry?;
        let kind = entry.file_type()?;
        let source_child = entry.path();
        let destination_child = destination.join(entry.file_name());
        if kind.is_symlink() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidInput,
                "symbolic links are not supported in a library move",
            ));
        }
        if kind.is_dir() {
            copy_directory(&source_child, &destination_child)?;
        } else if kind.is_file() {
            fs::copy(&source_child, &destination_child)?;
        }
    }
    Ok(())
}

pub fn move_directory(source: &str, destination_parent: &str) -> Result<String, String> {
    let source_input = PathBuf::from(source.trim());
    let source_metadata = fs::symlink_metadata(&source_input)
        .map_err(|error| format!("The current library is unavailable: {error}"))?;
    if source_metadata.file_type().is_symlink() || !source_metadata.is_dir() {
        return Err("The current library must be a real folder.".into());
    }
    let source = fs::canonicalize(&source_input)
        .map_err(|error| format!("The current library is unavailable: {error}"))?;
    let parent = fs::canonicalize(destination_parent.trim())
        .map_err(|error| format!("The destination folder is unavailable: {error}"))?;
    if !parent.is_dir() {
        return Err("The destination must be a folder.".into());
    }
    if parent == source || parent.starts_with(&source) {
        return Err("The destination cannot be inside the current library.".into());
    }
    let name = source
        .file_name()
        .ok_or_else(|| "The current library has no usable folder name.".to_owned())?;
    let target = parent.join(name);
    if target.exists() {
        return Err(format!(
            "A folder named '{}' already exists at the destination.",
            name.to_string_lossy()
        ));
    }

    if fs::rename(&source, &target).is_ok() {
        return Ok(target.display().to_string());
    }

    let temporary = parent.join(format!(
        ".{}.janemove-{}",
        name.to_string_lossy(),
        now_stamp()
    ));
    copy_directory(&source, &temporary).map_err(|error| {
        let _ = fs::remove_dir_all(&temporary);
        format!("Could not copy the library to the destination: {error}")
    })?;
    if let Err(error) = fs::rename(&temporary, &target) {
        let _ = fs::remove_dir_all(&temporary);
        return Err(format!("Could not finalize the library move: {error}"));
    }
    if let Err(error) = fs::remove_dir_all(&source) {
        let _ = fs::remove_dir_all(&target);
        return Err(format!(
            "The library was not moved because the original could not be removed: {error}"
        ));
    }
    Ok(target.display().to_string())
}

fn first_preview_source(path: &Path, depth: usize) -> Option<PathBuf> {
    if depth > 4 {
        return None;
    }
    let kind = fs::symlink_metadata(path).ok()?.file_type();
    if kind.is_symlink() {
        return None;
    }
    if kind.is_file() && (media_extension(path) || image_extension(path)) {
        return Some(path.to_path_buf());
    }
    if !kind.is_dir() {
        return None;
    }

    for name in [
        "cover.jpg",
        "cover.jpeg",
        "cover.png",
        "cover.webp",
        "folder.jpg",
        "album.jpg",
    ] {
        let candidate = path.join("metadata").join(name);
        if candidate.is_file() {
            return Some(candidate);
        }
    }

    let mut entries = fs::read_dir(path).ok()?.flatten().collect::<Vec<_>>();
    entries.sort_by_key(|entry| entry.file_name());
    for entry in entries {
        if let Some(candidate) = first_preview_source(&entry.path(), depth + 1) {
            return Some(candidate);
        }
    }
    None
}

fn render_preview(path: &Path) -> Option<Vec<u8>> {
    let mut command = Command::new(find_ffmpeg());
    command.arg("-hide_banner").arg("-loglevel").arg("error");
    let extension = path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    if matches!(extension.as_str(), "mp4" | "mkv" | "webm" | "mov" | "gif") {
        command.arg("-ss").arg("1");
    }
    command
        .arg("-i")
        .arg(path)
        .arg("-map")
        .arg("0:v:0?")
        .arg("-frames:v")
        .arg("1")
        .arg("-vf")
        .arg("scale=320:320:force_original_aspect_ratio=decrease")
        .arg("-f")
        .arg("image2pipe")
        .arg("-vcodec")
        .arg("mjpeg")
        .arg("-q:v")
        .arg("5")
        .arg("-");
    command.stdout(Stdio::piped()).stderr(Stdio::null());
    prepare_command(&mut command);
    let mut child = command.spawn().ok()?;
    let deadline = Instant::now() + Duration::from_secs(3);
    loop {
        match child.try_wait() {
            Ok(Some(status)) => {
                if !status.success() {
                    return None;
                }
                let mut bytes = Vec::new();
                child.stdout.take()?.read_to_end(&mut bytes).ok()?;
                if bytes.is_empty() || bytes.len() > 2 * 1024 * 1024 {
                    return None;
                }
                return Some(bytes);
            }
            Ok(None) if Instant::now() < deadline => {
                std::thread::sleep(Duration::from_millis(25));
            }
            _ => {
                let _ = child.kill();
                let _ = child.wait();
                return None;
            }
        }
    }
}

pub fn thumbnail(root: &str, path: &str) -> Result<Option<String>, String> {
    let (_root, target) = canonical_library_item(root, path)?;
    let Some(source) = first_preview_source(&target, 0) else {
        return Ok(None);
    };
    let Some(bytes) = render_preview(&source) else {
        return Ok(None);
    };
    let encoded = base64::engine::general_purpose::STANDARD.encode(bytes);
    Ok(Some(format!("data:image/jpeg;base64,{encoded}")))
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

    #[test]
    fn preview_sources_include_covers_without_listing_them_as_media() {
        assert!(image_extension(Path::new("cover.jpg")));
        assert!(!media_extension(Path::new("cover.jpg")));
    }

    #[test]
    fn recent_returns_nested_media_and_ignores_non_media_files() {
        let root = std::env::temp_dir().join(format!("janec-recent-{}", crate::paths::now_stamp()));
        let nested = root.join("Videos").join("Facebook");
        fs::create_dir_all(&nested).expect("create recent test folders");
        fs::write(root.join("cover.jpg"), b"cover").expect("write cover");
        fs::write(root.join("first.mp4"), b"first").expect("write first media");
        fs::write(nested.join("second.mp3"), b"second").expect("write nested media");

        let entries =
            recent(root.to_str().expect("recent test path"), 10).expect("scan recent media");

        assert_eq!(entries.len(), 2);
        assert!(entries.iter().any(|entry| entry.name == "first.mp4"));
        assert!(entries.iter().any(|entry| entry.name == "second.mp3"));
        assert!(entries.iter().all(|entry| entry.extension != "JPG"));
        fs::remove_dir_all(root).expect("clean recent test folders");
    }
}
