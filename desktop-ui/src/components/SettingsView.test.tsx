import { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsView } from "./SettingsView";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const updateCheck = vi.hoisted(() => ({ run: vi.fn() }));
const relaunch = vi.hoisted(() => ({ run: vi.fn() }));
const sourceRuntime = { mode: "tauri", pythonReady: true, ffmpegReady: true, pythonPath: ".venv/bin/python3", dataRoot: ".", projectRoot: ".", gpuAvailable: false, gpuLabel: "CPU mode", packaged: false, frontendPreference: "tauri" } as const;
vi.mock("../bridge", () => ({
  bridge: {
    setFrontendPreference: vi.fn(),
    checkUpdates: updateCheck.run,
    relaunch: relaunch.run,
  },
}));

describe("Settings updates", () => {
  beforeEach(() => {
    updateCheck.run.mockReset();
    updateCheck.run.mockResolvedValue("Update check complete. JaneConverter is up to date.");
    relaunch.run.mockResolvedValue(undefined);
  });

  it("shows the update result inside Settings", async () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    await act(async () => {
      root.render(<SettingsView runtime={sourceRuntime} onStatus={vi.fn()} />);
    });

    const check = Array.from(container.querySelectorAll("button")).find((button) => button.textContent?.includes("Check now"));
    expect(check).toBeDefined();
    await act(async () => {
      check?.click();
      await Promise.resolve();
    });

    expect(container.querySelector('[role="status"]')?.textContent).toContain("Update check complete");

    await act(async () => { root.unmount(); });
    container.remove();
  });

  it("offers a relaunch action for the selected interface", async () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    await act(async () => {
      root.render(<SettingsView runtime={sourceRuntime} onStatus={vi.fn()} />);
    });

    const relaunchButton = Array.from(container.querySelectorAll("button")).find((button) => button.textContent?.includes("Relaunch now"));
    expect(relaunchButton).toBeDefined();
    await act(async () => {
      relaunchButton?.click();
      await Promise.resolve();
    });

    expect(relaunch.run).toHaveBeenCalled();

    await act(async () => { root.unmount(); });
    container.remove();
  });

  it("hides unavailable legacy launchers in production packages", async () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    await act(async () => {
      root.render(<SettingsView runtime={{ mode: "tauri", pythonReady: true, ffmpegReady: true, pythonPath: "resources/runtime/engine/JaneConverterEngine", dataRoot: "/home/user/.local/share/JaneConverter", projectRoot: "resources/runtime", gpuAvailable: false, gpuLabel: "CPU mode", packaged: true, frontendPreference: "tauri" }} onStatus={vi.fn()} />);
    });

    expect(container.textContent).not.toContain("Legacy Rust");
    expect(container.textContent).not.toContain("Legacy Python");
    expect(container.textContent).not.toContain("Relaunch now");
    expect(container.textContent).toContain("OS user-data directory");

    await act(async () => { root.unmount(); });
    container.remove();
  });
});
