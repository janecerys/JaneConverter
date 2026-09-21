import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";
import App from "./App";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("Application shell", () => {
  it("suppresses the native webview context menu", async () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    await act(async () => {
      root.render(<App />);
    });

    const event = new MouseEvent("contextmenu", { bubbles: true, cancelable: true });
    container.firstElementChild?.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);

    await act(async () => { root.unmount(); });
    container.remove();
  });
});