const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const popupSource = fs.readFileSync(
  path.join(__dirname, "..", "popup.js"),
  "utf8"
);

test("keeps executeScript world outside the target object", () => {
  assert.equal(
    (popupSource.match(/target:\s*\{[^}]*world\s*:/g) || []).length,
    0
  );
  assert.match(
    popupSource,
    /target:\s*\{\s*tabId:\s*sourceTab\.id,\s*allFrames:\s*true\s*\},\s*world:\s*"MAIN"/s
  );
  assert.match(
    popupSource,
    /target:\s*\{\s*tabId:\s*sourceTab\.id\s*\},\s*world:\s*"MAIN"/s
  );
});

test("falls back to visible player capture when a media URL returns no bytes", () => {
  assert.match(popupSource, /async function captureVisibleMedia\(sourceTab, item\)/);
  assert.match(
    popupSource,
    /source page returned no media bytes[\s\S]*captureVisibleMedia\(sourceTab, item\)/s
  );
});

test("uses the authenticated service-worker path before rendered capture", () => {
  assert.match(popupSource, /async function captureThroughAuthenticatedSession\(/);
  assert.match(popupSource, /type:\s*"jane-authenticated-fetch"/);
  assert.match(popupSource, /Using the signed-in browser session[\s\S]*captureThroughAuthenticatedSession\(sourceTab, item, mode\)/);
  assert.match(popupSource, /Authenticated browser fetch was unavailable; trying the rendered media fallback/);
});

test("uses clone-safe media bytes and retries the isolated capture world", () => {
  assert.match(popupSource, /new Uint8Array\(await blob\.arrayBuffer\(\)\)/);
  assert.match(popupSource, /\["MAIN",\s*"ISOLATED"\]/);
});

test("bounds remote reads and refuses to wait on a paused player", () => {
  assert.match(popupSource, /const MEDIA_FETCH_TIMEOUT_MS = 8 \* 1000/);
  assert.match(popupSource, /AbortController/);
  assert.match(popupSource, /if \(element\.paused\)/);
});

test("normalizes cloned page blobs and preserves the useful capture error", () => {
  assert.match(popupSource, /pageCapture\.blob/);
  assert.match(popupSource, /ArrayBuffer\.isView/);
  assert.match(popupSource, /base64:\s*btoa\(binary\)/);
  assert.match(popupSource, /const binary = atob\(pageCapture\.base64\)/);
  assert.match(popupSource, /tag === "img" \|\| tag === "canvas" \? "image"/);
  assert.match(popupSource, /Start playback in the browser, then retry/);
  assert.match(popupSource, /errors\.find/);
});

test("keeps the confirmed bridge reusable for additional captures", () => {
  assert.doesNotMatch(
    popupSource,
    /if \(challenge\.connected\)[\s\S]*Clear access before starting another session/
  );
});

test("captures story items while they are still visible", () => {
  assert.match(popupSource, /async function captureStorySequence\(/);
  assert.match(popupSource, /Capturing story item/);
  assert.match(popupSource, /await inspectCurrentMedia\(sourceTab\)/);
});
