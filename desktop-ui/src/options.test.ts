import { describe, expect, it } from "vitest";
import {
  formatsFor,
  qualitiesFor,
  intentPresets,
  detectCategoryFromPath,
  resolutionLabel,
  videoQualityLabel,
} from "./options";

describe("converter option parity", () => {
  it("keeps the legacy category format families", () => {
    expect(formatsFor("Music")).toContain("mp3");
    expect(formatsFor("Audio")).toContain("mp3");
    expect(formatsFor("Video")).toContain("mp4");
    expect(formatsFor("Video")).toContain("source");
    expect(formatsFor("Image")).toContain("png");
  });

  it("offers dedicated image formats", () => {
    expect(formatsFor("Image")).toContain("png");
    expect(qualitiesFor("png")).toEqual(["best"]);
  });

  it("keeps legacy quality controls mapped by output format", () => {
    expect(qualitiesFor("mp3")).toContain("320k");
    expect(qualitiesFor("mp4")).toContain("balanced");
  });

  it("explains video quality choices in consumer language", () => {
    expect(videoQualityLabel("best")).toBe("Highest video quality — largest file");
    expect(videoQualityLabel("balanced")).toBe("Good quality — recommended");
    expect(videoQualityLabel("small")).toBe("Smaller file — more compression");
    expect(resolutionLabel("original")).toBe("Keep original size — do not resize");
    expect(resolutionLabel("1080p")).toBe("Full HD — 1080p");
  });

  it("provides intent-based presets matching their target categories", () => {
    expect(intentPresets.length).toBeGreaterThanOrEqual(5);
    const studio = intentPresets.find((p) => p.id === "studio-master");
    expect(studio).toBeDefined();
    expect(studio?.format).toBe("wav");
    expect(studio?.bitrate).toBe("32-bit");

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
    expect(detectCategoryFromPath("song.mp3")).toBe("Audio");
    expect(detectCategoryFromPath("audio.wav")).toBe("Audio");
    expect(detectCategoryFromPath("video.mp4")).toBe("Video");
    expect(detectCategoryFromPath("clip.mkv")).toBe("Video");
    expect(detectCategoryFromPath("photo.png")).toBe("Image");
    expect(detectCategoryFromPath("picture.webp")).toBe("Image");
    expect(detectCategoryFromPath("unknown_no_extension")).toBeNull();
  });
});
