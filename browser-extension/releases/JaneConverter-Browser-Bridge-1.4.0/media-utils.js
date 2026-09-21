(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.JaneMediaUtils = api;
  }
}(typeof globalThis === "object" ? globalThis : this, function () {
  const DIRECT_EXTENSIONS = /\.(mp3|m4a|aac|ogg|oga|opus|wav|flac|weba|mp4|m4v|webm|mov|mkv|avi|flv|3gp|jpe?g|png|gif|webp|avif|heic)(?:[?#]|$)/i;
  const STREAM_EXTENSIONS = /\.(m3u8|mpd)(?:[?#]|$)/i;
  const RANGE_PARAMS = ["bytestart", "byteend", "range", "rn", "rbuf"];
  // Explicit site and CDN registry for privileged browser-session fetches.
  // Page-provided URLs are never treated as unrestricted fetch targets.
  const SESSION_PLATFORMS = Object.freeze([
    { id: "facebook", pages: ["facebook.com", "fb.watch"], media: ["facebook.com", "fbcdn.net", "fbsbx.com"] },
    { id: "instagram", pages: ["instagram.com"], media: ["instagram.com", "cdninstagram.com", "fbcdn.net"] },
    { id: "x", pages: ["x.com", "twitter.com"], media: ["x.com", "twitter.com", "twimg.com"] },
    { id: "tiktok", pages: ["tiktok.com"], media: ["tiktok.com", "tiktokcdn.com", "ibytedtos.com", "byteoversea.com"] },
    { id: "youtube", pages: ["youtube.com", "youtu.be"], media: ["youtube.com", "youtu.be", "googlevideo.com", "ytimg.com"] },
    { id: "reddit", pages: ["reddit.com", "redd.it"], media: ["reddit.com", "redd.it", "redditmedia.com"] },
    { id: "vimeo", pages: ["vimeo.com"], media: ["vimeo.com", "vimeocdn.com"] },
    { id: "twitch", pages: ["twitch.tv"], media: ["twitch.tv", "ttvnw.net"] },
    { id: "dailymotion", pages: ["dailymotion.com"], media: ["dailymotion.com", "dmcdn.net"] },
    { id: "soundcloud", pages: ["soundcloud.com"], media: ["soundcloud.com", "sndcdn.com"] },
    { id: "rumble", pages: ["rumble.com"], media: ["rumble.com", "rmbl.ws"] }
  ]);

  function hostMatches(host, root) {
    const value = String(host || "").toLowerCase().replace(/\.$/, "");
    const allowed = String(root || "").toLowerCase().replace(/\.$/, "");
    return Boolean(value && allowed) && (value === allowed || value.endsWith("." + allowed));
  }

  function parsedHttpsUrl(value) {
    try {
      const parsed = new URL(value);
      if (parsed.protocol !== "https:" || parsed.username || parsed.password || (parsed.port && parsed.port !== "443")) return null;
      return parsed;
    } catch (_) {
      return null;
    }
  }

  function sessionPlatformForPage(pageUrl) {
    const parsed = parsedHttpsUrl(pageUrl);
    if (!parsed) return null;
    return SESSION_PLATFORMS.find(function (platform) {
      return platform.pages.some(function (host) { return hostMatches(parsed.hostname, host); });
    }) || null;
  }

  function isAllowedSessionMediaUrl(pageUrl, mediaUrl) {
    const platform = sessionPlatformForPage(pageUrl);
    const parsed = parsedHttpsUrl(mediaUrl);
    return Boolean(platform && parsed && platform.media.some(function (host) {
      return hostMatches(parsed.hostname, host);
    }));
  }

  function isExpectedMediaResponse(mediaKind, contentType) {
    const type = String(contentType || "").split(";", 1)[0].trim().toLowerCase();
    return (mediaKind === "video" && type.startsWith("video/"))
      || (mediaKind === "audio" && type.startsWith("audio/"))
      || (mediaKind === "image" && type.startsWith("image/"));
  }

  function networkMediaCandidate(url, contentType, resourceType) {
    const value = String(url || "");
    const type = String(contentType || "").split(";", 1)[0].trim().toLowerCase();
    let mediaKind = classify(value, type);
    if (mediaKind === "stream") {
      return { accepted: false, reason: "adaptive stream manifest" };
    }
    if (!mediaKind && String(resourceType || "").toLowerCase() === "media" && isStreamSegment(value, type)) {
      mediaKind = "video";
    }
    if (!mediaKind || !["video", "audio", "image"].includes(mediaKind)) {
      return { accepted: false, reason: "not a media response" };
    }
    return { accepted: true, mediaKind: mediaKind, contentType: type || "application/octet-stream" };
  }

  function networkMinimumBytes(mediaKind) {
    if (mediaKind === "image") return 8 * 1024;
    return 32 * 1024;
  }

  function networkCaptureDisposition(mediaKind, byteLength) {
    const size = Number(byteLength || 0);
    if (!Number.isFinite(size) || size < networkMinimumBytes(mediaKind)) {
      return { accepted: false, reason: "below media size floor" };
    }
    return { accepted: true };
  }

  function classify(url, contentType) {
    const value = String(url || "");
    const type = String(contentType || "").toLowerCase();
    if (STREAM_EXTENSIONS.test(value) || type.includes("mpegurl") || type.includes("dash+xml")) {
      return "stream";
    }
    if (type.startsWith("video/")) return "video";
    if (type.startsWith("audio/")) return "audio";
    if (type.startsWith("image/")) return "image";
    const extension = /\.([a-z0-9]{2,5})(?:[?#]|$)/i.exec(value);
    if (!extension || !DIRECT_EXTENSIONS.test(value)) return null;
    if (/^(jpe?g|png|gif|webp|avif|heic)$/i.test(extension[1])) return "image";
    if (/^(mp3|m4a|aac|ogg|oga|opus|wav|flac|weba)$/i.test(extension[1])) return "audio";
    return "video";
  }

  function normalizeMediaUrl(url) {
    try {
      const parsed = new URL(url);
      let wasRanged = false;
      for (const parameter of RANGE_PARAMS) {
        if (parsed.searchParams.has(parameter)) {
          parsed.searchParams.delete(parameter);
          wasRanged = true;
        }
      }
      return { url: parsed.toString(), wasRanged };
    } catch (_) {
      return { url: String(url || ""), wasRanged: false };
    }
  }

  function isStreamSegment(url, contentType) {
    const value = String(url || "");
    const type = String(contentType || "").toLowerCase();
    return /\.(ts|m4s)(?:[?#]|$)/i.test(value)
      || /\/videoplayback\b|googlevideo\.com\//i.test(value)
      || /[/_-](seg|segment|chunk|frag)[-_/.]?\d/i.test(value)
      || /segment/i.test(type);
  }

  function isSocialMediaImage(url) {
    const value = String(url || "");
    return /\.(jpe?g|png|gif|webp|svg|ico|bmp|avif|heic)(?:[?#]|$)/i.test(value)
      || (/fbcdn\.net\//i.test(value) && /\/[ps]\d{2,4}x\d{2,4}\//i.test(value));
  }

  function filenameFromUrl(url, kind, index) {
    try {
      const path = new URL(url).pathname.split("/").pop() || "";
      const clean = decodeURIComponent(path)
        .replace(/[^a-z0-9._-]+/gi, "-")
        .replace(/^-+|-+$/g, "");
      if (clean && /\.[a-z0-9]{2,5}$/i.test(clean)) return clean.slice(-180);
    } catch (_) {}
    const extension = kind === "image" ? "jpg" : kind === "audio" ? "mp3" : "webm";
    return "browser-capture-" + (Number(index) + 1) + "." + extension;
  }

  function selectCaptureItems(items, mode, maxItems) {
    const unique = new Map();
    for (const item of Array.isArray(items) ? items : []) {
      if (!item || !item.mediaKind) continue;
      const normalized = item.mediaUrl && normalizeMediaUrl(item.mediaUrl).url;
      const key = normalized || (item.mediaKind + ":" + item.frameId + ":" + item.elementIndex);
      if (!unique.has(key)) unique.set(key, item);
    }
    const usable = Array.from(unique.values()).filter(function (item) {
      if (item.storyCandidate === false) return false;
      if (item.source === "page-network" && item.mediaKind === "image" && item.storyCandidate !== true) return false;
      return item.mediaKind !== "video" || item.captureable !== false || !item.mediaUrl;
    });
    const ranked = usable.sort(function (left, right) {
      return Number(Boolean(right.storyCandidate)) - Number(Boolean(left.storyCandidate))
        || Number(Boolean(right.playing)) - Number(Boolean(left.playing))
        || Number(Boolean(right.visible)) - Number(Boolean(left.visible))
        || Number(left.source === "page-network") - Number(right.source === "page-network")
        || Number(right.surfaceScore || 0) - Number(left.surfaceScore || 0)
        || Number(right.size || 0) - Number(left.size || 0);
    });
    return ranked.slice(0, mode === "sequence" ? maxItems : 1);
  }

  return {
    classify,
    filenameFromUrl,
    isSocialMediaImage,
    isStreamSegment,
    isAllowedSessionMediaUrl,
    isExpectedMediaResponse,
    networkCaptureDisposition,
    networkMediaCandidate,
    normalizeMediaUrl,
    sessionPlatformForPage,
    selectCaptureItems
  };
}));
