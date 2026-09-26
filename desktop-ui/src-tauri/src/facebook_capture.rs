use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use serde::Deserialize;
use std::collections::BTreeMap;
use url::Url;

use crate::model::FacebookPhoto;

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PageMessage {
    pub kind: String,
    #[serde(default)]
    pub title: String,
    #[serde(default)]
    pub error: String,
    #[serde(default)]
    pub count: usize,
    #[serde(default)]
    pub sequence: usize,
    #[serde(default)]
    pub photos: Vec<FacebookPhoto>,
}

#[derive(Debug, Default)]
pub struct CaptureAccumulator {
    pub title: String,
    pub photos: BTreeMap<String, FacebookPhoto>,
}

pub fn validate_post_url(value: &str) -> Result<Url, String> {
    let url =
        Url::parse(value.trim()).map_err(|_| "Paste a valid Facebook post link.".to_string())?;
    let host = url.host_str().unwrap_or_default().to_ascii_lowercase();
    let path = url.path().to_ascii_lowercase();
    if url.scheme() != "https"
        || !(host == "facebook.com" || host.ends_with(".facebook.com"))
        || !(path.starts_with("/share/p/")
            || path.contains("/permalink/")
            || path.contains("/posts/")
            || path.ends_with("/story.php"))
    {
        return Err("Paste a public Facebook post link to capture its photos.".into());
    }
    Ok(url)
}

pub fn is_facebook_navigation(value: &str) -> bool {
    Url::parse(value)
        .ok()
        .and_then(|url| url.host_str().map(str::to_ascii_lowercase))
        .is_some_and(|host| host == "facebook.com" || host.ends_with(".facebook.com"))
}

pub fn validate_photo_url(value: &str) -> bool {
    Url::parse(value).ok().is_some_and(|url| {
        let host = url.host_str().unwrap_or_default().to_ascii_lowercase();
        url.scheme() == "https"
            && url.username().is_empty()
            && url.password().is_none()
            && (host == "fbcdn.net"
                || host.ends_with(".fbcdn.net")
                || host == "fbsbx.com"
                || host.ends_with(".fbsbx.com"))
    })
}

pub fn message_from_title(title: &str, nonce: &str) -> Option<PageMessage> {
    let prefix = format!("__JANE_FACEBOOK_CAPTURE__{nonce}__");
    let encoded = title.strip_prefix(&prefix)?;
    let bytes = URL_SAFE_NO_PAD.decode(encoded).ok()?;
    serde_json::from_slice(&bytes).ok()
}

pub fn initialization_script(nonce: &str) -> String {
    let nonce_json = serde_json::to_string(nonce).expect("nonce is a string");
    format!(
        r#"(() => {{
  const nonce = {nonce_json};
  const prefix = "__JANE_FACEBOOK_CAPTURE__" + nonce + "__";
  const ackKey = "__JANE_FACEBOOK_ACK__" + nonce;
  window[ackKey] = 0;
  let scanned = new Set();
  let unchanged = 0;
  let previousCount = 0;
  let attempts = 0;
  let finished = false;
  let pending = [];
  let nextSequence = 0;
  let awaitingSequence = 0;
  const send = (value) => {{
    const bytes = new TextEncoder().encode(JSON.stringify(value));
    let binary = "";
    for (const byte of bytes) binary += String.fromCharCode(byte);
    document.title = prefix + btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
  }};
  const pageTitle = () => {{
    const meta = document.querySelector('meta[property="og:title"]');
    return (meta && meta.content) || document.title || "Facebook Post";
  }};
  const isCdn = (value) => {{
    try {{ const host = new URL(value, location.href).hostname.toLowerCase(); return host.endsWith(".fbcdn.net") || host === "fbcdn.net" || host.endsWith(".fbsbx.com") || host === "fbsbx.com"; }} catch (_) {{ return false; }}
  }};
  const chooseImage = (image) => {{
    const candidates = [];
    for (const value of [image.currentSrc, image.src, image.getAttribute("data-src")]) {{
      if (value && isCdn(value)) candidates.push({{url: value, width: image.naturalWidth || 0}});
    }}
    for (const entry of (image.getAttribute("srcset") || "").split(",")) {{
      const parts = entry.trim().split(/\s+/);
      if (parts[0] && isCdn(parts[0])) candidates.push({{url: parts[0], width: parseInt(parts[1] || "0", 10) || 0}});
    }}
    candidates.sort((a, b) => b.width - a.width);
    return candidates[0] || null;
  }};
  const closeGuestPrompt = () => {{
    const button = document.querySelector('button[aria-label="Close"], [role="button"][aria-label="Close"]');
    if (button) button.click();
  }};
  const findAlbumSet = () => {{
    for (const anchor of document.querySelectorAll('a[href*="fbid="]')) {{
      try {{
        const href = new URL(anchor.href, location.href);
        const set = href.searchParams.get("set");
        if (set && set.startsWith("pcb.")) return set;
      }} catch (_) {{}}
    }}
    return "";
  }};
  const scan = () => {{
    if (finished) return;
    attempts += 1;
    if (awaitingSequence && window[ackKey] === awaitingSequence) awaitingSequence = 0;
    closeGuestPrompt();
    if (location.pathname.toLowerCase().includes("/login")) {{
      finished = true;
      send({{kind:"error",error:"Facebook requires sign-in to view this post. JaneConverter only captures photos visible to logged-out visitors."}});
      return;
    }}
    if (!location.pathname.toLowerCase().includes("/media/set/")) {{
      const set = findAlbumSet();
      if (set) {{
        sessionStorage.setItem("janeFacebookCaptureTitle", pageTitle());
        location.replace("https://www.facebook.com/media/set/?set=" + encodeURIComponent(set));
        return;
      }}
    }} else {{
      const savedTitle = sessionStorage.getItem("janeFacebookCaptureTitle");
      const albumTitle = pageTitle();
      const title = savedTitle || (albumTitle && albumTitle !== "Facebook" ? albumTitle : "Facebook Photo Album");
      for (const anchor of document.querySelectorAll('a[href*="fbid="]')) {{
        let photoId = "";
        try {{ photoId = new URL(anchor.href, location.href).searchParams.get("fbid") || ""; }} catch (_) {{}}
        if (!/^[0-9]{{5,30}}$/.test(photoId) || scanned.has(photoId)) continue;
        const image = anchor.querySelector("img");
        const selected = image && chooseImage(image);
        if (!selected) continue;
        scanned.add(photoId);
        pending.push({{id:photoId,url:selected.url,width:selected.width}});
      }}
      if (pending.length && awaitingSequence === 0) {{
        awaitingSequence = ++nextSequence;
        send({{kind:"photos",sequence:awaitingSequence,photos:pending.splice(0,2),title}});
      }}
      const atBottom = window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 8;
      if (scanned.size === previousCount && atBottom) unchanged += 1;
      else unchanged = 0;
      previousCount = scanned.size;
      window.scrollTo(0, document.documentElement.scrollHeight);
      if (((unchanged >= 4 && scanned.size >= 2) || attempts >= 55) && pending.length === 0 && awaitingSequence === 0) {{
        finished = true;
        if (scanned.size >= 2) send({{kind:"done",count:scanned.size,title}});
        else send({{kind:"error",error:"No multi-photo album was visible to a logged-out visitor."}});
        return;
      }}
    }}
    if (attempts >= 55) {{
      finished = true;
      send({{kind:"error",error:"Facebook did not expose a complete public photo album in time."}});
    }}
    setTimeout(scan, 1000);
  }};
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => setTimeout(scan, 1000), {{once:true}});
  else setTimeout(scan, 1000);
}})();"#
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_facebook_post_links_are_accepted() {
        assert!(validate_post_url("https://www.facebook.com/share/p/abc123/").is_ok());
        assert!(validate_post_url("https://www.facebook.com/groups/42/permalink/123/").is_ok());
        assert!(validate_post_url("http://www.facebook.com/share/p/abc123/").is_err());
        assert!(validate_post_url("https://example.com/posts/123").is_err());
    }

    #[test]
    fn photo_urls_must_use_the_public_facebook_media_cdn() {
        assert!(validate_photo_url(
            "https://scontent.xx.fbcdn.net/photo.jpg?sig=sample"
        ));
        assert!(validate_photo_url("https://lookaside.fbsbx.com/photo.jpg"));
        assert!(!validate_photo_url("https://example.com/photo.jpg"));
        assert!(!validate_photo_url(
            "https://user@scontent.xx.fbcdn.net/photo.jpg"
        ));
    }

    #[test]
    fn capture_messages_are_bound_to_the_current_nonce() {
        let encoded = URL_SAFE_NO_PAD.encode(br#"{"kind":"done","count":2}"#);
        let title = format!("__JANE_FACEBOOK_CAPTURE__session-1__{encoded}");
        assert_eq!(message_from_title(&title, "session-1").unwrap().count, 2);
        assert!(message_from_title(&title, "another-session").is_none());
    }

    #[test]
    fn remote_capture_script_has_no_tauri_command_bridge() {
        let script = initialization_script("session-1");
        assert!(!script.contains("__TAURI__"));
        assert!(!script.contains("fetch("));
        assert!(script.contains("__JANE_FACEBOOK_CAPTURE__"));
        assert!(script.contains("__JANE_FACEBOOK_ACK__"));
        assert!(script.contains("pending.splice(0,2)"));
        assert!(script.contains("awaitingSequence === 0"));
    }
}
