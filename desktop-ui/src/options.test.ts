import { describe, expect, it } from "vitest";
import { formatsFor, qualitiesFor, intentPresets, detectCategoryFromPath } from "./options";

describe("converter option parity", () => {
  it("keeps the legacy category format families", () => {
    expect(formatsFor("Music")).toContain("mp3");
    expect(formatsFor("Video")).toEqual(["mp4", "mkv", "webm", "mov", "gif"]);
    expect(formatsFor("Miscellaneous")).toContain("flac");
  });

  it("offers dedicated image formats", () => {
    expect(formatsFor("Image")).toEqual(["jpg", "png", "webp"]);
    expect(qualitiesFor("png")).toEqual(["best"]);
  });

  it("keeps legacy quality controls mapped by output format", () => {
    expect(qualitiesFor("wav")).toEqual(["16-bit", "24-bit", "32-bit"]);
    expect(qualitiesFor("flac")).toEqual(["16-bit", "24-bit"]);
    expect(qualitiesFor("ogg")).toEqual(["q10", "q8", "q6", "q4"]);
    expect(qualitiesFor("mp3")).toContain("320k");
    expect(qualitiesFor("mp4")).toContain("balanced");
  });

  it("provides intent-based presets matching their target categories", () => {
    expect(intentPresets.length).toBeGreaterThanOrEqual(5);
    const studio = intentPresets.find((p) => p.id === "studio-master");
    expect(studio).toBeDefined();
    expect(studio?.format).toBe("wav");
    expect(studio?.bitrate).toBe("24-bit");

    const music = intentPresets.find((p) => p.id === "universal-music");
    expect(music?.format).toBe("mp3");
    expect(music?.normalize).toBe(true);

    const video = intentPresets.find((p) => p.id === "universal-video");
    expect(video?.format).toBe("mp4");
    expect(video?.useGpu).toBe(true);

    const image = intentPresets.find((p) => p.id === "lossless-image");
    expect(image?.format).toBe("png");
    expect(image?.bitrate).toBe("best");

    const preserve = intentPresets.find((p) => p.id === "preserve-quality");
    expect(preserve?.name).toBe("Preserve Quality");
    expect(preserve?.preserveQuality).toBe(true);
  });

  it("detects media category accurately from file extensions", () => {
    expect(detectCategoryFromPath("song.mp3")).toBe("Music");
    expect(detectCategoryFromPath("audio.wav")).toBe("Music");
    expect(detectCategoryFromPath("video.mp4")).toBe("Video");
    expect(detectCategoryFromPath("clip.mkv")).toBe("Video");
    expect(detectCategoryFromPath("photo.png")).toBe("Image");
    expect(detectCategoryFromPath("picture.webp")).toBe("Image");
    expect(detectCategoryFromPath("unknown_no_extension")).toBeNull();
  });
});
