/* Tab-scoped authenticated media capture.
 *
 * This file deliberately has no cookie API, cookie parsing, request-header
 * access, or token logging. chrome.debugger is used only after the user
 * enables Network Compatibility Mode for the selected tab.
 */
(function () {
  const MAX_NETWORK_CAPTURE_BYTES = 256 * 1024 * 1024;
  const MAX_NETWORK_PENDING = 96;
  const NETWORK_STORAGE_KEY = "janeNetworkTabs";
  const DEBUGGER_PROTOCOL = "0.1";
  const states = new Map();

  function safeHost(url) {
    try {
      return new URL(url).hostname.toLowerCase();
    } catch (_) {
      return "";
    }
  }

  function sameSite(left, right) {
    const a = String(left || "").toLowerCase().replace(/\.$/, "");
    const b = String(right || "").toLowerCase().replace(/\.$/, "");
    return Boolean(a && b) && (a === b || a.endsWith("." + b) || b.endsWith("." + a));
  }

  function pagePlatform(pageUrl) {
    return globalThis.JaneMediaUtils && globalThis.JaneMediaUtils.sessionPlatformForPage(pageUrl);
  }

  function candidateForResponse(pageUrl, response) {
    const mediaUrl = String(response && response.url || "");
    const contentType = String(response && response.mimeType || "").split(";", 1)[0].trim().toLowerCase();
    const resourceType = String(response && response.resourceType || "").toLowerCase();
    if (!globalThis.JaneMediaUtils || !globalThis.JaneMediaUtils.isAllowedSessionMediaUrl(pageUrl, mediaUrl)) {
      return { accepted: false, reason: "media host not approved" };
    }
    if (response.status < 200 || response.status >= 400) {
      return { accepted: false, reason: "response was not successful" };
    }
    let mediaKind = globalThis.JaneMediaUtils.classify(mediaUrl, contentType);
    if (mediaKind === "stream") {
      return { accepted: false, reason: "adaptive stream manifest" };
    }
    if (!mediaKind && resourceType === "media" && globalThis.JaneMediaUtils.isStreamSegment(mediaUrl, contentType)) {
      mediaKind = "video";
    }
    if (!mediaKind || !["video", "audio", "image"].includes(mediaKind)) {
      return { accepted: false, reason: "not a media response" };
    }
    const encodedBytes = Number(response.encodedDataLength || 0);
    if (encodedBytes > MAX_NETWORK_CAPTURE_BYTES) {
      return { accepted: false, reason: "response exceeded the 256 MB limit" };
    }
    return {
      accepted: true,
      mediaUrl: mediaUrl,
      host: safeHost(mediaUrl),
      mediaKind: mediaKind,
      mimeType: contentType || (mediaKind + "/*"),
      status: Number(response.status || 0),
      bytes: encodedBytes || undefined
    };
  }

  function decodeBody(body, base64Encoded) {
    if (base64Encoded) {
      const binary = atob(String(body || ""));
      const bytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
      return bytes;
    }
    return new TextEncoder().encode(String(body || ""));
  }

  function fileNameFor(item) {
    const name = globalThis.JaneMediaUtils.filenameFromUrl(item.mediaUrl, item.mediaKind, 0);
    if (/\.[a-z0-9]{2,5}$/i.test(name)) return name.slice(-180);
    const extension = item.mediaKind === "image" ? "jpg" : item.mediaKind === "audio" ? "mp3" : "mp4";
    return name.slice(-170) + "." + extension;
  }

  async function storedEntry(tabId) {
    const stored = await chrome.storage.local.get({ [NETWORK_STORAGE_KEY]: {} });
    const entry = stored[NETWORK_STORAGE_KEY] && stored[NETWORK_STORAGE_KEY][String(tabId)];
    if (!entry || !entry.enabled) return null;
    return entry;
  }

  async function writeEntry(tabId, entry) {
    const stored = await chrome.storage.local.get({ [NETWORK_STORAGE_KEY]: {} });
    const next = Object.assign({}, stored[NETWORK_STORAGE_KEY] || {});
    if (entry) next[String(tabId)] = entry;
    else delete next[String(tabId)];
    await chrome.storage.local.set({ [NETWORK_STORAGE_KEY]: next });
  }

  async function getState(tabId) {
    if (states.has(tabId)) return states.get(tabId);
    const entry = await storedEntry(tabId);
    if (!entry) return null;
    const state = {
      tabId: tabId,
      pageUrl: String(entry.pageUrl || ""),
      platform: String(entry.platform || ""),
      pending: new Map(),
      attached: false
    };
    states.set(tabId, state);
    return state;
  }

  async function diagnose(state, event, fields) {
    try {
      const bridge = await findConfirmedAccess();
      await sendDiagnostic(bridge, event, Object.assign({
        platform: state.platform,
        host: safeHost(state.pageUrl)
      }, fields || {}));
    } catch (_) {
      // Console diagnostics must never make media capture less reliable.
    }
  }

  async function uploadNetworkBytes(bridge, state, item, bytes) {
    const payload = {
      fileName: fileNameFor(item),
      mediaKind: item.mediaKind,
      captureMode: "network",
      pageUrl: state.pageUrl,
      title: "Authenticated network media"
    };
    const captureId = await startCaptureUpload(bridge, payload, item.mimeType, bytes.byteLength);
    let offset = 0;
    while (offset < bytes.byteLength) {
      const next = Math.min(offset + MAX_CHUNK_BYTES, bytes.byteLength);
      const chunk = await fetch(accessEndpoint(bridge.tab, "/bridge/capture/chunk"), {
        method: "POST",
        headers: {
          "Content-Type": "application/octet-stream",
          "X-JaneConverter-Bridge": bridge.challenge.bridgeToken,
          "X-JaneConverter-Capture-Id": captureId,
          "X-JaneConverter-Capture-Offset": String(offset)
        },
        body: bytes.slice(offset, next)
      });
      const result = await readJson(chunk);
      if (!chunk.ok) throw new Error(result.error || "JaneConverter rejected a network-media chunk.");
      offset = next;
    }
    const finish = await fetch(accessEndpoint(bridge.tab, "/bridge/capture/finish"), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-JaneConverter-Bridge": bridge.challenge.bridgeToken },
      body: JSON.stringify({ captureId: captureId })
    });
    const result = await readJson(finish);
    if (!finish.ok) throw new Error(result.error || "JaneConverter could not finish the network media.");
    return result;
  }

  function sourceKey(source, requestId) {
    return String(source && source.sessionId || "root") + ":" + String(requestId);
  }

  function targetForSource(source) {
    const target = { tabId: source.tabId };
    if (source.sessionId) target.sessionId = source.sessionId;
    return target;
  }

  async function captureFinished(state, requestKey) {
    const item = state.pending.get(requestKey);
    state.pending.delete(requestKey);
    if (!item || !state.attached) return;
    try {
      const body = await chrome.debugger.sendCommand(
        item.target || { tabId: state.tabId },
        "Network.getResponseBody",
        { requestId: item.requestId }
      );
      const bytes = decodeBody(body && body.body, Boolean(body && body.base64Encoded));
      if (!bytes.byteLength || bytes.byteLength > MAX_NETWORK_CAPTURE_BYTES) {
        await diagnose(state, "network_discarded", { mediaKind: item.mediaKind, status: item.status, bytes: bytes.byteLength, reason: "response exceeded the 256 MB limit" });
        return;
      }
      const disposition = globalThis.JaneMediaUtils.networkCaptureDisposition
        ? globalThis.JaneMediaUtils.networkCaptureDisposition(item.mediaKind, bytes.byteLength)
        : { accepted: true };
      if (!disposition.accepted) {
        await diagnose(state, "network_discarded", { mediaKind: item.mediaKind, status: item.status, bytes: bytes.byteLength, reason: disposition.reason });
        return;
      }
      await diagnose(state, "network_body_ready", { mediaKind: item.mediaKind, status: item.status, bytes: bytes.byteLength });
      const bridge = await findConfirmedAccess();
      const result = await uploadNetworkBytes(bridge, state, item, bytes);
      await sendDiagnostic(bridge, "upload_complete", { mediaKind: item.mediaKind, bytes: bytes.byteLength });
      await setBadge(state.tabId, String(Math.min(Number(result && result.captureCount || 1), 99)), "#0f766e");
    } catch (error) {
      await diagnose(state, "network_capture_failed", { mediaKind: item.mediaKind, status: item.status, reason: "response body was unavailable" });
      await setBadge(state.tabId, "!", "#be123c");
    }
  }

  async function handleEvent(source, method, params) {
    if (!source || typeof source.tabId !== "number") return;
    const state = await getState(source.tabId);
    if (!state || !state.attached) return;
    if (method === "Target.attachedToTarget") {
      const sessionId = params && params.sessionId;
      if (!sessionId) return;
      try {
        await chrome.debugger.sendCommand(
          { tabId: source.tabId, sessionId: sessionId },
          "Network.enable",
          { maxTotalBufferSize: MAX_NETWORK_CAPTURE_BYTES, maxResourceBufferSize: MAX_NETWORK_CAPTURE_BYTES }
        );
      } catch (_) {}
      return;
    }
    if (method === "Network.responseReceived") {
      const item = candidateForResponse(state.pageUrl, Object.assign({}, params && params.response || {}, { resourceType: params && params.type }));
      if (!item.accepted) return;
      if (state.pending.size >= MAX_NETWORK_PENDING) return;
      item.requestId = String(params.requestId);
      item.target = targetForSource(source);
      state.pending.set(sourceKey(source, params.requestId), item);
      void diagnose(state, "network_probe", {
        mediaKind: item.mediaKind,
        status: item.status,
        bytes: item.bytes
      });
      return;
    }
    if (method === "Network.loadingFinished") {
      void captureFinished(state, sourceKey(source, params.requestId));
    } else if (method === "Network.loadingFailed") {
      state.pending.delete(sourceKey(source, params.requestId));
    }
  }

  async function attachNetworkMode(tabId, pageUrl) {
    const platform = pagePlatform(pageUrl);
    if (!platform) throw new Error("Network Compatibility Mode is available only on an approved media site.");
    const bridge = await findConfirmedAccess();
    if (bridge.challenge.sourceUrl && !sameSite(safeHost(bridge.challenge.sourceUrl), safeHost(pageUrl))) {
      throw new Error("The confirmed JaneConverter session belongs to a different site.");
    }
    const existing = await getState(tabId);
    if (existing && existing.attached) return existing;
    try {
      await chrome.debugger.attach({ tabId: tabId }, DEBUGGER_PROTOCOL);
      await chrome.debugger.sendCommand({ tabId: tabId }, "Network.enable", {
        maxTotalBufferSize: MAX_NETWORK_CAPTURE_BYTES,
        maxResourceBufferSize: MAX_NETWORK_CAPTURE_BYTES
      });
    } catch (_) {
      try { await chrome.debugger.detach({ tabId: tabId }); } catch (_) {}
      throw new Error("Chrome could not attach Network Compatibility Mode to this tab.");
    }
    const state = existing || { tabId: tabId, pending: new Map() };
    state.pageUrl = pageUrl;
    state.platform = platform.id;
    state.attached = true;
    states.set(tabId, state);
    await writeEntry(tabId, { enabled: true, pageUrl: pageUrl, platform: platform.id });
    await diagnose(state, "network_mode_enabled", {});
    await setBadge(tabId, "NET", "#f59e0b");
    return state;
  }

  async function detachNetworkMode(tabId, persist) {
    const state = states.get(tabId);
    if (state) {
      state.attached = false;
      state.pending.clear();
    }
    try { await chrome.debugger.detach({ tabId: tabId }); } catch (_) {}
    states.delete(tabId);
    if (persist !== false) await writeEntry(tabId, null);
    await setBadge(tabId, "", "#52525b");
  }

  chrome.debugger.onEvent.addListener(function (source, method, params) {
    void handleEvent(source, method, params);
  });

  chrome.debugger.onDetach.addListener(function (source) {
    if (!source || typeof source.tabId !== "number") return;
    void detachNetworkMode(source.tabId, true);
  });

  chrome.tabs.onUpdated.addListener(function (tabId, changeInfo, tab) {
    if (changeInfo.status !== "complete") return;
    void (async function () {
      const entry = await storedEntry(tabId);
      if (!entry || !entry.enabled || !tab.url) return;
      const nextPlatform = pagePlatform(tab.url);
      if (!nextPlatform || nextPlatform.id !== entry.platform) {
        await detachNetworkMode(tabId, true);
        return;
      }
      await detachNetworkMode(tabId, false);
      try { await attachNetworkMode(tabId, tab.url); } catch (_) { await writeEntry(tabId, entry); }
    }());
  });

  chrome.tabs.onRemoved.addListener(function (tabId) {
    void detachNetworkMode(tabId, true);
  });

  chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (sender.id !== chrome.runtime.id || !message || message.type !== "jane-network-mode") return false;
    const tabId = typeof message.tabId === "number" ? message.tabId : sender.tab && sender.tab.id;
    const requestedUrl = String(message.pageUrl || sender.tab && sender.tab.url || "");
    if (typeof tabId !== "number" || !requestedUrl) {
      sendResponse({ ok: false, error: "Keep the approved media page open in the active tab." });
      return false;
    }
    chrome.tabs.get(tabId).then(function (tab) {
      if (!tab || tab.id !== tabId || tab.url !== requestedUrl) {
        throw new Error("The selected media tab changed. Reopen the extension and try again.");
      }
      if (message.enabled) return attachNetworkMode(tabId, tab.url).then(function () { return { ok: true, enabled: true }; });
      return detachNetworkMode(tabId, true).then(function () { return { ok: true, enabled: false }; });
    }).then(sendResponse).catch(function (error) {
      sendResponse({ ok: false, error: error instanceof Error ? error.message : String(error) });
    });
    return true;
  });

  chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (sender.id !== chrome.runtime.id || !message || message.type !== "jane-network-status") return false;
    const tabId = sender.tab && sender.tab.id;
    if (typeof tabId !== "number") {
      sendResponse({ ok: true, enabled: false });
      return false;
    }
    getState(tabId).then(function (state) {
      sendResponse({ ok: true, enabled: Boolean(state && state.attached) });
    }).catch(function () { sendResponse({ ok: true, enabled: false }); });
    return true;
  });
}());
