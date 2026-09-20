import { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConverterView } from "./ConverterView";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const bridge = vi.hoisted(() => ({
  chooseFile: vi.fn(),
  chooseFolder: vi.fn(),
  openPath: vi.fn(),
  openUrl: vi.fn(),
}));

vi.mock("../bridge", () => ({ bridge }));

const settings = {
  outputDir: "converted",
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
  access = { active: false, link: "", browser: "", bridgeConnected: false },
) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  const onStatus = vi.fn();

  act(() => {
    root.render(
      <ConverterView
        settings={settings}
        runtime={null}
        events={[]}
        access={access}
        running={false}
        progress={0}
        status="Ready"
        onSettings={vi.fn()}
        onStart={vi.fn().mockResolvedValue(undefined)}
        onCancel={vi.fn().mockResolvedValue(undefined)}
        onCreateAccess={onCreateAccess}
        onClearAccess={vi.fn().mockResolvedValue(undefined)}
        onStatus={onStatus}
      />,
    );
  });

  return { container, root, onCreateAccess, onStatus };
}

describe("Converter account access feedback", () => {
  beforeEach(() => {
    bridge.openUrl.mockReset();
    bridge.openUrl.mockResolvedValue(undefined);
  });

  it("explains that an online source is required when access is clicked too early", async () => {
    const view = renderView();
    const button = Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent?.includes("Create access link"));

    await act(async () => {
      button?.click();
      await Promise.resolve();
    });

    expect(view.container.querySelector('[role="status"]')?.textContent).toContain("Paste an online source URL first");
    expect(view.onCreateAccess).not.toHaveBeenCalled();

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

  it("tells the user that the browser can remain open for the live session path", async () => {
    const view = renderView(undefined, { active: true, link: "http://127.0.0.1:4321/access/test", browser: "Vivaldi", bridgeConnected: false });

    expect(view.container.querySelector('[role="status"]')?.textContent).toContain("keep the browser open");
    expect(view.container.textContent).toContain("read-only in-memory session");

    await act(async () => { view.root.unmount(); });
    view.container.remove();
  });
});
