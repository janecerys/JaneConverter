(() => {
  if (window.__janeConverterCollectMode__) return;
  const state = {
    enabled: false,
    busy: false,
    timer: null,
    observer: null,
    lastKeys: new Set()
  };
  window.__janeConverterCollectMode__ = state;

  const MAX_BYTES = 64 * 1024 * 1024;
  const MAX_VIDEO_MS = 30 * 1000;

  function visible(element) {
    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    const area = Math.max(0, rect.width) * Math.max(0, rect.height);
    return style.display !== "none"
      && style.visibility !== "hidden"
      && style.opacity !== "0"
      && rect.bottom > 0
      && rect.right > 0
      && rect.top < innerHeight
      && rect.left < innerWidth
      && area > 4
      ? { rect: rect, area: area }
      : null;
  }

  function isPrimary(element, geometry) {
    const tag = element.tagName.toLowerCase();
    const playing = tag === "video" && !element.paused && element.readyState >= 2;
    return playing
      || geometry.area >= Math.max(96000, innerWidth * innerHeight * 0.10)
      || geometry.rect.width >= innerWidth * 0.32
      || geometry.rect.height >= innerHeight * 0.32;
  }

  function currentUrl(element) {
    const source = element.querySelector && element.querySelector("source[src]");
    return element.currentSrc || element.src || (source && source.src) || "";
  }

  function candidates() {
    const found = [];
    const seen = new Set();
    const visit = function (root) {
      if (!root || typeof root.querySelectorAll !== "function") return;
      for (const element of root.querySelectorAll("video, img, canvas")) {
        if (seen.has(element)) continue;
        seen.add(element);
        const geometry = visible(element);
        if (!geometry || !isPrimary(element, geometry)) continue;
        const tag = element.tagName.toLowerCase();
        const playing = tag === "video" && !element.paused && element.readyState >= 2;
        found.push({ element: element, geometry: geometry, playing: playing, tag: tag });
        if (element.shadowRoot) visit(element.shadowRoot);
      }
      for (const element of root.querySelectorAll("*")) {
        if (element.shadowRoot) visit(element.shadowRoot);
      }
    };
    visit(document);
    return found.sort(function (left, right) {
      return Number(right.playing) - Number(left.playing)
        || right.geometry.area - left.geometry.area;
    });
  }

  function keyFor(candidate) {
    const element = candidate.element;
    const url = currentUrl(element);
    let visual = "";
    if (candidate.tag === "canvas") {
      try { visual = element.toDataURL("image/jpeg", 0.08).slice(0, 160); } catch (_) {}
    }
    return [candidate.tag, url, element.videoWidth || element.naturalWidth || element.width, element.videoHeight || element.naturalHeight || element.height, visual].join("|");
  }

  async function encodeBlob(blob, fileName) {
    if (!blob || !blob.size || blob.size > MAX_BYTES) throw new Error("The rendered capture is empty or larger than 64 MB.");
    const bytes = new Uint8Array(await blob.arrayBuffer());
    let binary = "";
    for (let offset = 0; offset < bytes.length; offset += 0x8000) {
      binary += String.fromCharCode.apply(null, bytes.subarray(offset, Math.min(offset + 0x8000, bytes.length)));
    }
    return {
      base64: btoa(binary),
      contentType: blob.type || "application/octet-stream",
      fileName: fileName,
      mediaKind: blob.type.startsWith("image/") ? "image" : blob.type.startsWith("audio/") ? "audio" : "video",
      pageUrl: location.href,
      title: document.title || "Collected browser media"
    };
  }

  async function captureImage(candidate) {
    const element = candidate.element;
    const width = element.naturalWidth || element.videoWidth || element.width;
    const height = element.naturalHeight || element.videoHeight || element.height;
    if (!width || !height) throw new Error("The story image has not finished loading.");
    const canvas = element.tagName.toLowerCase() === "canvas" ? element : document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    if (canvas !== element) {
      const context = canvas.getContext("2d");
      if (!context) throw new Error("The browser could not create a rendered image surface.");
      try {
        context.drawImage(element, 0, 0, width, height);
      } catch (_) {
        const source = currentUrl(element);
        if (!source || !/^https?:/i.test(source)) throw new Error("The browser protected the rendered story image.");
        const response = await fetch(source, { credentials: "include", cache: "no-store" });
        if (!response.ok) throw new Error("The story image could not be read.");
        return encodeBlob(await response.blob(), "browser-collect-" + Date.now() + ".png");
      }
    }
    const blob = await new Promise(function (resolve) { canvas.toBlob(resolve, "image/png"); });
    return encodeBlob(blob, "browser-collect-" + Date.now() + ".png");
  }

  async function captureVideo(candidate) {
    const element = candidate.element;
    if (!candidate.playing) throw new Error("Start the story video before collect mode captures it.");
    const captureStream = element.captureStream || element.mozCaptureStream;
    if (typeof captureStream !== "function" || typeof MediaRecorder === "undefined") {
      throw new Error("This browser does not expose rendered story video frames.");
    }
    const mimeType = ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm"]
      .find(function (value) { return !MediaRecorder.isTypeSupported || MediaRecorder.isTypeSupported(value); });
    if (!mimeType) throw new Error("This browser cannot record the story video format.");
    const recorder = new MediaRecorder(captureStream.call(element), { mimeType: mimeType });
    const chunks = [];
    const result = await new Promise(function (resolve, reject) {
      let timer;
      const finish = function (callback, value) {
        clearTimeout(timer);
        recorder.removeEventListener("dataavailable", onData);
        recorder.removeEventListener("stop", onStop);
        recorder.removeEventListener("error", onError);
        element.removeEventListener("ended", stop);
        callback(value);
      };
      const onData = function (event) { if (event.data && event.data.size) chunks.push(event.data); };
      const onError = function () { finish(reject, new Error("The browser could not record the story video.")); };
      const onStop = async function () {
        const blob = new Blob(chunks, { type: mimeType });
        if (!blob.size) {
          finish(reject, new Error("The browser returned no rendered story frames."));
          return;
        }
        try {
          finish(resolve, await encodeBlob(blob, "browser-collect-" + Date.now() + ".webm"));
        } catch (error) {
          finish(reject, error);
        }
      };
      const stop = function () { if (recorder.state !== "inactive") recorder.stop(); };
      recorder.addEventListener("dataavailable", onData);
      recorder.addEventListener("stop", onStop);
      recorder.addEventListener("error", onError);
      element.addEventListener("ended", stop, { once: true });
      timer = setTimeout(stop, MAX_VIDEO_MS);
      recorder.start(250);
    });
    return result;
  }

  async function captureCandidate(candidate) {
    return candidate.tag === "video" ? captureVideo(candidate) : captureImage(candidate);
  }

  async function scan() {
    if (!state.enabled || state.busy) return;
    const candidate = candidates()[0];
    if (!candidate) return;
    const key = keyFor(candidate);
    if (state.lastKeys.has(key)) return;
    state.busy = true;
    try {
      const payload = await captureCandidate(candidate);
      state.lastKeys.add(key);
      if (state.lastKeys.size > 48) state.lastKeys.delete(state.lastKeys.values().next().value);
      chrome.runtime.sendMessage({ type: "jane-collect-media", payload: payload }, function () {
        if (chrome.runtime.lastError || !arguments[0] || !arguments[0].ok) {
          state.lastKeys.delete(key);
        }
      });
    } catch (_) {
      // Keep watching. A protected or paused item should not stop later story pages.
    } finally {
      state.busy = false;
    }
  }

  function stopWatching() {
    if (state.timer) clearInterval(state.timer);
    state.timer = null;
    if (state.observer) state.observer.disconnect();
    state.observer = null;
  }

  function startWatching() {
    stopWatching();
    state.timer = setInterval(function () { void scan(); }, 900);
    state.observer = new MutationObserver(function () { void scan(); });
    if (document.documentElement) state.observer.observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ["src", "poster", "class", "style"] });
    void scan();
  }

  chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (!message || message.type !== "jane-collect-control") return false;
    state.enabled = Boolean(message.enabled);
    if (state.enabled) {
      startWatching();
      chrome.runtime.sendMessage({ type: "jane-collect-status", enabled: true });
    } else {
      stopWatching();
      chrome.runtime.sendMessage({ type: "jane-collect-status", enabled: false });
    }
    sendResponse({ ok: true, enabled: state.enabled });
    return true;
  });
})();
