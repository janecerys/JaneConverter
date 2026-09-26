import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

export type Category = "Audio" | "Music" | "Video" | "Image" | "Miscellaneous";
export type EventKind = "started" | "log" | "progress" | "status" | "finished" | "failed" | "cancelled";

export interface RuntimeInfo {
  mode: "tauri" | "browser";
  pythonReady: boolean;
  ffmpegReady: boolean;
  ffmpegPath: string;
  pythonPath: string;
  dataRoot: string;
  projectRoot: string;
  gpuAvailable: boolean;
  gpuLabel: string;
  packaged: boolean;
}

export interface HardwareSnapshot {
  cpuName: string;
  logicalCores: number;
  cpuSystemPct: number;
  cpuAppPct: number;
  ramSystemPct: number;
  ramUsedGb: number;
  ramTotalGb: number;
  ramAppMb: number;
  gpuSystemPct: number;
  gpuVramUsedMb: number;
  gpuVramTotalMb: number;
  gpuAppVramMb: number;
  gpuTempC: number | null;
  gpuName: string;
  telemetrySource: string;
}

export interface ConverterSettings {
  outputDir: string;
  fetchedDir: string;
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

export interface UpdateCheckResult {
  message: string;
  engine?: {
    has_update?: boolean;
    online?: boolean;
    current_version?: string;
    latest_version?: string;
  };
  repo?: {
    has_update?: boolean;
    current_version?: string;
    latest_version?: string;
    installer_available?: boolean;
    installer_url?: string;
    installer_checksum_url?: string;
    release_url?: string;
  };
}

export interface UpdateInstallRequest {
  installerUrl: string;
  checksumUrl: string;
  version: string;
}

export interface ConversionRequest extends Omit<ConverterSettings, "fetchedDir"> {
  source: string;
  playlistIndexes?: string;
  browserSession?: string;
  browserCapturePath?: string;
  facebookCaptureId?: string;
  socialCaptureId?: string;
}

export interface FacebookCaptureResult {
  captureId: string;
  title: string;
  photoCount: number;
}

export interface SocialCaptureResult {
  captureId: string;
  title: string;
  photoCount: number;
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
  source?: string | null;
  bridgeConnected: boolean;
  captureCount?: number;
  capturedMediaKind?: "video" | "audio" | "image";
}

export interface FetchedMedia {
  path: string;
  name: string;
  mediaKind: "video" | "audio" | "image";
  mimeType: string;
  captureMode: "current" | "sequence" | "collect" | "network" | "saved";
  title: string;
  size: number;
}

export interface AccessDiagnostic {
  id: number;
  message: string;
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
  hardwareSnapshot(): Promise<HardwareSnapshot>;
  settingsGet(): Promise<ConverterSettings>;
  settingsSave(settings: ConverterSettings): Promise<void>;
  setDataRoot(path: string): Promise<string>;
  chooseFile(): Promise<string | null>;
  chooseFiles(): Promise<string[]>;
  chooseFolder(): Promise<string | null>;
  openPath(path: string): Promise<void>;
  openFile(path: string): Promise<void>;
  openUrl(url: string): Promise<void>;
  startConversion(request: ConversionRequest): Promise<string>;
  captureFacebookAlbum(source: string, captureId: string): Promise<FacebookCaptureResult>;
  cancelFacebookAlbum(captureId: string): Promise<void>;
  captureSocialPostPhotos(source: string, captureId: string): Promise<SocialCaptureResult>;
  cancelSocialPostPhotos(captureId: string): Promise<void>;
  cancelConversion(jobId: string): Promise<void>;
  loadPlaylist(source: string): Promise<PlaylistCatalog>;
  subscribe(listener: (event: ConverterEvent) => void): Promise<UnlistenFn>;
  scanLibrary(path: string): Promise<LibraryEntry[]>;
  isConvertedLibraryPath(path: string): Promise<boolean>;
  recentConversions(path: string, limit: number): Promise<LibraryEntry[]>;
  dragLibraryFile(path: string): Promise<void>;
  getThumbnail(root: string, path: string): Promise<string | null>;
  moveLibrary(source: string, destinationParent: string): Promise<string>;
  moveFetchedFolder(source: string, destinationParent: string): Promise<string>;
  deleteLibraryEntry(root: string, path: string): Promise<void>;
  createAccessLink(source: string): Promise<AccessStatus>;
  accessStatus(): Promise<AccessStatus>;
  fetchedMedia(): Promise<FetchedMedia[]>;
  accessDiagnostics(): Promise<AccessDiagnostic[]>;
  fetchedMediaThumbnail(path: string): Promise<string | null>;
  discardFetchedMedia(path: string): Promise<void>;
  clearAccessLink(): Promise<void>;
  relaunch(): Promise<void>;
  checkUpdates(): Promise<UpdateCheckResult>;
  installUpdate(update: UpdateInstallRequest): Promise<void>;
}

const demoSettings: ConverterSettings = {
  outputDir: "Project-local/converted",
  fetchedDir: "Project-local/fetched",
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
    return { mode: "browser", pythonReady: false, ffmpegReady: false, ffmpegPath: "", pythonPath: "", dataRoot: "Project-local", projectRoot: "Project-local", gpuAvailable: false, gpuLabel: "Preview mode", packaged: false };
  },
  async hardwareSnapshot() {
    return { cpuName: "Preview mode", logicalCores: 0, cpuSystemPct: 0, cpuAppPct: 0, ramSystemPct: 0, ramUsedGb: 0, ramTotalGb: 0, ramAppMb: 0, gpuSystemPct: 0, gpuVramUsedMb: 0, gpuVramTotalMb: 0, gpuAppVramMb: 0, gpuTempC: null, gpuName: "Unavailable in browser preview", telemetrySource: "Unavailable" };
  },
  async settingsGet() { return { ...demoSettings }; },
  async settingsSave() {},
  async setDataRoot(path) { return path; },
  async chooseFile() { return null; },
  async chooseFiles() { return []; },
  async chooseFolder() { return null; },
  async openPath() {},
  async openFile() {},
  async openUrl() {},
  async startConversion() { return "preview-job"; },
  async captureFacebookAlbum() { throw new Error("Facebook album capture is available in the JaneConverter desktop app."); },
  async cancelFacebookAlbum() {},
  async captureSocialPostPhotos() { return { captureId: "", title: "", photoCount: 0 }; },
  async cancelSocialPostPhotos() {},
  async cancelConversion() {},
  async loadPlaylist() { return { title: "Preview playlist", items: [] }; },
  async subscribe() { return () => {}; },
  async scanLibrary() { return []; },
  async isConvertedLibraryPath() { return false; },
  async recentConversions() { return []; },
  async dragLibraryFile() { throw new Error("Drag files into other apps from the desktop build."); },
  async getThumbnail() { return null; },
  async moveLibrary(source) { return source; },
  async moveFetchedFolder(source) { return source; },
  async deleteLibraryEntry() {},
  async createAccessLink() { return { active: true, link: "Preview mode", browser: "", bridgeConnected: false }; },
  async accessStatus() { return { active: false, link: "", browser: "", bridgeConnected: false }; },
  async fetchedMedia() { return []; },
  async accessDiagnostics() { return []; },
  async fetchedMediaThumbnail() { return null; },
  async discardFetchedMedia() {},
  async clearAccessLink() {},
  async relaunch() {},
  async checkUpdates() { return { message: "Preview mode: update checks are available in the desktop build." }; },
  async installUpdate() {},
};

const isTauriRuntime = () => "__TAURI_INTERNALS__" in window;

const tauriBridge: JaneBridge = {
  runtimeInfo: () => invoke<RuntimeInfo>("runtime_info"),
  hardwareSnapshot: () => invoke<HardwareSnapshot>("hardware_snapshot"),
  settingsGet: () => invoke<ConverterSettings>("settings_get"),
  settingsSave: (settings) => invoke<void>("settings_save", { settings }),
  setDataRoot: (path) => invoke<string>("set_data_root_path", { path }),
  chooseFile: () => invoke<string | null>("choose_file"),
  chooseFiles: () => invoke<string[]>("choose_files"),
  chooseFolder: () => invoke<string | null>("choose_folder"),
  openPath: (path) => invoke<void>("open_path", { path }),
  openFile: (path) => invoke<void>("open_file", { path }),
  openUrl: (url) => invoke<void>("open_url", { url }),
  startConversion: (request) => invoke<string>("start_conversion", { request }),
  captureFacebookAlbum: (source, captureId) => invoke<FacebookCaptureResult>("capture_facebook_album", { source, captureId }),
  cancelFacebookAlbum: (captureId) => invoke<void>("cancel_facebook_album", { captureId }),
  captureSocialPostPhotos: (source, captureId) => invoke<SocialCaptureResult>("capture_social_post_photos", { source, captureId }),
  cancelSocialPostPhotos: (captureId) => invoke<void>("cancel_social_post_photos", { captureId }),
  cancelConversion: (jobId) => invoke<void>("cancel_conversion", { jobId }),
  loadPlaylist: (source) => invoke<PlaylistCatalog>("load_playlist", { source }),
  subscribe: (listener) => listen<ConverterEvent>("converter-event", (event) => listener(event.payload)),
  scanLibrary: (path) => invoke<LibraryEntry[]>("scan_library", { path }),
  isConvertedLibraryPath: (path) => invoke<boolean>("is_converted_library_path", { path }),
  recentConversions: (path, limit) => invoke<LibraryEntry[]>("recent_conversions", { path, limit }),
  dragLibraryFile: (path) => invoke<void>("drag_library_file", { path }),
  getThumbnail: (root, path) => invoke<string | null>("get_thumbnail", { root, path }),
  moveLibrary: (source, destinationParent) => invoke<string>("move_library", { source, destinationParent }),
  moveFetchedFolder: (source, destinationParent) => invoke<string>("move_fetched_folder", { source, destinationParent }),
  deleteLibraryEntry: (root, path) => invoke<void>("delete_library_entry", { root, path }),
  createAccessLink: (source) => invoke<AccessStatus>("create_access_link", { source }),
  accessStatus: () => invoke<AccessStatus>("access_status"),
  fetchedMedia: () => invoke<FetchedMedia[]>("fetched_media"),
  accessDiagnostics: () => invoke<AccessDiagnostic[]>("access_diagnostics"),
  fetchedMediaThumbnail: (path) => invoke<string | null>("fetched_media_thumbnail", { path }),
  discardFetchedMedia: (path) => invoke<void>("discard_fetched_media", { path }),
  clearAccessLink: () => invoke<void>("clear_access_link"),
  relaunch: () => invoke<void>("relaunch"),
  checkUpdates: () => invoke<UpdateCheckResult>("check_updates"),
  installUpdate: (update) => invoke<void>("install_update", { update }),
};

export const bridge: JaneBridge = isTauriRuntime() ? tauriBridge : demoBridge;
