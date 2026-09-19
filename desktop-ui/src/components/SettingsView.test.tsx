import { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsView } from "./SettingsView";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const updateCheck = vi.hoisted(() => ({ run: vi.fn() }));
vi.mock("../bridge", () => ({
  bridge: {
    setFrontendPreference: vi.fn(),
    checkUpdates: updateCheck.run,
  },
}));

describe("Settings updates", () => {
  beforeEach(() => {
    updateCheck.run.mockReset();
    updateCheck.run.mockResolvedValue("Update check complete. JaneConverter is up to date.");
  });

  it("shows the update result inside Settings", async () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    await act(async () => {
      root.render(<SettingsView runtime={null} onStatus={vi.fn()} />);
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
});