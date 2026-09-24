import type { Category } from "./bridge";

export const audioFormats = ["mp3", "flac", "wav", "aac", "ogg", "m4a"];
export const videoFormats = ["mp4", "mkv", "webm", "mov", "gif"];
export const imageFormats = ["jpg", "png", "webp"];
export const resolutions = ["original", "4k", "1440p", "1080p", "720p", "480p"];

const VIDEO_QUALITY_LABELS: Record<string, string> = {
  best: "Highest quality / least compression",
  high: "High quality / light compression",
  balanced: "Balanced quality / recommended",
  small: "Smaller file / more compression / less detail",
};

const RESOLUTION_LABELS: Record<string, string> = {
  original: "Keep original size — do not resize",
  "4k": "4K Ultra HD — 2160p",
  "1440p": "2.5K — 1440p",
  "1080p": "Full HD — 1080p",
  "720p": "HD — 720p",
  "480p": "SD — 480p",
};

export function videoQualityLabel(value: string): string {
  return VIDEO_QUALITY_LABELS[value] ?? value;
}

export function resolutionLabel(value: string): string {
  return RESOLUTION_LABELS[value] ?? value;
}

export function imageQualityLabel(value: string, format: string): string {
  if (value !== "best") return value;
  if (format === "png") return "Lossless / every pixel preserved";
  if (format === "webp") return "Highest WebP quality / larger file";
  if (format === "jpg" || format === "jpeg") return "Highest JPEG quality / larger file";
  return value;
}

export function formatsFor(category: Category): string[] {
  if (category === "Video") return ["source", ...videoFormats];
  if (category === "Image") return ["source", ...imageFormats];
  if (category === "Miscellaneous") return ["source", ...videoFormats, ...audioFormats, ...imageFormats];
  return ["source", ...audioFormats];
}

export function qualitiesFor(format: string): string[] {
  if (format === "source") return ["best"];
  if (format === "wav") return ["16-bit", "24-bit", "32-bit"];
  if (format === "flac") return ["16-bit", "24-bit"];
  if (format === "ogg") return ["q10", "q8", "q6", "q4"];
  if (imageFormats.includes(format)) return ["best"];
  if (videoFormats.includes(format)) return ["best", "high", "balanced", "small"];
  return ["320k", "256k", "192k", "128k"];
}

export interface IntentPreset {
  id: string;
  name: string;
  description: string;
  group: "Music" | "Video" | "Image" | "Other";
  category: Category;
  format: string;
  bitrate: string;
  sampleRate: number;
  resolution: string;
  normalize: boolean;
  useGpu: boolean;
  preserveQuality?: boolean;
}

export const intentPresets: IntentPreset[] = [
  {
    id: "preserve-quality",
    name: "Preserve Quality",
    description: "Keep source quality: takes the raw file or highest-quality stream without re-encoding",
    group: "Other",
    category: "Video",
    format: "source",
    bitrate: "best",
    sampleRate: 48000,
    resolution: "original",
    normalize: false,
    useGpu: false,
    preserveQuality: true,
  },
  {
    id: "studio-master",
    name: "Studio Master",
    description: "32-bit uncompressed WAV at 48kHz without dynamic compression, with cover art and credits",
    group: "Music",
    category: "Audio",
    format: "wav",
    bitrate: "32-bit",
    sampleRate: 48000,
    resolution: "original",
    normalize: false,
    useGpu: false,
  },
  {
    id: "universal-music",
    name: "Universal Music",
    description: "High-bitrate 320k MP3 with EBU R128 (-14 LUFS) streaming volume leveling, cover art, and credits",
    group: "Music",
    category: "Audio",
    format: "mp3",
    bitrate: "320k",
    sampleRate: 48000,
    resolution: "original",
    normalize: true,
    useGpu: false,
  },
  {
    id: "lossless-flac",
    name: "Lossless FLAC",
    description: "Pristine 24-bit FLAC archive at 48kHz with cover art and credits",
    group: "Music",
    category: "Audio",
    format: "flac",
    bitrate: "24-bit",
    sampleRate: 48000,
    resolution: "original",
    normalize: false,
    useGpu: false,
  },
  {
    id: "universal-video",
    name: "Universal Video",
    description: "Standard 1080p Full HD MP4 with recommended picture quality",
    group: "Video",
    category: "Video",
    format: "mp4",
    bitrate: "balanced",
    sampleRate: 48000,
    resolution: "1080p",
    normalize: false,
    useGpu: true,
  },
  {
    id: "studio-cinematic",
    name: "Studio Cinematic",
    description: "Source-resolution MKV at the highest quality; preserves original video and audio streams when compatible",
    group: "Video",
    category: "Video",
    format: "mkv",
    bitrate: "best",
    sampleRate: 48000,
    resolution: "original",
    normalize: false,
    useGpu: false,
  },
  {
    id: "lossless-image",
    name: "Lossless Image",
    description: "Uncompressed pixel-for-pixel PNG preserving original full image dimensions and clarity",
    group: "Image",
    category: "Image",
    format: "png",
    bitrate: "best",
    sampleRate: 48000,
    resolution: "original",
    normalize: false,
    useGpu: false,
  },
];

export const intentPresetGroups = ["Music", "Video", "Image", "Other"] as const;

export function detectCategoryFromPath(pathOrUrl: string): Category | null {
  if (!pathOrUrl || !pathOrUrl.trim()) return null;
  const cleanPath = pathOrUrl.trim().split("?")[0].split("#")[0];
  const lastDot = cleanPath.lastIndexOf(".");
  if (lastDot === -1) return null;
  const ext = cleanPath.slice(lastDot + 1).toLowerCase();
  if (audioFormats.includes(ext) || ["opus", "alac", "aiff", "wma"].includes(ext)) return "Audio";
  if (videoFormats.includes(ext) || ["avi", "ts", "m2ts", "flv"].includes(ext)) return "Video";
  if (imageFormats.includes(ext) || ["jpeg", "bmp", "svg", "tiff", "ico"].includes(ext)) return "Image";
  return null;
}
