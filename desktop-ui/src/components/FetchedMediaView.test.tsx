import { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FetchedMediaView } from "./FetchedMediaView";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const bridge = vi.hoisted(() => ({
  fetchedMedia: vi.fn(),
  fetchedMediaThumbnail: vi.fn(),
  openFile: vi.fn(),
  openPath: vi.fn(),
  chooseFolder: vi.fn(),
  moveFetchedFolder: vi.fn(),
  discardFetchedMedia: vi.fn(),
}));

vi.mock("../bridge", () => ({ bridge }));

const item = {
  path: "C:/JaneConverter/temp/story-one.jpg",
  name: "story-one.jpg",
  mediaKind: "image" as const,
  mimeType: "image/jpeg",
  captureMode: "sequence" as const,
  title: "Kathleen Puse story",
  size: 156 * 1024,
};

describe("FetchedMediaView", () => {
  beforeEach(() => { vi.clearAllMocks(); });
  it("renders fetched thumbnails and discards the selected item", async () => {
    bridge.fetchedMedia.mockResolvedValue([item]);
    bridge.fetchedMediaThumbnail.mockResolvedValue("data:image/jpeg;base64,preview");
    bridge.discardFetchedMedia.mockResolvedValue(undefined);

    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    await act(async () => {
      root.render(
        <FetchedMediaView
          access={{ active: true, link: "", browser: "Vivaldi", bridgeConnected: true }}
          settings={{ outputDir: "converted", fetchedDir: "fetched", category: "Music", format: "mp3", bitrate: "320k", sampleRate: 48000, resolution: "original", normalize: false, useGpu: false, saveCover: true, saveMetadata: true, retries: 2 }}
          onSettings={vi.fn()}
          onSelect={vi.fn()}
          onDiscard={vi.fn()}
          onStatus={vi.fn()}
        />,
      );
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(container.querySelector('img[alt="Kathleen Puse story"]')?.getAttribute("src")).toBe("data:image/jpeg;base64,preview");
    expect(container.textContent).toContain("Open file");
    expect(container.textContent).toContain("Open path");

    const discard = container.querySelector<HTMLButtonElement>('button[aria-label="Discard story-one.jpg"]');
    await act(async () => {
      discard?.click();
      await Promise.resolve();
    });

    expect(bridge.discardFetchedMedia).toHaveBeenCalledWith(item.path);
    expect(container.textContent).not.toContain("story-one.jpg");


    await act(async () => { root.unmount(); });
    container.remove();
  });

  it("moves the fetched media folder through the native bridge", async () => {
    const onSettings = vi.fn();
    const onStatus = vi.fn();
    bridge.chooseFolder.mockResolvedValue("E:/Media");
    bridge.moveFetchedFolder.mockResolvedValue("E:/Media/fetched");

    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    await act(async () => {
      root.render(
        <FetchedMediaView
          access={{ active: false, link: "", browser: "", bridgeConnected: false }}
          settings={{ outputDir: "converted", fetchedDir: "C:/JaneConverter/fetched", category: "Music", format: "mp3", bitrate: "320k", sampleRate: 48000, resolution: "original", normalize: false, useGpu: false, saveCover: true, saveMetadata: true, retries: 2 }}
          onSettings={onSettings}
          onSelect={vi.fn()}
          onDiscard={vi.fn()}
          onStatus={onStatus}
        />,
      );
      await Promise.resolve();
      await Promise.resolve();
    });

    await act(async () => {
      Array.from(container.querySelectorAll("button")).find((button) => button.textContent?.includes("Move fetched folder"))?.click();
      await Promise.resolve();
    });

    expect(container.textContent).toContain("Move fetched media folder?");

    const confirmButton = Array.from(container.querySelectorAll("button"))
      .find((button) => button.textContent?.trim() === "Move folder");
    expect(confirmButton).toBeDefined();

    await act(async () => {
      confirmButton?.click();
      await Promise.resolve();
    });

    expect(bridge.moveFetchedFolder).toHaveBeenCalledWith("C:/JaneConverter/fetched", "E:/Media");
    expect(onSettings).toHaveBeenCalledWith(expect.objectContaining({ fetchedDir: "E:/Media/fetched" }));
    expect(onStatus).toHaveBeenCalledWith(expect.stringContaining("Fetched media folder moved"));

    await act(async () => { root.unmount(); });
    container.remove();
  });

it("provides a quiet, clickable manual refresh control", async () => {
    bridge.fetchedMedia.mockResolvedValue([]);

    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    await act(async () => {
      root.render(
        <FetchedMediaView
          access={{ active: false, link: "", browser: "", bridgeConnected: false }}
          settings={{ outputDir: "converted", fetchedDir: "fetched", category: "Music", format: "mp3", bitrate: "320k", sampleRate: 48000, resolution: "original", normalize: false, useGpu: false, saveCover: true, saveMetadata: true, retries: 2 }}
          onSettings={vi.fn()}
          onSelect={vi.fn()}
          onDiscard={vi.fn()}
          onStatus={vi.fn()}
        />,
      );
      await Promise.resolve();
    });

    const refresh = container.querySelector<HTMLButtonElement>('button[aria-label="Refresh fetched media"]');
    expect(refresh).not.toBeNull();
    expect(refresh?.querySelector("svg")?.getAttribute("class") ?? "").not.toContain("animate-spin");
    const callsBefore = bridge.fetchedMedia.mock.calls.length;

    await act(async () => {
      refresh?.click();
      await Promise.resolve();
    });

    expect(bridge.fetchedMedia.mock.calls.length).toBeGreaterThan(callsBefore);

    await act(async () => { root.unmount(); });
    container.remove();
  });});
