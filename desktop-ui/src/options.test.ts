import { describe, expect, it } from "vitest";
import { formatsFor, qualitiesFor } from "./options";

describe("converter option parity", () => {
  it("keeps the legacy category format families", () => {
    expect(formatsFor("Music")).toContain("mp3");
    expect(formatsFor("Video")).toEqual(["mp4", "mkv", "webm", "mov", "gif"]);
    expect(formatsFor("Miscellaneous")).toContain("flac");
  });

  it("keeps legacy quality controls mapped by output format", () => {
    expect(qualitiesFor("wav")).toEqual(["16-bit", "24-bit", "32-bit"]);
    expect(qualitiesFor("flac")).toEqual(["16-bit", "24-bit"]);
    expect(qualitiesFor("ogg")).toEqual(["q10", "q8", "q6", "q4"]);
    expect(qualitiesFor("mp3")).toContain("320k");
    expect(qualitiesFor("mp4")).toContain("balanced");
  });
});