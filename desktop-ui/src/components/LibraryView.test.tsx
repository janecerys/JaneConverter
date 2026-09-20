import { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LibraryView } from "./LibraryView";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const fakeBridge = vi.hoisted(() => ({
  scanLibrary: vi.fn(),
  openPath: vi.fn(),
  chooseFolder: vi.fn(),
  moveLibrary: vi.fn(),
  getThumbnail: vi.fn(),
  deleteLibraryEntry: vi.fn(),
}));

vi.mock("../bridge", () => ({ bridge: fakeBridge }));

const settings = {
  outputDir: "D:\\JaneConverter\\converted",
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

describe("Converted library", () => {
  beforeEach(() => {
    fakeBridge.scanLibrary.mockReset();
    fakeBridge.openPath.mockReset();
    fakeBridge.chooseFolder.mockReset();
    fakeBridge.moveLibrary.mockReset();
    fakeBridge.getThumbnail.mockReset();
    fakeBridge.deleteLibraryEntry.mockReset();
    fakeBridge.scanLibrary.mockResolvedValue([
      {
        path: "D:\\JaneConverter\\converted\\Music",
        name: "Music",
        isDirectory: true,
        isPlaylist: false,
        mediaCount: 1,
        totalBytes: 1024,
        extension: "",
      },
      {
        path: "D:\\JaneConverter\\converted\\song.mp3",
        name: "song.mp3",
        isDirectory: false,
        isPlaylist: false,
        mediaCount: 1,
        totalBytes: 1024,
        extension: "MP3",
      },
    ]);
    fakeBridge.getThumbnail.mockResolvedValue("data:image/jpeg;base64,preview");
  });

  it("keeps navigation inside the library and shows root actions", async () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    await act(async () => {
      root.render(<LibraryView settings={settings} onSettings={vi.fn()} onStatus={vi.fn()} />);
    });

    const back = Array.from(container.querySelectorAll("button")).find((button) => button.textContent?.includes("Back"));
    expect(back).toBeDefined();
    expect(back).toHaveProperty("disabled", true);
    expect(container.textContent).toContain("Open folder");
    expect(container.textContent).toContain("Move library");
    expect(container.querySelector('img[alt=""]')).not.toBeNull();

    await act(async () => {
      Array.from(container.querySelectorAll("button")).find((button) => button.textContent?.trim() === "Open")?.click();
      await Promise.resolve();
    });
    expect(fakeBridge.scanLibrary).toHaveBeenLastCalledWith("D:\\JaneConverter\\converted\\Music");

    const nestedBack = Array.from(container.querySelectorAll("button")).find((button) => button.textContent?.includes("Back"));
    expect(nestedBack).toHaveProperty("disabled", false);
    await act(async () => {
      nestedBack?.click();
      await Promise.resolve();
    });
    expect(fakeBridge.scanLibrary).toHaveBeenLastCalledWith("D:\\JaneConverter\\converted");

    await act(async () => { root.unmount(); });
    container.remove();
  });

  it("moves the root library through the native bridge", async () => {
    const onSettings = vi.fn();
    const onStatus = vi.fn();
    fakeBridge.chooseFolder.mockResolvedValue("E:\\Media");
    fakeBridge.moveLibrary.mockResolvedValue("E:\\Media\\converted");
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    await act(async () => {
      root.render(<LibraryView settings={settings} onSettings={onSettings} onStatus={onStatus} />);
    });
    await act(async () => {
      Array.from(container.querySelectorAll("button")).find((button) => button.textContent?.includes("Move library"))?.click();
      await Promise.resolve();
    });

    expect(container.textContent).toContain("Move converted library?");
    expect(fakeBridge.moveLibrary).not.toHaveBeenCalled();
    const confirmButton = Array.from(container.querySelectorAll("button"))
      .filter((button) => button.textContent?.trim() === "Move library")
      .pop();
    expect(confirmButton).toBeDefined();
    await act(async () => {
      confirmButton?.click();
      await Promise.resolve();
    });

    expect(fakeBridge.moveLibrary).toHaveBeenCalledWith(settings.outputDir, "E:\\Media");
    expect(onSettings).toHaveBeenCalledWith({ ...settings, outputDir: "E:\\Media\\converted" });
    expect(onStatus).toHaveBeenCalledWith(expect.stringContaining("Library moved"));
    await act(async () => { root.unmount(); });
    container.remove();
  });
});
