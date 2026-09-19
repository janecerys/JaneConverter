import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it, vi } from "vitest";
import { Sidebar } from "./Sidebar";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("Sidebar layout", () => {
  it("places the workspace note directly below the navigation", async () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    await act(async () => {
      root.render(<Sidebar activeView="converter" onChange={vi.fn()} />);
    });

    const nav = container.querySelector("nav");
    expect(nav?.nextElementSibling?.textContent).toContain("Project-local workspace");
    expect(nav?.nextElementSibling?.className).toContain("mt-4");
    expect(nav?.nextElementSibling?.className).not.toContain("mt-auto");

    await act(async () => { root.unmount(); });
    container.remove();
  });
});
