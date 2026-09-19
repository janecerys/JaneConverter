import type { Category } from "./bridge";

export const audioFormats = ["mp3", "flac", "wav", "aac", "ogg", "m4a"];
export const videoFormats = ["mp4", "mkv", "webm", "mov", "gif"];
export const resolutions = ["original", "4k", "1440p", "1080p", "720p", "480p"];

export function formatsFor(category: Category): string[] {
  if (category === "Video") return [...videoFormats];
  if (category === "Miscellaneous") return [...audioFormats, ...videoFormats];
  return [...audioFormats];
}

export function qualitiesFor(format: string): string[] {
  if (format === "wav") return ["16-bit", "24-bit", "32-bit"];
  if (format === "flac") return ["16-bit", "24-bit"];
  if (format === "ogg") return ["q10", "q8", "q6", "q4"];
  if (videoFormats.includes(format)) return ["best", "high", "balanced", "small"];
  return ["320k", "256k", "192k", "128k"];
}