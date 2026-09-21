import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it, vi } from "vitest";
import { FetchedMediaView } from "./FetchedMediaView";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const bridge = vi.hoisted(() => ({
  fetchedMedia: vi.fn(),
  fetchedMediaThumbnail: vi.fn(),
  openFile: vi.fn(),
  openPath: vi.fn(),
  chooseFolder: vi.fn(),
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
});
