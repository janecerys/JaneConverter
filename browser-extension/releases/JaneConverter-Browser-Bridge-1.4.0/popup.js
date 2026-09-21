const currentButton = document.getElementById("current");
const sequenceButton = document.getElementById("sequence");
const collectButton = document.getElementById("collect");
const networkButton = document.getElementById("network");
const statusElement = document.getElementById("status");

const MAX_CHUNK_BYTES = 1024 * 1024;
const MAX_SEQUENCE_ITEMS = 24;
const MAX_SEQUENCE_MS = 45 * 1000;
const STORY_QUIET_MS = 8 * 1000;
const MAX_RENDERED_CAPTURE_BYTES = 64 * 1024 * 1024;
const MEDIA_FETCH_TIMEOUT_MS = 8 * 1000;

function setStatus(message, kind) {
  statusElement.textContent = message;
  statusElement.className = kind || "";
}

async function findAccessTabs() {
  const tabs = await chrome.tabs.query({});
  return tabs.filter(function (tab) {
    if (!tab.url) return false;
    try {
      const url = new URL(tab.url);
      return (url.hostname === "127.0.0.1" || url.hostname === "localhost")
        && /^\/access\/[^/]+(?:\/ready)?\/?$/.test(url.pathname);
    } catch (_) {
      return false;
    }
  }).sort(function (left, right) {
    return Number(Boolean(right.active)) - Number(Boolean(left.active));
  });
}

function accessEndpoint(tab, suffix) {
  const url = new URL(tab.url);
  const match = url.pathname.match(/^\/access\/[^/]+/);
  if (!match) throw new Error("The JaneConverter access page is no longer open.");
  return url.origin + match[0] + suffix;
}

async function readJson(response) {
  const body = await response.text();
  try {
    return JSON.parse(body);
  } catch (_) {
    throw new Error("JaneConverter returned an unexpected page (HTTP " + response.status + "). Reopen and confirm a fresh access link.");
  }
}

function sameSite(left, right) {
  left = left.toLowerCase().replace(/\.$/, "");
  right = right.toLowerCase().replace(/\.$/, "");
  return left === right || left.endsWith("." + right) || right.endsWith("." + left);
}

async function requestOriginPermission(mediaUrl) {
  const parsed = new URL(mediaUrl);
  if (parsed.protocol !== "https:") {
    throw new Error("Browser-session fetching only permits HTTPS media.");
  }
  const origin = parsed.protocol + "//" + parsed.host + "/*";
  if (await chrome.permissions.contains({ origins: [origin] })) return;
  let granted = false;
  try {
    granted = await chrome.permissions.request({ origins: [origin] });
  } catch (_) {
    throw new Error("Allow access to " + parsed.host + " in the browser prompt, then try again.");
  }
  if (!granted) throw new Error("Permission for " + parsed.host + " was not approved.");
}

async function requestSessionFetchPermissions(pageUrl, mediaUrl) {
  if (!globalThis.JaneMediaUtils || !globalThis.JaneMediaUtils.isAllowedSessionMediaUrl(pageUrl, mediaUrl)) {
    throw new Error("JaneConverter does not use browser-session access for this media host.");
  }
  await requestOriginPermission(pageUrl);
  await requestOriginPermission(mediaUrl);
}

async function captureThroughAuthenticatedSession(sourceTab, item, mode) {
  await requestSessionFetchPermissions(sourceTab.url, item.mediaUrl);
  const result = await chrome.runtime.sendMessage({
    type: "jane-authenticated-fetch",
    payload: {
      pageUrl: sourceTab.url,
      mediaUrl: item.mediaUrl,
      mediaKind: item.mediaKind,
      captureMode: mode,
      fileName: item.fileName,
      title: item.title
    }
  });
  if (!result || !result.ok) {
    throw new Error(result && result.error || "The authenticated browser fetch did not complete.");
  }
  return result;
}

function describeFetchFailure(stage, url, error) {
  let host = "";
  try {
    host = " (" + new URL(url).host + ")";
  } catch (_) {}
  const detail = error instanceof Error && error.message ? ": " + error.message : "";
  return stage + host + " failed" + detail + ".";
}

async function bridgeFetch(url, options, stage) {
  try {
    return await fetch(url, options);
  } catch (error) {
    throw new Error(describeFetchFailure(stage, url, error));
  }
}

async function fetchWithTimeout(url, options) {
  const controller = new AbortController();
  const timer = setTimeout(function () {
    controller.abort();
  }, MEDIA_FETCH_TIMEOUT_MS);
  try {
    return await fetch(url, Object.assign({}, options || {}, { signal: controller.signal }));
  } finally {
    clearTimeout(timer);
  }
}

async function findSourceTab(sourceUrl) {
  if (!sourceUrl) {
    const tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    const activePage = tabs.find(function (tab) {
      if (!tab.url || typeof tab.id !== "number") return false;
      try {
        const url = new URL(tab.url);
        return url.protocol === "http:" || url.protocol === "https:";
      } catch (_) {
        return false;
      }
    });
    if (!activePage) throw new Error("Keep the media page open in this browser, then retry.");
    return activePage;
  }
  const source = new URL(sourceUrl);
  const tabs = await chrome.tabs.query({});
  const matching = tabs.filter(function (tab) {
    if (!tab.url || typeof tab.id !== "number") return false;
    try {
      return sameSite(new URL(tab.url).hostname, source.hostname);
    } catch (_) {
      return false;
    }
  }).sort(function (left, right) {
    return Number(Boolean(right.active)) - Number(Boolean(left.active));
  });
  if (!matching.length) {
    throw new Error("Keep the signed-in " + source.hostname + " source page open in this browser.");
  }
  return matching[0];
}

function probePage() {
  const state = window.__janeConverterBrowserProbe__ || {
    installed: false,
    network: [],
    seen: []
  };
  const hasSeen = function (url) { return state.seen.indexOf(url) >= 0; };
  const remember = function (url, mimeType) {
    if (typeof url !== "string" || !/^https?:\/\//i.test(url) || hasSeen(url)) return;
    const type = String(mimeType || "").toLowerCase();
    const kind = type.startsWith("video/")
      ? "video"
      : type.startsWith("audio/")
        ? "audio"
        : type.startsWith("image/")
          ? "image"
          : /\.(mp3|m4a|aac|ogg|oga|opus|wav|flac|weba)(?:[?#]|$)/i.test(url)
            ? "audio"
            : /\.(jpe?g|png|gif|webp|avif|heic)(?:[?#]|$)/i.test(url)
              ? "image"
              : /\.(m3u8|mpd)(?:[?#]|$)/i.test(url)
                ? "stream"
                : /\.(mp4|m4v|webm|mov|mkv|avi|flv|3gp)(?:[?#]|$)/i.test(url)
                  ? "video"
                  : "";
    if (!kind) return;
    state.seen.push(url);
    state.network.push({
      mediaUrl: url,
      mediaKind: kind === "stream" ? "video" : kind,
      mimeType: String(mimeType || ""),
      fileName: "browser-capture-" + (state.network.length + 1) + "." + (kind === "image" ? "jpg" : kind === "audio" ? "mp3" : "webm"),
      title: document.title || "Browser capture",
      pageUrl: location.href,
      source: "page-network",
      captureable: kind !== "stream"
    });
    if (state.seen.length > 128) state.seen.shift();
    if (state.network.length > 64) state.network.shift();
  };
  const elements = [];
  const seenElements = new Set();
  const visit = function (root) {
    if (!root || typeof root.querySelectorAll !== "function") return;
    for (const element of root.querySelectorAll("*")) {
      const tag = element.tagName.toLowerCase();
      if ((tag === "video" || tag === "audio" || tag === "img" || tag === "canvas") && !seenElements.has(element)) {
        seenElements.add(element);
        elements.push(element);
      }
      if (element.shadowRoot) visit(element.shadowRoot);
    }
  };
  visit(document);
  const dom = elements.map(function (element, index) {
    const tag = element.tagName.toLowerCase();
    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    const area = Math.max(0, rect.width) * Math.max(0, rect.height);
    const visible = style.display !== "none"
      && style.visibility !== "hidden"
      && style.opacity !== "0"
      && rect.bottom > 0
      && rect.right > 0
      && rect.top < innerHeight
      && rect.left < innerWidth
      && area > 4;
    const source = element.querySelector && element.querySelector("source[src]");
    const url = element.currentSrc || element.src || (source && source.src) || "";
    const readable = tag === "video"
      ? element.readyState > 0 || element.videoWidth > 0 || Boolean(url)
      : tag === "audio"
        ? element.readyState > 0 || Boolean(url)
        : tag === "canvas"
          ? element.width > 0 && element.height > 0
          : element.complete && element.naturalWidth > 0 || Boolean(url);
    if (!visible || !readable) return null;
    const kind = tag === "img" || tag === "canvas" ? "image" : tag;
    const playing = tag === "video" && !element.paused && element.readyState >= 2;
    const storyCandidate = visible && (
      playing
      || area >= Math.max(96000, innerWidth * innerHeight * 0.10)
      || rect.width >= innerWidth * 0.32
      || rect.height >= innerHeight * 0.32
    );
    return {
      mediaUrl: url,
      mediaKind: kind,
      elementIndex: index,
      fileName: "browser-capture-" + (index + 1) + "." + (kind === "image" ? "jpg" : kind === "audio" ? "mp3" : "webm"),
      title: document.title || "Browser capture",
      pageUrl: location.href,
      source: "page-dom",
      visible: true,
      playing: playing,
      storyCandidate: storyCandidate,
      surfaceScore: area + (storyCandidate ? 1000000 : 0),
      score: (playing ? 100000000 : 0) + area
    };
  }).filter(Boolean).sort(function (left, right) {
    return right.score - left.score;
  }).map(function (item) {
    delete item.score;
    return item;
  });

  if (!state.installed) {
    state.installed = true;
    window.__janeConverterBrowserProbe__ = state;
    if (typeof window.fetch === "function") {
      const originalFetch = window.fetch;
      window.fetch = function () {
        const input = arguments[0];
        const requestUrl = typeof input === "string" ? input : input && input.url;
        if (requestUrl) {
          try { remember(new URL(requestUrl, location.href).href, ""); } catch (_) {}
        }
        return originalFetch.apply(this, arguments).then(function (response) {
          remember(response.url, response.headers && response.headers.get ? response.headers.get("content-type") : "");
          return response;
        });
      };
    }
    const originalOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function (method, url) {
      try { remember(new URL(String(url), location.href).href, ""); } catch (_) {}
      return originalOpen.apply(this, arguments);
    };
  }
  return { dom: dom, network: state.network.slice() };
}

function inspectPageMedia(sequence) {
  const collectElements = function () {
    const elements = [];
    const seen = new Set();
    const visit = function (root) {
      if (!root || typeof root.querySelectorAll !== "function") return;
      for (const element of root.querySelectorAll("*")) {
        const tag = element.tagName.toLowerCase();
        if ((tag === "video" || tag === "audio" || tag === "img" || tag === "canvas") && !seen.has(element)) {
          seen.add(element);
          elements.push(element);
        }
        if (element.shadowRoot) visit(element.shadowRoot);
      }
    };
    visit(document);
    return elements;
  };
  const readable = function (element) {
    const tag = element.tagName.toLowerCase();
    if (tag === "video") return element.readyState > 0 || element.videoWidth > 0 || Boolean(element.currentSrc || element.src);
    if (tag === "audio") return element.readyState > 0 || Boolean(element.currentSrc || element.src);
    if (tag === "canvas") return element.width > 0 && element.height > 0;
    return element.complete ? element.naturalWidth > 0 || Boolean(element.currentSrc || element.src) : Boolean(element.currentSrc || element.src);
  };
  const score = function (element) {
    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") return -1;
    const area = Math.max(0, rect.width) * Math.max(0, rect.height);
    const inViewport = rect.bottom > 0 && rect.right > 0 && rect.top < innerHeight && rect.left < innerWidth;
    const tag = element.tagName.toLowerCase();
    const playing = tag === "video" && !element.paused && element.readyState >= 2;
    const intrinsic = tag === "video"
      ? Math.max(0, element.videoWidth) * Math.max(0, element.videoHeight)
      : tag === "img"
        ? Math.max(0, element.naturalWidth) * Math.max(0, element.naturalHeight)
        : tag === "canvas"
          ? Math.max(0, element.width) * Math.max(0, element.height)
        : 0;
    if (!readable(element) || (area <= 4 && intrinsic <= 0)) return -1;
    return (playing ? 100000000 : 0) + (inViewport ? 10000000 : 0) + Math.min(area, 1000000) + Math.min(intrinsic, 1000000);
  };
  const mediaKind = function (element) {
    const tag = element.tagName.toLowerCase();
    return tag === "img" || tag === "canvas" ? "image" : tag;
  };
  const currentUrl = function (element) {
    const source = element.querySelector("source[src]");
    return element.currentSrc || element.src || (source && source.src) || "";
  };
  const filename = function (url, kind, index) {
    try {
      const path = new URL(url).pathname.split("/").pop() || "";
      const clean = decodeURIComponent(path).replace(/[^a-z0-9._-]+/gi, "-").replace(/^-+|-+$/g, "");
      if (clean && /\.[a-z0-9]{2,5}$/i.test(clean)) return clean.slice(-180);
    } catch (_) {}
    return "browser-capture-" + (index + 1) + "." + (kind === "image" ? "jpg" : kind === "audio" ? "mp3" : "webm");
  };
  const collect = function () {
    return collectElements().map(function (element, index) {
      const url = currentUrl(element);
      const rect = element.getBoundingClientRect();
      const area = Math.max(0, rect.width) * Math.max(0, rect.height);
      const visible = rect.bottom > 0 && rect.right > 0 && rect.top < innerHeight && rect.left < innerWidth && area > 4;
      const tag = element.tagName.toLowerCase();
      const playing = tag === "video" && !element.paused && element.readyState >= 2;
      const storyCandidate = visible && (
        playing
        || area >= Math.max(96000, innerWidth * innerHeight * 0.10)
        || rect.width >= innerWidth * 0.32
        || rect.height >= innerHeight * 0.32
      );
      const kind = mediaKind(element);
      const mediaScore = score(element);
      if (mediaScore < 0 || (url && !/^(https?:|blob:|data:)/i.test(url))) return null;
      return {
        mediaUrl: url,
        mediaKind: kind,
        elementIndex: index,
        fileName: filename(url, kind, index),
        title: document.title || "Browser capture",
        pageUrl: location.href,
        source: "page-dom",
        visible: visible,
        playing: playing,
        storyCandidate: storyCandidate,
        surfaceScore: area + (storyCandidate ? 1000000 : 0),
        score: mediaScore
      };
    }).filter(Boolean).sort(function (left, right) {
      return right.score - left.score;
    }).map(function (item) {
      delete item.score;
      return item;
    });
  };
  if (!sequence) return collect().slice(0, 1);

  return new Promise(function (resolve) {
    const found = new Map();
    let finished = false;
    let quietTimer;
    let interval;
    let timeout;
    const observer = new MutationObserver(remember);
    const finish = function () {
      if (finished) return;
      finished = true;
      clearInterval(interval);
      clearTimeout(timeout);
      clearTimeout(quietTimer);
      observer.disconnect();
      resolve(Array.from(found.values()));
    };
    const remember = function () {
      const previousSize = found.size;
      for (const item of collect()) {
        const key = item.mediaUrl || (item.mediaKind + ":" + item.elementIndex);
        if (!found.has(key) && found.size < MAX_SEQUENCE_ITEMS) found.set(key, item);
      }
      if (found.size !== previousSize) {
        clearTimeout(quietTimer);
        quietTimer = setTimeout(finish, STORY_QUIET_MS);
      }
      if (found.size >= MAX_SEQUENCE_ITEMS) finish();
    };
    observer.observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ["src", "poster"] });
    interval = setInterval(remember, 1000);
    timeout = setTimeout(finish, MAX_SEQUENCE_MS);
    remember();
  });
}

async function capturePageMedia(item, maxBytes) {
  const collectElements = function () {
    const elements = [];
    const seen = new Set();
    const visit = function (root) {
      if (!root || typeof root.querySelectorAll !== "function") return;
      for (const element of root.querySelectorAll("*")) {
        const tag = element.tagName.toLowerCase();
        if ((tag === "video" || tag === "audio" || tag === "img" || tag === "canvas") && !seen.has(element)) {
          seen.add(element);
          elements.push(element);
        }
        if (element.shadowRoot) visit(element.shadowRoot);
      }
    };
    visit(document);
    return elements;
  };
  const encodeCapture = async function (blob, contentType, fileName) {
    if (!blob || !blob.size || blob.size > maxBytes) return null;
    const bytes = new Uint8Array(await blob.arrayBuffer());
    let binary = "";
    for (let offset = 0; offset < bytes.length; offset += 0x8000) {
      binary += String.fromCharCode.apply(null, bytes.subarray(offset, Math.min(offset + 0x8000, bytes.length)));
    }
    return {
      base64: btoa(binary),
      contentType: contentType || blob.type || "application/octet-stream",
      fileName: fileName
    };
  };
  const currentUrl = function (element) {
    const source = element.querySelector("source[src]");
    return element.currentSrc || element.src || (source && source.src) || "";
  };
  const readBlobSource = async function (url) {
    try {
      const controller = new AbortController();
      const timer = setTimeout(function () { controller.abort(); }, 8000);
      let response;
      try {
        response = await fetch(url, { signal: controller.signal });
      } finally {
        clearTimeout(timer);
      }
      if (!response.ok) return null;
      const blob = await response.blob();
      return encodeCapture(blob, blob.type || "", item.fileName);
    } catch (_) {
      return null;
    }
  };
  if (/^(blob:|data:)/i.test(item.mediaUrl || "")) {
    const directBlob = await readBlobSource(item.mediaUrl);
    if (directBlob) return directBlob;
  }
  const candidates = collectElements();
  const element = candidates.find(function (candidate) {
    return currentUrl(candidate) === item.mediaUrl;
  }) || candidates[item.elementIndex] || candidates.find(function (candidate) {
    const tag = candidate.tagName.toLowerCase();
    return tag === "video" && (candidate.readyState > 0 || candidate.videoWidth > 0);
  });
  if (!element) throw new Error("The visible media element is no longer available. Keep it open and retry.");

  const sourceUrl = currentUrl(element);
  if (element.tagName.toLowerCase() === "canvas") {
    const blob = await new Promise(function (resolve) {
      element.toBlob(resolve, "image/png");
    });
    if (!blob || !blob.size || blob.size > maxBytes) {
      throw new Error("The visible canvas did not expose a usable image.");
    }
    return encodeCapture(blob, blob.type || "image/png", item.fileName.replace(/\.[^.]+$/, "") + ".png");
  }
  if (/^(blob:|data:)/i.test(sourceUrl)) {
    const sourceBlob = await readBlobSource(sourceUrl);
    if (sourceBlob) return sourceBlob;
  }

  if (element.tagName.toLowerCase() === "img") {
    const width = element.naturalWidth || element.width;
    const height = element.naturalHeight || element.height;
    if (!width || !height) {
      throw new Error("The visible image has not finished loading. Keep it open and retry.");
    }
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    try {
      context.drawImage(element, 0, 0, width, height);
    } catch (_) {
      throw new Error("The visible image is protected by the browser's cross-origin rules.");
    }
    const blob = await new Promise(function (resolve) {
      canvas.toBlob(resolve, "image/png");
    });
    if (!blob || !blob.size || blob.size > maxBytes) {
      throw new Error("The visible image did not expose a usable image.");
    }
    return encodeCapture(blob, blob.type || "image/png", item.fileName.replace(/\.[^.]+$/, "") + ".png");
  }

  if (element.tagName.toLowerCase() !== "video") {
    throw new Error("The page exposed media, but it did not provide readable media bytes.");
  }
  const captureStream = element.captureStream || element.mozCaptureStream;
  if (typeof captureStream !== "function" || typeof MediaRecorder === "undefined") {
    throw new Error("The page is playing protected media that the browser cannot expose to the bridge.");
  }
  const supportedTypes = [
    "video/webm;codecs=vp9,opus",
    "video/webm;codecs=vp8,opus",
    "video/webm"
  ];
  const mimeType = supportedTypes.find(function (value) {
    return typeof MediaRecorder.isTypeSupported !== "function" || MediaRecorder.isTypeSupported(value);
  });
  if (!mimeType) throw new Error("This browser cannot record the currently playing video format.");

  const originalTime = Number.isFinite(element.currentTime) ? element.currentTime : 0;
  const originalPaused = element.paused;
  const duration = Number.isFinite(element.duration) ? element.duration : 0;
  if (element.paused) {
    try { await element.play(); } catch (_) {}
    if (element.paused) {
      throw new Error("Start playback in the browser, then retry.");
    }
  }
  if (element.readyState < 2 && !element.videoWidth) {
    throw new Error("The browser has not loaded this media yet. Keep it playing, then retry.");
  }
  if (duration > 0 && duration < 30 * 60) {
    try {
      element.currentTime = 0;
      await Promise.race([
        new Promise(function (resolve) {
          element.addEventListener("seeked", resolve, { once: true });
        }),
        new Promise(function (resolve) { setTimeout(resolve, 2000); })
      ]);
    } catch (_) {}
  }

  const stream = captureStream.call(element);
  const chunks = [];
  const recorder = new MediaRecorder(stream, { mimeType: mimeType });
  const result = new Promise(function (resolve, reject) {
    let settled = false;
    const timeoutMs = duration > 0 ? Math.min(180 * 1000, Math.max(15 * 1000, (duration + 3) * 1000)) : 30 * 1000;
    let timer;
    let firstDataTimer;
    const finish = function (callback, value) {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      clearTimeout(firstDataTimer);
      recorder.removeEventListener("dataavailable", onData);
      recorder.removeEventListener("error", onError);
      recorder.removeEventListener("stop", onStop);
      element.removeEventListener("ended", stop);
      callback(value);
    };
    const onData = function (event) {
      if (event.data && event.data.size > 0) {
        clearTimeout(firstDataTimer);
        chunks.push(event.data);
      }
    };
    const onError = function () {
      finish(reject, new Error("The browser could not record the currently playing video."));
    };
    const onStop = async function () {
      const blob = new Blob(chunks, { type: mimeType });
      if (!blob.size) {
        finish(reject, new Error("The browser returned an empty rendered video."));
        return;
      }
      if (blob.size > maxBytes) {
        finish(reject, new Error("The rendered video is larger than JaneConverter's 64 MB browser-capture limit."));
        return;
      }
        finish(resolve, await encodeCapture(blob, blob.type || mimeType, item.fileName.replace(/\.[^.]+$/, "") + ".webm"));
    };
    const stop = function () {
      if (recorder.state !== "inactive") recorder.stop();
    };
    timer = setTimeout(stop, timeoutMs);
    recorder.addEventListener("dataavailable", onData);
    recorder.addEventListener("error", onError);
    recorder.addEventListener("stop", onStop);
    element.addEventListener("ended", stop, { once: true });
    recorder.start(250);
    firstDataTimer = setTimeout(function () {
      if (chunks.length === 0) {
        if (recorder.state !== "inactive") recorder.stop();
        finish(reject, new Error("The browser started playback but exposed no readable video frames. Keep it playing and retry."));
      }
    }, 8 * 1000);
  });
  const captured = await result;
  try {
    element.currentTime = originalTime;
    if (originalPaused) element.pause();
  } catch (_) {}
  return captured;
}

async function normalizePageCapture(pageCapture) {
  if (!pageCapture || typeof pageCapture !== "object") return null;
  let buffer = null;
  if (typeof pageCapture.base64 === "string") {
    try {
      const binary = atob(pageCapture.base64);
      buffer = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) buffer[index] = binary.charCodeAt(index);
    } catch (_) {
      buffer = null;
    }
  } else if (pageCapture.blob && typeof pageCapture.blob.arrayBuffer === "function") {
    buffer = new Uint8Array(await pageCapture.blob.arrayBuffer());
  } else {
    const raw = pageCapture.buffer;
    if (raw instanceof ArrayBuffer) {
      buffer = new Uint8Array(raw);
    } else if (ArrayBuffer.isView(raw)) {
      buffer = new Uint8Array(raw.buffer, raw.byteOffset, raw.byteLength);
    } else if (Array.isArray(raw)) {
      buffer = Uint8Array.from(raw);
    } else if (raw && typeof raw === "object") {
      const keys = Object.keys(raw)
        .filter(function (key) { return /^\d+$/.test(key); })
        .sort(function (left, right) { return Number(left) - Number(right); });
      if (keys.length) buffer = Uint8Array.from(keys.map(function (key) { return raw[key]; }));
    }
  }
  if (!buffer || !buffer.byteLength) return null;
  return Object.assign({}, pageCapture, { buffer: buffer });
}

async function runVisibleMediaCapture(sourceTab, item, world) {
  setStatus("Reading the visible media from the open page...", "warning");
  const target = { tabId: sourceTab.id };
  if (typeof item.frameId === "number") target.frameIds = [item.frameId];
  const captured = await chrome.scripting.executeScript({
    target: target,
    world: world,
    func: capturePageMedia,
    args: [item, MAX_RENDERED_CAPTURE_BYTES]
  });
  return normalizePageCapture(captured && captured[0] && captured[0].result);
}

async function captureVisibleMedia(sourceTab, item) {
  const errors = [];
  for (const world of ["MAIN", "ISOLATED"]) {
    try {
      const pageCapture = await runVisibleMediaCapture(sourceTab, item, world);
      if (pageCapture && pageCapture.buffer && pageCapture.buffer.byteLength) return pageCapture;
      errors.push(new Error("The " + world.toLowerCase() + " page context returned no media bytes."));
    } catch (error) {
      errors.push(error);
    }
  }
  const usefulError = errors.find(function (error) {
    return error && error.message && !/returned no media bytes/i.test(error.message);
  });
  throw new Error((usefulError || errors[0] || new Error("The browser did not expose readable bytes for this media. Keep it playing and retry.")).message);
}

async function sendCapture(sourceTab, accessTab, challenge, item, mode, index) {
  const isWebUrl = /^https?:\/\//i.test(item.mediaUrl || "");
  let mediaResponse = null;
  let pageFetched = null;
  let pageCapture = null;
  let contentLength = 0;
  let responseMime = "";
  let filename = item.fileName || ("browser-capture-" + (index + 1) + "." + (item.mediaKind === "image" ? "jpg" : item.mediaKind === "audio" ? "mp3" : "webm"));
  const sessionFetchAllowed = isWebUrl
    && globalThis.JaneMediaUtils
    && globalThis.JaneMediaUtils.isAllowedSessionMediaUrl(sourceTab.url, item.mediaUrl);
  if (sessionFetchAllowed) {
    try {
      setStatus("Using the signed-in browser session to fetch the selected media...", "warning");
      await captureThroughAuthenticatedSession(sourceTab, item, mode);
      return;
    } catch (error) {
      setStatus("Authenticated browser fetch was unavailable; trying the rendered media fallback...", "warning");
    }
  }
  const preferRenderedCapture = item.storyCandidate === true || item.source === "page-dom" || mode === "sequence";
  if (preferRenderedCapture) {
    try {
      pageCapture = await captureVisibleMedia(sourceTab, item);
      contentLength = pageCapture.buffer.byteLength;
      responseMime = String(pageCapture.contentType || "").split(";")[0].toLowerCase();
      filename = pageCapture.fileName || filename;
    } catch (_) {
      setStatus("Rendered capture unavailable; trying the source media...", "warning");
    }
  }
  if (!pageCapture && isWebUrl) {
    const mediaUrl = new URL(item.mediaUrl);
    await requestOriginPermission(item.mediaUrl);
    setStatus("Reading " + (mode === "sequence" ? "story item " + (index + 1) : "the selected media") + " from " + mediaUrl.host + "...", "warning");
    try {
      mediaResponse = await fetchWithTimeout(item.mediaUrl, { credentials: "include", cache: "no-store" });
      if (!mediaResponse.ok || !mediaResponse.body) throw new Error("HTTP " + mediaResponse.status);
      contentLength = Number(mediaResponse.headers.get("content-length") || 0);
      responseMime = String(mediaResponse.headers.get("content-type") || "").split(";")[0].toLowerCase();
    } catch (extensionError) {
      setStatus("Direct extension fetch failed; retrying from the signed-in source page...", "warning");
      try {
        const pageResult = await chrome.scripting.executeScript({
          target: { tabId: sourceTab.id },
          world: "MAIN",
              func: async function (url) {
            const controller = new AbortController();
            const timer = setTimeout(function () { controller.abort(); }, 8000);
            let response;
            try {
              response = await fetch(url, { credentials: "include", cache: "no-store", signal: controller.signal });
            } finally {
              clearTimeout(timer);
                }
                if (!response.ok) throw new Error("HTTP " + response.status);
                const blob = await response.blob();
                const bytes = new Uint8Array(await blob.arrayBuffer());
                let binary = "";
                for (let offset = 0; offset < bytes.length; offset += 0x8000) {
                  binary += String.fromCharCode.apply(null, bytes.subarray(offset, Math.min(offset + 0x8000, bytes.length)));
                }
                return {
                  base64: btoa(binary),
                  contentType: response.headers.get("content-type") || blob.type || ""
                };
          },
          args: [item.mediaUrl]
            });
            pageFetched = await normalizePageCapture(pageResult && pageResult[0] && pageResult[0].result);
            if (!pageFetched || !pageFetched.buffer || !pageFetched.buffer.byteLength) throw new Error("The source page returned no media bytes.");
        contentLength = pageFetched.buffer.byteLength;
        responseMime = String(pageFetched.contentType || "").split(";")[0].toLowerCase();
      } catch (pageError) {
        setStatus("The media URL returned no bytes; reading the visible player instead...", "warning");
        try {
          pageCapture = await captureVisibleMedia(sourceTab, item);
          contentLength = pageCapture.buffer.byteLength;
          responseMime = String(pageCapture.contentType || "").split(";")[0].toLowerCase();
          filename = pageCapture.fileName || filename;
        } catch (captureError) {
          throw new Error(describeFetchFailure("Media read", item.mediaUrl, captureError || pageError || extensionError));
        }
      }
    }
  } else if (!pageCapture) {
    pageCapture = await captureVisibleMedia(sourceTab, item);
    contentLength = pageCapture.buffer.byteLength;
    responseMime = String(pageCapture.contentType || "").split(";")[0].toLowerCase();
    filename = pageCapture.fileName || filename;
  }
  const mediaPrefix = item.mediaKind === "image" ? "image/" : item.mediaKind === "audio" ? "audio/" : "video/";
  const mimeType = responseMime.startsWith(mediaPrefix) ? responseMime : (mediaPrefix + "*");
  const startUrl = accessEndpoint(accessTab, "/bridge/capture/start");
  const start = await bridgeFetch(startUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-JaneConverter-Bridge": challenge.bridgeToken },
    body: JSON.stringify({
      fileName: filename,
      mediaKind: item.mediaKind,
      mimeType: mimeType,
      captureMode: mode,
      pageUrl: item.pageUrl || sourceTab.url || challenge.sourceUrl,
      expectedBytes: contentLength > 0 ? contentLength : undefined,
      title: item.title
    })
  }, "JaneConverter capture start");
  const started = await readJson(start);
  if (!start.ok) throw new Error(started.error || "JaneConverter rejected the capture metadata.");
  let offset = 0;
  const sendChunk = async function (chunkData) {
    const chunkUrl = accessEndpoint(accessTab, "/bridge/capture/chunk");
    const chunk = await bridgeFetch(chunkUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/octet-stream",
        "X-JaneConverter-Bridge": challenge.bridgeToken,
        "X-JaneConverter-Capture-Id": started.captureId,
        "X-JaneConverter-Capture-Offset": String(offset)
      },
      body: chunkData
    }, "JaneConverter capture upload");
    if (!chunk.ok) {
      const failure = await readJson(chunk);
      throw new Error(failure.error || "JaneConverter rejected a capture chunk.");
    }
    offset += chunkData.byteLength;
  };
  if (mediaResponse) {
    const reader = mediaResponse.body.getReader();
    while (true) {
      const read = await reader.read();
      if (read.done) break;
      let partOffset = 0;
      while (partOffset < read.value.byteLength) {
        const nextOffset = Math.min(partOffset + MAX_CHUNK_BYTES, read.value.byteLength);
        await sendChunk(read.value.slice(partOffset, nextOffset));
        partOffset = nextOffset;
      }
    }
  } else if (pageFetched) {
    const bytes = new Uint8Array(pageFetched.buffer);
    for (let offsetInBuffer = 0; offsetInBuffer < bytes.byteLength; offsetInBuffer += MAX_CHUNK_BYTES) {
      await sendChunk(bytes.slice(offsetInBuffer, Math.min(offsetInBuffer + MAX_CHUNK_BYTES, bytes.byteLength)));
    }
  } else {
    const bytes = new Uint8Array(pageCapture.buffer);
    for (let offsetInBuffer = 0; offsetInBuffer < bytes.byteLength; offsetInBuffer += MAX_CHUNK_BYTES) {
      await sendChunk(bytes.slice(offsetInBuffer, Math.min(offsetInBuffer + MAX_CHUNK_BYTES, bytes.byteLength)));
    }
  }
  const finishUrl = accessEndpoint(accessTab, "/bridge/capture/finish");
  const finished = await bridgeFetch(finishUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-JaneConverter-Bridge": challenge.bridgeToken },
    body: JSON.stringify({ captureId: started.captureId })
  }, "JaneConverter capture finalize");
  const result = await readJson(finished);
  if (!finished.ok) throw new Error(result.error || "JaneConverter could not finish the capture.");
}

function captureItemKey(item) {
  const raw = String(item && item.mediaUrl || "");
  if (raw && globalThis.JaneMediaUtils && typeof globalThis.JaneMediaUtils.normalizeMediaUrl === "function") {
    return globalThis.JaneMediaUtils.normalizeMediaUrl(raw).url;
  }
  return raw || [item && item.mediaKind, item && item.frameId, item && item.elementIndex].join(":");
}

async function inspectCurrentMedia(sourceTab) {
  const items = [];
  try {
    const probe = await chrome.scripting.executeScript({
      target: { tabId: sourceTab.id, allFrames: true },
      world: "MAIN",
      func: probePage
    });
    for (const frame of probe || []) {
      for (const item of (frame.result && frame.result.dom || []).concat(frame.result && frame.result.network || [])) {
        items.push(Object.assign({}, item, { frameId: frame.frameId }));
      }
    }
  } catch (_) {}
  try {
    const visible = await chrome.scripting.executeScript({
      target: { tabId: sourceTab.id, allFrames: true },
      func: inspectPageMedia,
      args: [false]
    });
    for (const frame of visible || []) {
      for (const item of frame.result || []) items.push(Object.assign({}, item, { frameId: frame.frameId }));
    }
  } catch (_) {}
  return items;
}

async function captureStorySequence(sourceTab, accessTab, challenge, initialItems) {
  const seen = new Set();
  const attempts = new Map();
  const failures = [];
  const deadline = Date.now() + MAX_SEQUENCE_MS;
  let lastNewItem = Date.now();
  let count = 0;
  let nextItems = initialItems;
  while (Date.now() < deadline && Date.now() - lastNewItem < STORY_QUIET_MS) {
    const candidates = globalThis.JaneMediaUtils
      ? globalThis.JaneMediaUtils.selectCaptureItems(nextItems, "sequence", MAX_SEQUENCE_ITEMS)
      : nextItems.slice(0, MAX_SEQUENCE_ITEMS);
    const candidate = candidates.find(function (item) {
      const key = captureItemKey(item);
      return !seen.has(key) && (attempts.get(key) || 0) < 2;
    });
    if (candidate) {
      const key = captureItemKey(candidate);
      attempts.set(key, (attempts.get(key) || 0) + 1);
      setStatus("Capturing story item " + (count + 1) + " while it is still open...", "warning");
      try {
        await sendCapture(sourceTab, accessTab, challenge, candidate, "sequence", count);
        seen.add(key);
        count += 1;
        lastNewItem = Date.now();
      } catch (error) {
        if ((attempts.get(key) || 0) >= 2) {
          seen.add(key);
          failures.push(error instanceof Error ? error.message : String(error));
        }
      }
    } else {
      await new Promise(function (resolve) { setTimeout(resolve, 750); });
    }
    nextItems = await inspectCurrentMedia(sourceTab);
  }
  return { count: count, failures: failures };
}

async function capture(mode) {
  currentButton.disabled = true;
  sequenceButton.disabled = true;
  try {
    const accessTabs = await findAccessTabs();
    if (!accessTabs.length) throw new Error("Open and confirm the JaneConverter access link first.");
    let accessTab;
    let challenge;
    let lastError;
    for (const candidate of accessTabs) {
      try {
        const challengeUrl = accessEndpoint(candidate, "/bridge/challenge");
        const response = await bridgeFetch(challengeUrl, { cache: "no-store" }, "JaneConverter bridge request");
        const value = await readJson(response);
        if (response.ok) {
          accessTab = candidate;
          challenge = value;
          break;
        }
        lastError = new Error(value.error || "JaneConverter has not confirmed access yet.");
      } catch (error) {
        lastError = error;
      }
    }
    if (!accessTab || !challenge) throw lastError || new Error("Confirm a fresh JaneConverter access link first.");
    if (!challenge.bridgeToken) throw new Error("JaneConverter did not provide a capture challenge. Reopen the access link and confirm it again.");

    const sourceTab = await findSourceTab(challenge.sourceUrl);
    if (challenge.sourceUrl) await requestOriginPermission(challenge.sourceUrl);
    setStatus(mode === "sequence" ? "Watching the open page for story items..." : "Inspecting the selected page and its media requests...", "warning");
    let inspected = [];
    try {
      inspected = await chrome.scripting.executeScript({
        target: { tabId: sourceTab.id, allFrames: true },
        world: "MAIN",
        func: probePage
      });
    } catch (_) {}
    const items = [];
    for (const frame of inspected || []) {
      const result = frame.result || {};
      for (const item of (result.dom || []).concat(result.network || [])) {
        items.push(Object.assign({}, item, { frameId: frame.frameId }));
      }
    }

    if (!items.length) {
      const fallback = await chrome.scripting.executeScript({
        target: { tabId: sourceTab.id, allFrames: true },
        func: inspectPageMedia,
        args: [false]
      });
      for (const frame of fallback || []) {
        for (const item of frame.result || []) {
          items.push(Object.assign({}, item, { frameId: frame.frameId }));
        }
      }
    }

    const selected = globalThis.JaneMediaUtils
      ? globalThis.JaneMediaUtils.selectCaptureItems(items, mode, MAX_SEQUENCE_ITEMS)
      : items.slice(0, mode === "sequence" ? MAX_SEQUENCE_ITEMS : 1);
    if (!selected.length) {
      throw new Error("The page exposed only an adaptive stream, not direct media bytes. Keep the story playing and retry.");
    }
    if (mode === "sequence") {
      const result = await captureStorySequence(sourceTab, accessTab, challenge, items);
      if (!result.count) {
        throw new Error(result.failures[0] || "The story viewer did not expose readable media. Keep the story open and playing, then retry.");
      }
      setStatus(result.count + " story capture" + (result.count === 1 ? "" : "s") + " sent to JaneConverter. You can keep this access session open and capture more.");
      return;
    }
    const captures = mode === "sequence" ? selected.slice(0, MAX_SEQUENCE_ITEMS) : selected.slice(0, 1);
    for (let index = 0; index < captures.length; index += 1) {
      await sendCapture(sourceTab, accessTab, challenge, captures[index], mode, index);
    }
    setStatus(captures.length + " capture" + (captures.length === 1 ? "" : "s") + " sent to JaneConverter. You can keep this access session open and capture more.");
  } catch (error) {
    setStatus(error instanceof Error ? error.message : String(error), "error");
  } finally {
    currentButton.disabled = false;
    sequenceButton.disabled = false;
  }
}

currentButton.addEventListener("click", function () { void capture("current"); });
async function resolveConfirmedSession() {
  const accessTabs = await findAccessTabs();
  if (!accessTabs.length) throw new Error("Open and confirm the JaneConverter access link first.");
  let lastError;
  for (const accessTab of accessTabs) {
    try {
      const response = await bridgeFetch(accessEndpoint(accessTab, "/bridge/challenge"), { cache: "no-store" }, "JaneConverter bridge request");
      const challenge = await readJson(response);
      if (!response.ok) {
        lastError = new Error(challenge.error || "JaneConverter has not confirmed access yet.");
        continue;
      }
      const sourceTab = await findSourceTab(challenge.sourceUrl || "");
      return { accessTab: accessTab, challenge: challenge, sourceTab: sourceTab };
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error("Confirm a fresh JaneConverter access link first.");
}

function setCollectButtonState(enabled) {
  if (!collectButton) return;
  collectButton.textContent = enabled ? "Disable collect mode" : "Enable collect mode";
  collectButton.classList.toggle("active", enabled);
}

function setNetworkButtonState(enabled) {
  if (!networkButton) return;
  networkButton.textContent = enabled ? "Disable Network Compatibility Mode" : "Enable Network Compatibility Mode";
  networkButton.classList.toggle("active", enabled);
}

async function updateCollectButton() {
  if (!collectButton || !chrome.storage || !chrome.storage.local) return;
  try {
    const session = await resolveConfirmedSession();
    const stored = await chrome.storage.local.get({ janeCollectTabs: {} });
    setCollectButtonState(Boolean(stored.janeCollectTabs && stored.janeCollectTabs[String(session.sourceTab.id)]));
  } catch (_) {
    setCollectButtonState(false);
  }
}

async function toggleCollectMode() {
  if (!collectButton) return;
  collectButton.disabled = true;
  currentButton.disabled = true;
  sequenceButton.disabled = true;
  try {
    const session = await resolveConfirmedSession();
    const sourceTab = session.sourceTab;
    if (!sourceTab || typeof sourceTab.id !== "number" || !sourceTab.url) {
      throw new Error("Keep the story page open in the browser, then retry.");
    }
    await requestOriginPermission(sourceTab.url);
    const stored = await chrome.storage.local.get({ janeCollectTabs: {} });
    const collectTabs = Object.assign({}, stored.janeCollectTabs || {});
    const key = String(sourceTab.id);
    const enabled = !collectTabs[key];
    await chrome.scripting.executeScript({ target: { tabId: sourceTab.id }, files: ["collect.js"] });
    await chrome.tabs.sendMessage(sourceTab.id, { type: "jane-collect-control", enabled: enabled });
    if (enabled) {
      collectTabs[key] = { enabled: true, sourceUrl: sourceTab.url, title: sourceTab.title || "" };
      await chrome.storage.local.set({ janeCollectTabs: collectTabs });
      setCollectButtonState(true);
      setStatus("Collect mode is on. Close this popup, then play or advance stories.", "warning");
    } else {
      delete collectTabs[key];
      await chrome.storage.local.set({ janeCollectTabs: collectTabs });
      setCollectButtonState(false);
      setStatus("Collect mode is off. The confirmed access session remains available.", "");
    }
  } catch (error) {
    setStatus(error instanceof Error ? error.message : String(error), "error");
  } finally {
    collectButton.disabled = false;
    currentButton.disabled = false;
    sequenceButton.disabled = false;
  }
}

async function updateNetworkButton() {
  if (!networkButton || !chrome.storage || !chrome.storage.local) return;
  try {
    const session = await resolveConfirmedSession();
    const stored = await chrome.storage.local.get({ janeNetworkTabs: {} });
    setNetworkButtonState(Boolean(stored.janeNetworkTabs && stored.janeNetworkTabs[String(session.sourceTab.id)]));
  } catch (_) {
    setNetworkButtonState(false);
  }
}

async function toggleNetworkMode() {
  if (!networkButton) return;
  networkButton.disabled = true;
  currentButton.disabled = true;
  sequenceButton.disabled = true;
  if (collectButton) collectButton.disabled = true;
  try {
    const session = await resolveConfirmedSession();
    const sourceTab = session.sourceTab;
    const stored = await chrome.storage.local.get({ janeNetworkTabs: {} });
    const enabled = !Boolean(stored.janeNetworkTabs && stored.janeNetworkTabs[String(sourceTab.id)]);
    const result = await chrome.runtime.sendMessage({
      type: "jane-network-mode",
      enabled: enabled,
      tabId: sourceTab.id,
      pageUrl: sourceTab.url
    });
    if (!result || !result.ok) throw new Error(result && result.error || "Network Compatibility Mode could not be changed.");
    setNetworkButtonState(enabled);
    setStatus(
      enabled
        ? "Network Compatibility Mode is on for this tab. Play or advance media; approved responses will appear in Fetched Media."
        : "Network Compatibility Mode is off. The confirmed access session remains available.",
      enabled ? "warning" : ""
    );
  } catch (error) {
    setStatus(error instanceof Error ? error.message : String(error), "error");
  } finally {
    networkButton.disabled = false;
    currentButton.disabled = false;
    sequenceButton.disabled = false;
    if (collectButton) collectButton.disabled = false;
  }
}

collectButton && collectButton.addEventListener("click", function () { void toggleCollectMode(); });
networkButton && networkButton.addEventListener("click", function () { void toggleNetworkMode(); });
sequenceButton.addEventListener("click", function () { void capture("sequence"); });
void updateCollectButton();
void updateNetworkButton();
