import { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConverterView } from "./ConverterView";
import type { AccessStatus, ConverterSettings, FetchedMedia } from "../bridge";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const bridge = vi.hoisted(() => ({
  chooseFile: vi.fn(),
  chooseFolder: vi.fn(),
  openPath: vi.fn(),
  openUrl: vi.fn(),
  isConvertedLibraryPath: vi.fn().mockResolvedValue(false),
  captureFacebookAlbum: vi.fn(),
  cancelFacebookAlbum: vi.fn(),
}));

vi.mock("../bridge", () => ({ bridge }));

const settings = {
  outputDir: "converted",
  fetchedDir: "fetched",
  category: "Music" as const,
  format: "mp3",
  bitrate: "320k",
  sampleRate: 48000,
  resolution: "original",
  normalize: false,
  useGpu: false,
  saveCover: true,
  saveMetadata: true,
  retries: 2,
};

function renderView(
  onCreateAccess = vi.fn().mockResolvedValue({ active: true, link: "http://127.0.0.1:4321/access/test", browser: "", bridgeConnected: false }),
  access: AccessStatus = { active: false, link: "", browser: "", bridgeConnected: false },
  onStart = vi.fn().mockResolvedValue(undefined),
  selectedCapture: FetchedMedia | null = null,
  onSettings = vi.fn(),
  settingsOverride: Partial<ConverterSettings> = {},
) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  const onStatus = vi.fn();

  act(() => {
    root.render(
      <ConverterView
        settings={{ ...settings, ...settingsOverride }}
        runtime={null}
        events={[]}
        access={access}
        selectedCapture={selectedCapture}
        running={false}
        progress={0}
        status="Ready"
        onSettings={onSettings}
        onStart={onStart}
        onCancel={vi.fn().mockResolvedValue(undefined)}
        onCreateAccess={onCreateAccess}
        onClearAccess={vi.fn().mockResolvedValue(undefined)}
        onStatus={onStatus}
      />,
    );
  });

  return { container, root, onCreateAccess, onStatus, onSettings };
}

describe("Converter account access feedback", () => {
  beforeEach(() => {
    window.scrollTo = vi.fn();
    bridge.openUrl.mockReset();
    bridge.openUrl.mockResolvedValue(undefined);
  });

  it("opens a generic browser capture session without a source URL", async () => {
    const view = renderView();
    const button = Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent?.includes("Create access link"));

    await act(async () => {
      button?.click();
      await Promise.resolve();
    });

    expect(view.container.querySelector('[role="status"]')?.textContent).toContain("Access page opened");
    expect(view.onCreateAccess).toHaveBeenCalledWith("");

    await act(async () => { view.root.unmount(); });
    view.container.remove();
  });

  it("offers a preserve-quality intent preset that selects source format", async () => {
    const view = renderView();
    const button = Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent?.trim() === "Preserve Quality");

    expect(button).toBeDefined();
    await act(async () => { button?.click(); await Promise.resolve(); });

    expect(view.onSettings).toHaveBeenCalledWith(expect.objectContaining({
      format: "source",
      resolution: "original",
      normalize: false,
      useGpu: false,
    }));
    expect(view.onStatus).toHaveBeenCalledWith(expect.stringContaining("Applied Preserve Quality preset"));

    await act(async () => { view.root.unmount(); });
    view.container.remove();
  });

  it("unselects a preset and restores the prior manual settings", async () => {
    const view = renderView();
    const presetButton = Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent?.trim() === "Studio Master");

    expect(presetButton).toBeDefined();
    expect(view.container.textContent).not.toContain("No preset");
    await act(async () => { presetButton?.click(); await Promise.resolve(); });
    expect(presetButton?.getAttribute("aria-pressed")).toBe("true");
    expect(view.onSettings).toHaveBeenLastCalledWith(expect.objectContaining({ format: "wav" }));

    await act(async () => { presetButton?.click(); await Promise.resolve(); });
    expect(presetButton?.getAttribute("aria-pressed")).toBe("false");
    expect(view.onSettings).toHaveBeenLastCalledWith(expect.objectContaining({ format: "mp3", bitrate: "320k", category: "Music" }));
    expect(view.onStatus).toHaveBeenCalledWith(expect.stringContaining("previous conversion settings were restored"));

    await act(async () => { view.root.unmount(); });
    view.container.remove();
  });

  it("restores video settings and keeps relevant advanced controls available", async () => {
    const view = renderView(undefined, undefined, undefined, null, vi.fn(), { category: "Video", format: "mkv", bitrate: "best" });
    const presetButton = Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent?.trim() === "Universal Video");

    await act(async () => { presetButton?.click(); await Promise.resolve(); });
    expect(view.onSettings).toHaveBeenLastCalledWith(expect.objectContaining({ format: "mp4", resolution: "1080p" }));
    await act(async () => { presetButton?.click(); await Promise.resolve(); });
    expect(view.onSettings).toHaveBeenLastCalledWith(expect.objectContaining({ format: "mkv", resolution: "original", useGpu: false }));

    const advancedSwitch = view.container.querySelector<HTMLButtonElement>('button[role="switch"]');
    await act(async () => { advancedSwitch?.click(); await Promise.resolve(); });
    expect(advancedSwitch?.getAttribute("aria-checked")).toBe("true");
    expect(view.container.querySelector<HTMLSelectElement>('select[aria-label="Video quality"]')?.disabled).toBe(false);
    expect(view.container.querySelector<HTMLSelectElement>('select[aria-label="Video resolution"]')?.disabled).toBe(false);
    expect(view.container.querySelector<HTMLSelectElement>('select[aria-label="Audio sample rate"]')?.disabled).toBe(true);

    await act(async () => { view.root.unmount(); });
    view.container.remove();
  });

  it("shows where the user is in the access handoff", async () => {
    const view = renderView();
    const input = view.container.querySelector<HTMLInputElement>('input[aria-label="Source media URL or local path"]');
    const button = Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent?.includes("Create access link"));

    await act(async () => {
      if (input) {
        const setNativeValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
        setNativeValue?.call(input, "https://example.com/private-media");
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }
      button?.click();
      await Promise.resolve();
    });

    expect(view.container.querySelector('[role="status"]')?.textContent).toContain("Access page opened");

    await act(async () => { view.root.unmount(); });
    view.container.remove();
  });

  it("tells the user to capture media after browser access is confirmed", async () => {
    const view = renderView(undefined, { active: true, link: "http://127.0.0.1:4321/access/test", browser: "Vivaldi", bridgeConnected: false });

    expect(view.container.querySelector('[role="status"]')?.textContent).toContain("Browser Capture extension");
    expect(view.container.textContent).toContain("capture the visible media");

    await act(async () => { view.root.unmount(); });
    view.container.remove();
  });

  it("starts conversion from browser capture without requiring a source URL", async () => {
    const onStart = vi.fn().mockResolvedValue(undefined);
    const view = renderView(
      undefined,
      { active: true, link: "http://127.0.0.1:4321/access/test", browser: "Vivaldi", bridgeConnected: true },
      onStart,
    );
    const button = Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent?.includes("Convert media"));

    await act(async () => {
      button?.click();
      await Promise.resolve();
    });

    expect(onStart).toHaveBeenCalledWith("", undefined);

    await act(async () => { view.root.unmount(); });
    view.container.remove();
  });

  it("captures a public Facebook album before starting its local download", async () => {
    const source = "https://www.facebook.com/share/p/1EpX6FjAuC/";
    const onStart = vi.fn().mockResolvedValue(undefined);
    bridge.captureFacebookAlbum.mockReset();
    bridge.captureFacebookAlbum.mockResolvedValue({
      captureId: "12345678-1234-1234-1234-123456789abc",
      title: "Public album",
      photoCount: 9,
    });
    const view = renderView(undefined, undefined, onStart);
    const input = view.container.querySelector('input[aria-label="Source media URL or local path"]') as HTMLInputElement;

    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
      setter?.call(input, source);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    const button = Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent === "Download all photos");

    await act(async () => {
      button?.click();
      await Promise.resolve();
    });

    expect(bridge.captureFacebookAlbum).toHaveBeenCalledWith(source, expect.any(String));
    expect(onStart).toHaveBeenCalledWith(source, undefined, "12345678-1234-1234-1234-123456789abc");

    await act(async () => { view.root.unmount(); });
    view.container.remove();
  });

  it("does not lock output controls to an unselected browser capture", async () => {
    const view = renderView(undefined, {
      active: true,
      link: "http://127.0.0.1:4321/access/test",
      browser: "Vivaldi",
      bridgeConnected: true,
      capturedMediaKind: "video",
    });

    await act(async () => { await Promise.resolve(); });

    expect(view.onSettings).not.toHaveBeenCalled();
    const imageButton = Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent === "Image");
    expect(imageButton).toBeDefined();
    await act(async () => { imageButton?.click(); });
    expect(view.onSettings).toHaveBeenCalledWith(expect.objectContaining({ category: "Image" }));

    await act(async () => { view.root.unmount(); });
    view.container.remove();
  });
  it("switches to image output when the browser capture is an image", async () => {
    const view = renderView(
      undefined,
      {
        active: true,
        link: "http://127.0.0.1:4321/access/test",
        browser: "Vivaldi",
        bridgeConnected: true,
        capturedMediaKind: "image",
      },
      undefined,
      { path: "fetched/image.jpg", name: "image.jpg", mediaKind: "image", mimeType: "image/jpeg", captureMode: "network", title: "image", size: 1000 },
    );

    await act(async () => { await Promise.resolve(); });

    expect(view.container.textContent).toContain("Image");
    expect((view.container.querySelector('select[aria-label="Container format"]') as HTMLSelectElement | null)?.value).toBe("jpg");

    await act(async () => { view.root.unmount(); });
    view.container.remove();
  });

  it("handles dropped web links and files into the converter", async () => {
    const view = renderView();
    const input = view.container.querySelector('input[aria-label="Source media URL or local path"]') as HTMLInputElement;
    expect(input).not.toBeNull();

    // Test dropping a web URL
    await act(async () => {
      const dropEvent = new Event("drop", { bubbles: true, cancelable: true });
      Object.defineProperty(dropEvent, "dataTransfer", {
        value: {
          files: [],
          getData: (format: string) => (format === "text/uri-list" ? "https://youtube.com/watch?v=12345" : ""),
        },
      });
      input.dispatchEvent(dropEvent);
      await Promise.resolve();
    });

    expect(input.value).toBe("https://youtube.com/watch?v=12345");

    await act(async () => { view.root.unmount(); });
    view.container.remove();
  });
});
