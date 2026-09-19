import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

export type Category = "Music" | "Video" | "Miscellaneous";
export type FrontendPreference = "tauri" | "rust" | "python";
export type EventKind = "started" | "log" | "progress" | "status" | "finished" | "failed" | "cancelled";

export interface RuntimeInfo {
  mode: "tauri" | "browser";
  pythonReady: boolean;
  ffmpegReady: boolean;
  pythonPath: string;
  dataRoot: string;
  projectRoot: string;
  gpuAvailable: boolean;
  gpuLabel: string;
  frontendPreference: FrontendPreference;
}

export interface ConverterSettings {
  outputDir: string;
  category: Category;
  format: string;
  bitrate: string;
  sampleRate: number;
  resolution: string;
  normalize: boolean;
  useGpu: boolean;
  saveCover: boolean;
  saveMetadata: boolean;
  retries: number;
}

export interface ConversionRequest extends ConverterSettings {
  source: string;
  playlistIndexes?: string;
  browserSession?: string;
}

export interface ConverterEvent {
  jobId: string;
  kind: EventKind;
  message: string;
  progress?: number;
  output?: string;
}

export interface PlaylistItem {
  index: number;
  title: string;
  artist: string;
  duration: string;
  url: string;
}

export interface PlaylistCatalog {
  title: string;
  items: PlaylistItem[];
}

export interface AccessStatus {
  active: boolean;
  link: string;
  browser: string;
}

export interface LibraryEntry {
  path: string;
  name: string;
  isDirectory: boolean;
  isPlaylist: boolean;
  mediaCount: number;
  totalBytes: number;
  extension: string;
}

export interface JaneBridge {
  runtimeInfo(): Promise<RuntimeInfo>;
  settingsGet(): Promise<ConverterSettings>;
  settingsSave(settings: ConverterSettings): Promise<void>;
  chooseFile(): Promise<string | null>;
  chooseFolder(): Promise<string | null>;
  openPath(path: string): Promise<void>;
  openUrl(url: string): Promise<void>;
  startConversion(request: ConversionRequest): Promise<string>;
  cancelConversion(jobId: string): Promise<void>;
  loadPlaylist(source: string): Promise<PlaylistCatalog>;
  subscribe(listener: (event: ConverterEvent) => void): Promise<UnlistenFn>;
  scanLibrary(path: string): Promise<LibraryEntry[]>;
  getThumbnail(root: string, path: string): Promise<string | null>;
  moveLibrary(source: string, destinationParent: string): Promise<string>;
  deleteLibraryEntry(root: string, path: string): Promise<void>;
  createAccessLink(source: string): Promise<AccessStatus>;
  accessStatus(): Promise<AccessStatus>;
  clearAccessLink(): Promise<void>;
  setFrontendPreference(preference: FrontendPreference): Promise<void>;
  relaunch(): Promise<void>;
  checkUpdates(): Promise<string>;
}

const demoSettings: ConverterSettings = {
  outputDir: "Project-local/converted",
  category: "Music",
  format: "mp3",
  bitrate: "320k",
  sampleRate: 48000,
  resolution: "original",
  normalize: false,
  useGpu: false,
  saveCover: true,
  saveMetadata: true,
  retries: 2,
};

const demoBridge: JaneBridge = {
  async runtimeInfo() {
    return { mode: "browser", pythonReady: false, ffmpegReady: false, pythonPath: "", dataRoot: "Project-local", projectRoot: "Project-local", gpuAvailable: false, gpuLabel: "Preview mode", frontendPreference: "tauri" };
  },
  async settingsGet() { return { ...demoSettings }; },
  async settingsSave() {},
  async chooseFile() { return null; },
  async chooseFolder() { return null; },
  async openPath() {},
  async openUrl() {},
  async startConversion() { return "preview-job"; },
  async cancelConversion() {},
  async loadPlaylist() { return { title: "Preview playlist", items: [] }; },
  async subscribe() { return () => {}; },
  async scanLibrary() { return []; },
  async getThumbnail() { return null; },
  async moveLibrary(source) { return source; },
  async deleteLibraryEntry() {},
  async createAccessLink() { return { active: true, link: "Preview mode", browser: "" }; },
  async accessStatus() { return { active: false, link: "", browser: "" }; },
  async clearAccessLink() {},
  async setFrontendPreference() {},
  async relaunch() {},
  async checkUpdates() { return "Preview mode: update checks are available in the desktop build."; },
};

const isTauriRuntime = () => "__TAURI_INTERNALS__" in window;

const tauriBridge: JaneBridge = {
  runtimeInfo: () => invoke<RuntimeInfo>("runtime_info"),
  settingsGet: () => invoke<ConverterSettings>("settings_get"),
  settingsSave: (settings) => invoke<void>("settings_save", { settings }),
  chooseFile: () => invoke<string | null>("choose_file"),
  chooseFolder: () => invoke<string | null>("choose_folder"),
  openPath: (path) => invoke<void>("open_path", { path }),
  openUrl: (url) => invoke<void>("open_url", { url }),
  startConversion: (request) => invoke<string>("start_conversion", { request }),
  cancelConversion: (jobId) => invoke<void>("cancel_conversion", { jobId }),
  loadPlaylist: (source) => invoke<PlaylistCatalog>("load_playlist", { source }),
  subscribe: (listener) => listen<ConverterEvent>("converter-event", (event) => listener(event.payload)),
  scanLibrary: (path) => invoke<LibraryEntry[]>("scan_library", { path }),
  getThumbnail: (root, path) => invoke<string | null>("get_thumbnail", { root, path }),
  moveLibrary: (source, destinationParent) => invoke<string>("move_library", { source, destinationParent }),
  deleteLibraryEntry: (root, path) => invoke<void>("delete_library_entry", { root, path }),
  createAccessLink: (source) => invoke<AccessStatus>("create_access_link", { source }),
  accessStatus: () => invoke<AccessStatus>("access_status"),
  clearAccessLink: () => invoke<void>("clear_access_link"),
  setFrontendPreference: (preference) => invoke<void>("set_frontend_preference", { preference }),
  relaunch: () => invoke<void>("relaunch"),
  checkUpdates: () => invoke<string>("check_updates"),
};

export const bridge: JaneBridge = isTauriRuntime() ? tauriBridge : demoBridge;