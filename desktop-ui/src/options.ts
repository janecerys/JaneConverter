import type { Category } from "./bridge";

export const audioFormats = ["mp3", "flac", "wav", "aac", "ogg", "m4a"];
export const videoFormats = ["mp4", "mkv", "webm", "mov", "gif"];
export const imageFormats = ["jpg", "png", "webp"];
export const resolutions = ["original", "4k", "1440p", "1080p", "720p", "480p"];

export function formatsFor(category: Category): string[] {
  if (category === "Video") return [...videoFormats];
  if (category === "Image") return [...imageFormats];
  if (category === "Miscellaneous") return [...audioFormats, ...videoFormats, ...imageFormats];
  return [...audioFormats];
}

export function qualitiesFor(format: string): string[] {
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
    description: "Keep the selected format and skip quality-changing processing; use lossless stream copy when compatible",
    category: "Miscellaneous",
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
    description: "24-bit uncompressed WAV at 48kHz without dynamic compression",
    category: "Music",
    format: "wav",
    bitrate: "24-bit",
    sampleRate: 48000,
    resolution: "original",
    normalize: false,
    useGpu: false,
  },
  {
    id: "universal-music",
    name: "Universal Music",
    description: "High-bitrate 320k MP3 with EBU R128 (-14 LUFS) streaming normalization",
    category: "Music",
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
    description: "Pristine 24-bit FLAC for archival and audiophile listening",
    category: "Music",
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
    description: "High-compatibility MP4 with original resolution and hardware acceleration",
    category: "Video",
    format: "mp4",
    bitrate: "best",
    sampleRate: 48000,
    resolution: "original",
    normalize: false,
    useGpu: true,
  },
  {
    id: "lossless-image",
    name: "Lossless Image",
    description: "Crisp, uncompressed PNG with maximum visual fidelity",
    category: "Image",
    format: "png",
    bitrate: "best",
    sampleRate: 48000,
    resolution: "original",
    normalize: false,
    useGpu: false,
  },
  {
    id: "web-image",
    name: "Web Image",
    description: "Modern high-efficiency WebP image for web and social media",
    category: "Image",
    format: "webp",
    bitrate: "best",
    sampleRate: 48000,
    resolution: "original",
    normalize: false,
    useGpu: false,
  },
];

export function detectCategoryFromPath(pathOrUrl: string): Category | null {
  if (!pathOrUrl || !pathOrUrl.trim()) return null;
  const cleanPath = pathOrUrl.trim().split("?")[0].split("#")[0];
  const lastDot = cleanPath.lastIndexOf(".");
  if (lastDot === -1) return null;
  const ext = cleanPath.slice(lastDot + 1).toLowerCase();
  if (audioFormats.includes(ext) || ["opus", "alac", "aiff", "wma"].includes(ext)) return "Music";
  if (videoFormats.includes(ext) || ["avi", "ts", "m2ts", "flv"].includes(ext)) return "Video";
  if (imageFormats.includes(ext) || ["jpeg", "bmp", "svg", "tiff", "ico"].includes(ext)) return "Image";
  return null;
}
