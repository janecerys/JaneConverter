importScripts("media-utils.js");

const MAX_CHUNK_BYTES = 1024 * 1024;
const MAX_SESSION_FETCH_BYTES = 1024 * 1024 * 1024;
const SESSION_FETCH_TIMEOUT_MS = 120 * 1000;

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
    throw new Error("JaneConverter returned an unexpected bridge response.");
  }
}

async function findConfirmedAccess() {
  const tabs = await chrome.tabs.query({});
  const candidates = tabs.filter(function (tab) {
    if (!tab.url) return false;
    try {
      const url = new URL(tab.url);
      return (url.hostname === "127.0.0.1" || url.hostname === "localhost")
        && /^\/access\/[^/]+(?:\/ready)?\/?$/.test(url.pathname);
    } catch (_) {
      return false;
    }
  });
  let lastError;
  for (const tab of candidates) {
    try {
      const response = await fetch(accessEndpoint(tab, "/bridge/challenge"), { cache: "no-store" });
      const value = await readJson(response);
      if (response.ok && value.bridgeToken) return { tab: tab, challenge: value };
      lastError = new Error(value.error || "JaneConverter has not confirmed browser access.");
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error("Open and confirm the JaneConverter access link first.");
}

function decodeBase64(value) {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

async function uploadCollectedMedia(payload) {
  if (!payload || typeof payload.base64 !== "string" || !payload.base64) {
    throw new Error("The browser did not provide media bytes.");
  }
  const bridge = await findConfirmedAccess();
  const bytes = decodeBase64(payload.base64);
  if (!bytes.byteLength || bytes.byteLength > 64 * 1024 * 1024) {
    throw new Error("The rendered capture is empty or larger than 64 MB.");
  }
  const mediaKind = payload.mediaKind === "audio" ? "audio" : payload.mediaKind === "image" ? "image" : "video";
  const fallbackMime = mediaKind + "/" + (mediaKind === "image" ? "png" : mediaKind === "audio" ? "webm" : "webm");
  const mimeType = String(payload.contentType || fallbackMime).split(";")[0].toLowerCase();
  const start = await fetch(accessEndpoint(bridge.tab, "/bridge/capture/start"), {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-JaneConverter-Bridge": bridge.challenge.bridgeToken },
    body: JSON.stringify({
      fileName: payload.fileName || ("browser-collect-" + Date.now() + "." + (mediaKind === "image" ? "png" : "webm")),
      mediaKind: mediaKind,
      mimeType: mimeType,
      captureMode: "collect",
      pageUrl: payload.pageUrl || bridge.challenge.sourceUrl || "",
      expectedBytes: bytes.byteLength,
      title: payload.title || "Collected browser media"
    })
  });
  const started = await readJson(start);
  if (!start.ok || !started.captureId) throw new Error(started.error || "JaneConverter rejected the collected media.");
  let offset = 0;
  try {
    while (offset < bytes.byteLength) {
      const next = Math.min(offset + MAX_CHUNK_BYTES, bytes.byteLength);
      const chunk = await fetch(accessEndpoint(bridge.tab, "/bridge/capture/chunk"), {
        method: "POST",
        headers: {
          "Content-Type": "application/octet-stream",
          "X-JaneConverter-Bridge": bridge.challenge.bridgeToken,
          "X-JaneConverter-Capture-Id": started.captureId,
          "X-JaneConverter-Capture-Offset": String(offset)
        },
        body: bytes.slice(offset, next)
      });
      const result = await readJson(chunk);
      if (!chunk.ok) throw new Error(result.error || "JaneConverter rejected a collected-media chunk.");
      offset = next;
    }
    const finish = await fetch(accessEndpoint(bridge.tab, "/bridge/capture/finish"), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-JaneConverter-Bridge": bridge.challenge.bridgeToken },
      body: JSON.stringify({ captureId: started.captureId })
    });
    const result = await readJson(finish);
    if (!finish.ok) throw new Error(result.error || "JaneConverter could not finish the collected media.");
    return result;
  } catch (error) {
    throw error;
  }
}

function requireSessionFetchPayload(payload) {
  if (!payload || typeof payload !== "object") throw new Error("The browser session request was missing.");
  const pageUrl = String(payload.pageUrl || "");
  const mediaUrl = String(payload.mediaUrl || "");
  const mediaKind = String(payload.mediaKind || "").toLowerCase();
  const captureMode = payload.captureMode === "sequence" ? "sequence" : "current";
  if (!globalThis.JaneMediaUtils || !globalThis.JaneMediaUtils.sessionPlatformForPage(pageUrl)) {
    throw new Error("Authenticated browser fetch is available only on an approved media site.");
  }
  if (!globalThis.JaneMediaUtils.isAllowedSessionMediaUrl(pageUrl, mediaUrl)) {
    throw new Error("The selected media host is not approved for this browser session.");
  }
  if (!["video", "audio", "image"].includes(mediaKind)) {
    throw new Error("The selected item is not supported media.");
  }
  return {
    pageUrl: pageUrl,
    mediaUrl: mediaUrl,
    mediaKind: mediaKind,
    captureMode: captureMode,
    title: String(payload.title || "Browser media").slice(0, 240),
    fileName: String(payload.fileName || globalThis.JaneMediaUtils.filenameFromUrl(mediaUrl, mediaKind, 0)).slice(0, 180)
  };
}

async function sendDiagnostic(bridge, event, fields) {
  try {
    await fetch(accessEndpoint(bridge.tab, "/bridge/diagnostic"), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-JaneConverter-Bridge": bridge.challenge.bridgeToken },
      body: JSON.stringify(Object.assign({ event: event }, fields || {}))
    });
  } catch (_) {
    // Diagnostics must never prevent a user-approved capture.
  }
}

async function startCaptureUpload(bridge, payload, mimeType, expectedBytes) {
  const response = await fetch(accessEndpoint(bridge.tab, "/bridge/capture/start"), {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-JaneConverter-Bridge": bridge.challenge.bridgeToken },
    body: JSON.stringify({
      fileName: payload.fileName,
      mediaKind: payload.mediaKind,
      mimeType: mimeType,
      captureMode: payload.captureMode,
      pageUrl: payload.pageUrl,
      expectedBytes: expectedBytes || undefined,
      title: payload.title
    })
  });
  const result = await readJson(response);
  if (!response.ok || !result.captureId) throw new Error(result.error || "JaneConverter rejected the media capture.");
  return result.captureId;
}

async function uploadSessionResponse(bridge, payload, response, mimeType, expectedBytes) {
  const captureId = await startCaptureUpload(bridge, payload, mimeType, expectedBytes);
  const reader = response.body && response.body.getReader();
  if (!reader) throw new Error("The signed-in browser response contained no media bytes.");
  let offset = 0;
  let nextDiagnosticAt = 8 * 1024 * 1024;
  while (true) {
    const read = await reader.read();
    if (read.done) break;
    for (let index = 0; index < read.value.byteLength; index += MAX_CHUNK_BYTES) {
      const chunkData = read.value.slice(index, Math.min(index + MAX_CHUNK_BYTES, read.value.byteLength));
      if (!chunkData.byteLength || offset + chunkData.byteLength > MAX_SESSION_FETCH_BYTES) {
        throw new Error("The authenticated media response exceeded JaneConverter's 1 GB capture limit.");
      }
      const chunk = await fetch(accessEndpoint(bridge.tab, "/bridge/capture/chunk"), {
        method: "POST",
        headers: {
          "Content-Type": "application/octet-stream",
          "X-JaneConverter-Bridge": bridge.challenge.bridgeToken,
          "X-JaneConverter-Capture-Id": captureId,
          "X-JaneConverter-Capture-Offset": String(offset)
        },
        body: chunkData
      });
      const chunkResult = await readJson(chunk);
      if (!chunk.ok) throw new Error(chunkResult.error || "JaneConverter rejected part of the media capture.");
      offset += chunkData.byteLength;
      if (offset >= nextDiagnosticAt) {
        await sendDiagnostic(bridge, "upload_progress", { bytes: offset });
        nextDiagnosticAt += 8 * 1024 * 1024;
      }
    }
  }
  if (!offset) throw new Error("The signed-in browser response contained no media bytes.");
  const finish = await fetch(accessEndpoint(bridge.tab, "/bridge/capture/finish"), {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-JaneConverter-Bridge": bridge.challenge.bridgeToken },
    body: JSON.stringify({ captureId: captureId })
  });
  const result = await readJson(finish);
  if (!finish.ok) throw new Error(result.error || "JaneConverter could not finish the media capture.");
  await sendDiagnostic(bridge, "upload_complete", { bytes: offset });
  return result;
}

async function fetchAuthenticatedMedia(payload) {
  const request = requireSessionFetchPayload(payload);
  const bridge = await findConfirmedAccess();
  const pagePlatform = globalThis.JaneMediaUtils.sessionPlatformForPage(request.pageUrl);
  const host = new URL(request.mediaUrl).hostname.toLowerCase();
  await sendDiagnostic(bridge, "session_fetch_started", { platform: pagePlatform.id, host: host, mediaKind: request.mediaKind });
  const controller = new AbortController();
  const timeout = setTimeout(function () { controller.abort(); }, SESSION_FETCH_TIMEOUT_MS);
  try {
    const response = await fetch(request.mediaUrl, {
      credentials: "include",
      cache: "no-store",
      redirect: "error",
      signal: controller.signal
    });
    const contentType = String(response.headers.get("content-type") || "").split(";", 1)[0].toLowerCase();
    const contentLength = Number(response.headers.get("content-length") || 0);
    if (!response.ok) {
      await sendDiagnostic(bridge, "media_response", { host: host, status: response.status });
      throw new Error("The signed-in browser request returned HTTP " + response.status + ".");
    }
    if (!globalThis.JaneMediaUtils.isExpectedMediaResponse(request.mediaKind, contentType)) {
      await sendDiagnostic(bridge, "candidate_rejected", { host: host, mediaKind: request.mediaKind });
      throw new Error("The signed-in browser response was not the requested " + request.mediaKind + " media.");
    }
    if (contentLength > MAX_SESSION_FETCH_BYTES) {
      throw new Error("The signed-in browser response is larger than JaneConverter's 1 GB capture limit.");
    }
    await sendDiagnostic(bridge, "media_response", { host: host, status: response.status, mediaKind: request.mediaKind, bytes: contentLength || undefined });
    const result = await uploadSessionResponse(bridge, request, response, contentType, contentLength || undefined);
    return { ok: true, captureCount: Number(result.captureCount || 0) };
  } catch (error) {
    await sendDiagnostic(bridge, "session_fetch_failed", { host: host, mediaKind: request.mediaKind });
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

async function setBadge(tabId, text, color) {
  try {
    await chrome.action.setBadgeText({ tabId: tabId, text: text });
    await chrome.action.setBadgeBackgroundColor({ tabId: tabId, color: color });
  } catch (_) {}
}

chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
  if (sender.id !== chrome.runtime.id) return false;
  if (!message || message.type !== "jane-collect-media") return false;
  uploadCollectedMedia(message.payload)
    .then(async function (result) {
      const count = Number(result && result.captureCount || 0);
      await setBadge(sender.tab && sender.tab.id, count ? String(Math.min(count, 99)) : "OK", "#0f766e");
      sendResponse({ ok: true, captureCount: count });
    })
    .catch(async function (error) {
      await setBadge(sender.tab && sender.tab.id, "!", "#be123c");
      sendResponse({ ok: false, error: error instanceof Error ? error.message : String(error) });
    });
  return true;
});

chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
  if (sender.id !== chrome.runtime.id || !message || message.type !== "jane-authenticated-fetch") return false;
  fetchAuthenticatedMedia(message.payload)
    .then(function (result) { sendResponse(result); })
    .catch(function (error) { sendResponse({ ok: false, error: error instanceof Error ? error.message : String(error) }); });
  return true;
});

chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
  if (!message || message.type !== "jane-collect-status") return false;
  setBadge(sender.tab && sender.tab.id, message.enabled ? "ON" : "", message.enabled ? "#0f766e" : "#52525b")
    .then(function () { sendResponse({ ok: true }); });
  return true;
});

chrome.tabs.onUpdated.addListener(function (tabId, changeInfo) {
  if (changeInfo.status !== "complete") return;
  chrome.storage.local.get({ janeCollectTabs: {} }).then(async function (stored) {
    const state = stored.janeCollectTabs && stored.janeCollectTabs[String(tabId)];
    if (!state || !state.enabled) return;
    try {
      await chrome.scripting.executeScript({ target: { tabId: tabId }, files: ["collect.js"] });
      await chrome.tabs.sendMessage(tabId, { type: "jane-collect-control", enabled: true });
      await setBadge(tabId, "ON", "#0f766e");
    } catch (_) {}
  });
});

chrome.tabs.onRemoved.addListener(function (tabId) {
  chrome.storage.local.get({ janeCollectTabs: {} }).then(function (stored) {
    const next = Object.assign({}, stored.janeCollectTabs || {});
    delete next[String(tabId)];
    return chrome.storage.local.set({ janeCollectTabs: next });
  }).catch(function () {});
});
