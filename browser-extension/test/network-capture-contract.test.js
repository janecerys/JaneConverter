const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const manifest = JSON.parse(fs.readFileSync(path.join(root, "manifest.json"), "utf8"));
const worker = fs.readFileSync(path.join(root, "network-capture.js"), "utf8");
const host = fs.readFileSync(path.join(root, "extension-worker.js"), "utf8");

test("declares the elevated debugger permission explicitly and keeps it opt-in", () => {
  assert.equal(manifest.permissions.includes("debugger"), true);
  const popup = fs.readFileSync(path.join(root, "popup.html"), "utf8");
  assert.match(popup, /Network Compatibility Mode/);
  assert.match(popup, /Capture story sequence \(Experimental\)/);
  assert.match(worker, /message\.type !== "jane-network-mode"/);
  assert.match(worker, /chrome\.debugger\.attach/);
  assert.match(worker, /Network\.enable/);
});

test("captures response bodies only through the tab-scoped Network domain", () => {
  assert.match(worker, /Network\.responseReceived/);
  assert.match(worker, /Network\.loadingFinished/);
  assert.match(worker, /Network\.getResponseBody/);
  assert.match(worker, /item\.target \|\| \{ tabId: state\.tabId \}/);
  assert.match(worker, /requestId: item\.requestId/);
  assert.doesNotMatch(worker, /getAllCookies|getCookies|document\.cookie|chrome\.cookies/);
  assert.doesNotMatch(worker, /Cookie["']\s*:/i);
  assert.match(host, /service-worker\.js/);
  assert.match(host, /network-capture\.js/);
});

test("keeps network uploads marked as network captures", () => {
  assert.match(worker, /captureMode:\s*"network"/);
  assert.match(worker, /networkCaptureDisposition/);
  assert.match(worker, /network_discarded/);
  assert.match(worker, /network_capture_failed/);
});
