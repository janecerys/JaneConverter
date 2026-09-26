use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use serde::Deserialize;
use std::collections::HashMap;
use url::Url;

use crate::model::{FacebookPhoto, SocialPhotoManifest};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SocialPlatform {
    Instagram,
    Twitter,
}

impl SocialPlatform {
    pub fn key(self) -> &'static str {
        match self {
            Self::Instagram => "instagram",
            Self::Twitter => "twitter",
        }
    }

    pub fn label(self) -> &'static str {
        match self {
            Self::Instagram => "Instagram",
            Self::Twitter => "X/Twitter",
        }
    }
}

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
    pub platform: String,
    #[serde(default)]
    pub photos: Vec<FacebookPhoto>,
}

#[derive(Debug, Default)]
pub struct CaptureAccumulator {
    pub title: String,
    pub photos: Vec<FacebookPhoto>,
    pub photo_indexes: HashMap<String, usize>,
}

pub fn validate_post_url(value: &str) -> Result<(SocialPlatform, Url), String> {
    let url = Url::parse(value.trim())
        .map_err(|_| "Paste a valid Instagram or X post link.".to_string())?;
    let host = url.host_str().unwrap_or_default().to_ascii_lowercase();
    let path = url.path().to_ascii_lowercase();
    let instagram = (host == "instagram.com" || host.ends_with(".instagram.com"))
        && path.starts_with("/p/")
        && path.trim_matches('/').split('/').count() == 2;
    let twitter_host = matches!(
        host.as_str(),
        "x.com" | "www.x.com" | "twitter.com" | "www.twitter.com"
    );
    let twitter = twitter_host
        && path.contains("/status/")
        && path.split("/status/").nth(1).is_some_and(|tail| {
            tail.split('/')
                .next()
                .is_some_and(|id| !id.is_empty() && id.bytes().all(|byte| byte.is_ascii_digit()))
        });
    if url.scheme() != "https" || url.username() != "" || url.password().is_some() {
        return Err("Paste a secure public Instagram or X post link.".into());
    }
    let platform = if instagram {
        SocialPlatform::Instagram
    } else if twitter {
        SocialPlatform::Twitter
    } else {
        return Err("Paste an Instagram photo post or X/Twitter post link.".into());
    };
    Ok((platform, url))
}

pub fn is_allowed_navigation(value: &str, platform: SocialPlatform) -> bool {
    let Some(host) = Url::parse(value)
        .ok()
        .and_then(|url| url.host_str().map(str::to_ascii_lowercase))
    else {
        return false;
    };
    match platform {
        SocialPlatform::Instagram => host == "instagram.com" || host.ends_with(".instagram.com"),
        SocialPlatform::Twitter => matches!(
            host.as_str(),
            "x.com" | "www.x.com" | "twitter.com" | "www.twitter.com"
        ),
    }
}

pub fn validate_photo_url(value: &str, platform: SocialPlatform) -> bool {
    Url::parse(value).ok().is_some_and(|url| {
        let host = url.host_str().unwrap_or_default().to_ascii_lowercase();
        let allowed = match platform {
            SocialPlatform::Instagram => ["cdninstagram.com", "fbcdn.net", "fbsbx.com"]
                .iter()
                .any(|suffix| host == *suffix || host.ends_with(&format!(".{suffix}"))),
            SocialPlatform::Twitter => host == "pbs.twimg.com",
        };
        url.scheme() == "https" && url.username().is_empty() && url.password().is_none() && allowed
    })
}

pub fn message_from_title(title: &str, nonce: &str) -> Option<PageMessage> {
    let prefix = format!("__JANE_SOCIAL_PHOTO_CAPTURE__{nonce}__");
    let encoded = title.strip_prefix(&prefix)?;
    let bytes = URL_SAFE_NO_PAD.decode(encoded).ok()?;
    serde_json::from_slice(&bytes).ok()
}

pub fn initialization_script(nonce: &str, platform: SocialPlatform) -> String {
    let nonce_json = serde_json::to_string(nonce).expect("nonce is a string");
    let platform_json = serde_json::to_string(platform.key()).expect("platform is a string");
    format!(
        r#"(() => {{
  const nonce = {nonce_json};
  const platform = {platform_json};
  const prefix = "__JANE_SOCIAL_PHOTO_CAPTURE__" + nonce + "__";
  const ackKey = "__JANE_SOCIAL_PHOTO_ACK__" + nonce;
  window[ackKey] = 0;
  const photos = new Map();
  let pending = [];
  let sequence = 0;
  let waiting = 0;
  let attempts = 0;
  let unchanged = 0;
  let lastCount = 0;
  let finished = false;
  let inFlight = null;
  let retryAfterAttempt = 0;
  let retryCount = 0;
  const send = (value) => {{
    const bytes = new TextEncoder().encode(JSON.stringify(value));
    let binary = "";
    for (const byte of bytes) binary += String.fromCharCode(byte);
    document.title = prefix + btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
  }};
  const sendFinal = (value) => {{
    finished = true;
    let retries = 0;
    const publish = () => {{
      send({{...value,retry:retries++}});
      if (retries < 4) setTimeout(publish, 700);
    }};
    publish();
  }};
  const isCdn = (value) => {{
    try {{
      const host = new URL(value, location.href).hostname.toLowerCase();
      return platform === "instagram"
        ? host === "fbcdn.net" || host.endsWith(".fbcdn.net") || host === "fbsbx.com" || host.endsWith(".fbsbx.com") || host === "cdninstagram.com" || host.endsWith(".cdninstagram.com")
        : host === "pbs.twimg.com";
    }} catch (_) {{ return false; }}
  }};
  const chooseImage = (image) => {{
    const candidates = [];
    const add = (url, width) => {{ if (url && isCdn(url)) candidates.push({{url, width: Number(width) || 0}}); }};
    add(image.currentSrc, image.naturalWidth);
    add(image.src, image.naturalWidth);
    add(image.getAttribute("data-src"), image.naturalWidth);
    for (const entry of (image.getAttribute("srcset") || "").split(",")) {{
      const parts = entry.trim().split(/\s+/);
      if (parts[0]) add(parts[0], parseInt(parts[1] || "0", 10));
    }}
    candidates.sort((a, b) => b.width - a.width);
    return candidates[0] || null;
  }};
  const imageId = (value) => {{
    try {{
      const url = new URL(value, location.href);
      const name = url.pathname.split("/").filter(Boolean).pop() || "";
      return name.replace(/\.[a-z0-9]+$/i, "").replace(/[^A-Za-z0-9_-]/g, "_").slice(0, 200);
    }} catch (_) {{ return ""; }}
  }};
  const pageTitle = () => {{
    const meta = document.querySelector('meta[property="og:title"]');
    const article = document.querySelector("article");
    const text = article && article.innerText ? article.innerText.slice(0, 140) : "";
    return ((meta && meta.content) || text || document.title || (platform === "instagram" ? "Instagram Post" : "X Post")).slice(0, 500);
  }};
  const closeGuestPrompt = () => {{
    const button = document.querySelector('button[aria-label="Close"], [role="button"][aria-label="Close"]');
    if (button) button.click();
  }};
  const postContainer = () => {{
    const articles = Array.from(document.querySelectorAll("article"));
    if (platform === "instagram") {{
      const postId = location.pathname.match(/^\/p\/([^/]+)\/?$/i)?.[1];
      const permalink = postId && Array.from(document.querySelectorAll("a[href]")).find(anchor => {{
        try {{ return new URL(anchor.href, location.href).pathname.match(/\/p\/([^/]+)\/?$/i)?.[1] === postId; }}
        catch (_) {{ return false; }}
      }});
      if (permalink) {{
        for (let container = permalink.parentElement; container && container !== document.body; container = container.parentElement) {{
          const hasPublicPostImage = Array.from(container.querySelectorAll("img")).some(image => {{
            const rect = image.getBoundingClientRect();
            return rect.width >= 120 && rect.height >= 120 && chooseImage(image);
          }});
          if (hasPublicPostImage) return container;
        }}
      }}
      const legacyPost = articles[0] || document.querySelector('[role="dialog"]');
      if (legacyPost && Array.from(legacyPost.querySelectorAll("img")).some(image => {{
        const rect = image.getBoundingClientRect();
        return rect.width >= 120 && rect.height >= 120 && chooseImage(image);
      }})) return legacyPost;
      return null;
    }}
    const statusId = location.pathname.match(/\/status\/(\d+)/i)?.[1];
    const matching = articles.find(article => !statusId || Array.from(article.querySelectorAll('a[href*="/status/"]')).some(link => link.href.includes("/status/" + statusId)));
    return matching || articles[0] || document.querySelector('[role="dialog"]') || document;
  }};
  const collectPhotos = () => {{
    const container = postContainer();
    if (!container) return;
    for (const image of container.querySelectorAll("img")) {{
      const rect = image.getBoundingClientRect();
      if (rect.width < 120 || rect.height < 120) continue;
      const selected = chooseImage(image);
      if (!selected) continue;
      const id = imageId(selected.url);
      if (!id) continue;
      const existing = photos.get(id);
      if (!existing || selected.width > existing.width) {{
        const photo = {{id, url:selected.url, width:selected.width}};
        photos.set(id, photo);
        const pendingIndex = pending.findIndex(item => item.id === id);
        if (pendingIndex >= 0) pending[pendingIndex] = photo;
        else pending.push(photo);
      }}
    }}
  }};
  const nextButton = () => {{
    const container = postContainer();
    if (!container) return null;
    return Array.from(container.querySelectorAll('button[aria-label], [role="button"][aria-label]'))
      .find(button => /^(next|next photo|next image)$/i.test(button.getAttribute("aria-label") || ""));
  }};
  const flush = (title) => {{
    if (!pending.length || waiting) return false;
    const batch = pending.splice(0, 2);
    waiting = ++sequence;
    inFlight = {{kind:"photos",sequence,photos:batch,title,platform}};
    retryCount = 0;
    retryAfterAttempt = attempts + 3;
    send(inFlight);
    return true;
  }};
  const scan = () => {{
    if (finished) return;
    attempts += 1;
    if (waiting && window[ackKey] === waiting) {{
      waiting = 0;
      inFlight = null;
    }} else if (waiting && inFlight && attempts >= retryAfterAttempt) {{
      retryCount += 1;
      send({{...inFlight,retry:retryCount}});
      retryAfterAttempt = attempts + 3;
    }}
    closeGuestPrompt();
    const path = location.pathname.toLowerCase();
    if (path.includes("/accounts/login") || path.includes("/i/flow/login") || path.includes("/challenge/") || path.includes("/checkpoint/")) {{
      sendFinal({{kind:"error",error:platform === "instagram" ? "Instagram requires sign-in to view this post. JaneConverter only captures photos visible to logged-out visitors." : "X requires sign-in to view this post. JaneConverter only captures photos visible to logged-out visitors."}});
      return;
    }}
    collectPhotos();
    const title = pageTitle();
    if (pending.length && !waiting) {{ flush(title); }}
    const currentCount = photos.size;
    if (currentCount === lastCount) unchanged = Math.min(unchanged + 1, 20);
    else unchanged = 0;
    lastCount = currentCount;
    if (platform === "instagram" && !waiting && !pending.length) {{
      const next = nextButton();
      if (next && next.getAttribute("aria-disabled") !== "true" && !next.disabled) {{
        next.click();
        unchanged = 0;
        setTimeout(scan, 850);
        return;
      }}
    }}
    const noPhotoWait = platform === "instagram" && !postContainer() ? 15 : 6;
    if (attempts >= noPhotoWait && unchanged >= 3 && !waiting && !pending.length) {{
      if (photos.size) sendFinal({{kind:"done",count:photos.size,title,platform}});
      else if (platform === "twitter") sendFinal({{kind:"no_photos",count:0,title,platform}});
      else sendFinal({{kind:"error",error:"No public Instagram photos were visible in this post."}});
      return;
    }}
    if (attempts >= 60) {{
      sendFinal({{kind:"error",error:platform === "instagram" ? "Instagram did not expose a complete public carousel in time." : "X did not expose the post photos to a logged-out visitor."}});
      return;
    }}
    setTimeout(scan, 900);
  }};
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => setTimeout(scan, 1000), {{once:true}});
  else setTimeout(scan, 1000);
}})();"#
    )
}

pub fn manifest(
    platform: SocialPlatform,
    title: String,
    photos: Vec<FacebookPhoto>,
) -> SocialPhotoManifest {
    SocialPhotoManifest {
        platform: platform.key().to_string(),
        title,
        photos,
    }
}
