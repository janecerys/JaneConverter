const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const read = (name) => fs.readFileSync(path.join(root, name), "utf8");

test("collect mode is wired as a persistent extension feature", () => {
  const manifest = JSON.parse(read("manifest.json"));
  assert.equal(manifest.background.service_worker, "extension-worker.js");
  assert.ok(manifest.permissions.includes("storage"));
  assert.ok(manifest.permissions.includes("debugger"));
  assert.match(read("popup.html"), /id="collect"/);
  assert.match(read("popup.js"), /janeCollectTabs/);
  assert.match(read("popup.js"), /files: \["collect\.js"\]/);
  assert.match(read("service-worker.js"), /jane-collect-media/);
  assert.match(read("service-worker.js"), /captureMode: "collect"/);
  assert.match(read("collect.js"), /MediaRecorder/);
  assert.match(read("collect.js"), /canvas\.toBlob/);
  assert.match(read("collect.js"), /isPrimary/);
});
