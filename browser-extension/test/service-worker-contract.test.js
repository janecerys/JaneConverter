const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const worker = fs.readFileSync(path.join(__dirname, "..", "service-worker.js"), "utf8");

test("keeps authenticated media fetches in the service worker with an allowlisted target", () => {
  assert.match(worker, /importScripts\("media-utils\.js"\)/);
  assert.match(worker, /isAllowedSessionMediaUrl\(pageUrl, mediaUrl\)/);
  assert.match(worker, /credentials:\s*"include"/);
  assert.match(worker, /redirect:\s*"error"/);
  assert.match(worker, /isExpectedMediaResponse\(request\.mediaKind, contentType\)/);
});

test("records structured diagnostics without accepting arbitrary page messages", () => {
  assert.match(worker, /sendDiagnostic\(bridge, "session_fetch_started"/);
  assert.match(worker, /sendDiagnostic\(bridge, "media_response"/);
  assert.match(worker, /sendDiagnostic\(bridge, "session_fetch_failed"/);
  assert.doesNotMatch(worker, /document\.cookie|chrome\.cookies/);
});
