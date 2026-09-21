import { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsView } from "./SettingsView";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const updateCheck = vi.hoisted(() => ({ run: vi.fn() }));
const installUpdate = vi.hoisted(() => ({ run: vi.fn() }));
const relaunch = vi.hoisted(() => ({ run: vi.fn() }));
const chooseFolder = vi.hoisted(() => ({ run: vi.fn() }));
const setDataRoot = vi.hoisted(() => ({ run: vi.fn() }));
const sourceRuntime = { mode: "tauri", pythonReady: true, ffmpegReady: true, ffmpegPath: "/usr/bin/ffmpeg", pythonPath: ".venv/bin/python3", dataRoot: ".", projectRoot: ".", gpuAvailable: false, gpuLabel: "CPU mode", packaged: false } as const;
vi.mock("../bridge", () => ({
  bridge: {
    checkUpdates: updateCheck.run,
    installUpdate: installUpdate.run,
    relaunch: relaunch.run,
    chooseFolder: chooseFolder.run,
    setDataRoot: setDataRoot.run,
  },
}));

describe("Settings updates", () => {
  beforeEach(() => {
    updateCheck.run.mockReset();
    installUpdate.run.mockReset();
    updateCheck.run.mockResolvedValue({ message: "Update check complete. JaneConverter is up to date." });
    relaunch.run.mockResolvedValue(undefined);
    chooseFolder.run.mockReset();
    setDataRoot.run.mockReset();
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

  it("lets the user dismiss an application update and check again", async () => {
    const available = {
      message: "Update check complete. JaneConverter update available: v2.2.0 -> v2.3.0.",
      repo: {
        has_update: true,
        current_version: "2.2.0",
        latest_version: "2.3.0",
        installer_available: true,
        installer_url: "https://github.com/janecerys/JaneConverter/releases/download/v2.3.0/JaneConverter-2.3.0-windows-x64-setup.exe",
        installer_checksum_url: "https://github.com/janecerys/JaneConverter/releases/download/v2.3.0/JaneConverter-2.3.0-windows-x64-setup.exe.sha256",
        release_url: "https://github.com/janecerys/JaneConverter/releases/tag/v2.3.0",
      },
    };
    updateCheck.run.mockReset();
    updateCheck.run.mockResolvedValue(available);
    installUpdate.run.mockResolvedValue(undefined);

    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => { root.render(<SettingsView runtime={sourceRuntime} onStatus={vi.fn()} />); });

    const check = () => Array.from(container.querySelectorAll("button")).find((button) => button.textContent?.includes("Check now"));
    await act(async () => { check()?.click(); await Promise.resolve(); });
    expect(container.textContent).toContain("JaneConverter v2.3.0 is available");
    expect(container.textContent).toContain("Update now");
    expect(container.textContent).toContain("Not now");

    await act(async () => {
      Array.from(container.querySelectorAll("button")).find((button) => button.textContent?.trim() === "Not now")?.click();
      await Promise.resolve();
    });
    expect(container.textContent).not.toContain("JaneConverter v2.3.0 is available");

    await act(async () => { check()?.click(); await Promise.resolve(); });
    expect(container.textContent).toContain("Update now");
    await act(async () => {
      Array.from(container.querySelectorAll("button")).find((button) => button.textContent?.trim() === "Update now")?.click();
      await Promise.resolve();
    });
    expect(installUpdate.run).toHaveBeenCalledWith({
      installerUrl: available.repo.installer_url,
      checksumUrl: available.repo.installer_checksum_url,
      version: available.repo.latest_version,
    });

    await act(async () => { root.unmount(); });
    container.remove();
  });

  it("offers a relaunch action for the current desktop application", async () => {
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

  it("changes the application data root and relaunches", async () => {
    chooseFolder.run.mockResolvedValue("E:/JaneConverterData");
    setDataRoot.run.mockResolvedValue("E:/JaneConverterData");

    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    await act(async () => {
      root.render(<SettingsView runtime={{ ...sourceRuntime, dataRoot: "C:/Users/User/AppData/Local/JaneConverter" }} onStatus={vi.fn()} />);
    });

    await act(async () => {
      Array.from(container.querySelectorAll("button")).find((button) => button.textContent?.trim() === "Browse")?.click();
      await Promise.resolve();
    });
    expect(chooseFolder.run).toHaveBeenCalled();

    await act(async () => {
      Array.from(container.querySelectorAll("button")).find((button) => button.textContent?.includes("Apply and relaunch"))?.click();
      await Promise.resolve();
    });

    expect(setDataRoot.run).toHaveBeenCalledWith("E:/JaneConverterData");
    expect(relaunch.run).toHaveBeenCalled();
    expect(container.textContent).toContain("Data root changed to E:/JaneConverterData.");

    await act(async () => { root.unmount(); });
    container.remove();
  });

  it("identifies production packages and keeps relaunch available", async () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    await act(async () => {
      root.render(<SettingsView runtime={{ mode: "tauri", pythonReady: true, ffmpegReady: true, ffmpegPath: "resources/runtime/bin/ffmpeg", pythonPath: "resources/runtime/engine/JaneConverterEngine", dataRoot: "/home/user/.local/share/JaneConverter", projectRoot: "resources/runtime", gpuAvailable: false, gpuLabel: "CPU mode", packaged: true }} onStatus={vi.fn()} />);
    });

    expect(container.textContent).toContain("Running from a production package");
    expect(container.textContent).toContain("Relaunch now");
    expect(container.textContent).toContain("OS user-data directory");

    await act(async () => { root.unmount(); });
    container.remove();
  });

  it("triggers accent and background color changes from pickers and reset button", async () => {
    const onAccentColorChange = vi.fn();
    const onBgColorChange = vi.fn();
    const onResetColors = vi.fn();
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    await act(async () => {
      root.render(
        <SettingsView
          runtime={sourceRuntime}
          accentColor="#c52b68"
          bgColor="#02000a"
          onAccentColorChange={onAccentColorChange}
          onBgColorChange={onBgColorChange}
          onResetColors={onResetColors}
          onStatus={vi.fn()}
        />,
      );
    });

    const setNativeValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;

    const accentPicker = container.querySelector<HTMLInputElement>('input[aria-label="Accent color picker"]');
    expect(accentPicker).toBeDefined();
    await act(async () => {
      if (accentPicker) {
        setNativeValue?.call(accentPicker, "#06b6d4");
        accentPicker.dispatchEvent(new Event("change", { bubbles: true }));
      }
      await Promise.resolve();
    });
    expect(onAccentColorChange).toHaveBeenCalledWith("#06b6d4");

    const bgPicker = container.querySelector<HTMLInputElement>('input[aria-label="Theme background color picker"]');
    expect(bgPicker).toBeDefined();
    await act(async () => {
      if (bgPicker) {
        setNativeValue?.call(bgPicker, "#09090b");
        bgPicker.dispatchEvent(new Event("change", { bubbles: true }));
      }
      await Promise.resolve();
    });
    expect(onBgColorChange).toHaveBeenCalledWith("#09090b");

    // Also test swatch click
    const cyanSwatch = Array.from(container.querySelectorAll("button")).find((button) => button.getAttribute("title")?.includes("Cyber Cyan"));
    expect(cyanSwatch).toBeDefined();
    await act(async () => {
      cyanSwatch?.click();
      await Promise.resolve();
    });
    expect(onAccentColorChange).toHaveBeenCalledWith("#06b6d4");

    const resetButton = Array.from(container.querySelectorAll("button")).find((button) => button.textContent?.includes("Reset colors"));
    expect(resetButton).toBeDefined();
    await act(async () => {
      resetButton?.click();
      await Promise.resolve();
    });
    expect(onResetColors).toHaveBeenCalled();

    await act(async () => { root.unmount(); });
    container.remove();
  });
});
