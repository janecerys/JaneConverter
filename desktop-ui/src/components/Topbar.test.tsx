import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";
import { Topbar } from "./Topbar";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("Topbar help", () => {
  it("opens an in-app help dialog when the help control is clicked", async () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    await act(async () => {
      root.render(<Topbar runtime={null} />);
    });

    expect(container.textContent).not.toContain("A quieter control room for your media.");
    expect(container.textContent).not.toContain("Conversion workspace");

    const help = container.querySelector<HTMLButtonElement>('[aria-label="JaneConverter help"]');
    expect(help).not.toBeNull();
    await act(async () => {
      help?.click();
    });

    expect(container.querySelector('[role="dialog"]')).not.toBeNull();
    expect(container.textContent).toContain("Using JaneConverter");

    await act(async () => { root.unmount(); });
    container.remove();
  });
});