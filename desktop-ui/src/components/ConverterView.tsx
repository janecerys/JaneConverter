import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowDownToLine,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clipboard,
  Copy,
  ExternalLink,
  FileAudio,
  FileImage,
  FilePlus2,
  Files,
  FileVideo,
  FolderOpen,
  Info,
  Link2,
  ListMusic,
  LoaderCircle,
  LockKeyhole,
  Play,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Square,
  Trash2,
  Wand2,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import type { AccessStatus, Category, ConverterEvent, ConverterSettings, FetchedMedia, PlaylistCatalog, RuntimeInfo } from "../bridge";
import { bridge } from "../bridge";
import {
  detectCategoryFromPath,
  formatsFor,
  imageFormats,
  imageQualityLabel,
  intentPresets,
  type IntentPreset,
  qualitiesFor,
  resolutionLabel,
  resolutions,
  videoFormats,
  videoQualityLabel,
} from "../options";
import { PlaylistDialog } from "./PlaylistDialog";

export interface QueueItem {
  id: string;
  source: string;
  name: string;
  category: Category;
  status: "queued" | "converting" | "completed" | "failed";
  progress: number;
  outputPath?: string;
  errorMessage?: string;
}

function SelectField({
  label,
  value,
  values,
  onChange,
  disabled = false,
  formatValue,
}: {
  label: string;
  value: string | number;
  values: Array<string | number>;
  onChange: (value: string) => void;
  disabled?: boolean;
  formatValue?: (item: string | number) => string;
}) {
  return (
    <label className="block min-w-0">
      <span className="mb-2 block text-[11px] font-medium text-zinc-500">{label}</span>
      <span className="relative block">
        <select
          aria-label={label}
          disabled={disabled}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="field w-full appearance-none px-3 py-2.5 pr-9 text-sm disabled:cursor-not-allowed disabled:opacity-50"
        >
          {values.map((item) => (
            <option key={item} value={item}>
              {formatValue ? formatValue(item) : String(item)}
            </option>
          ))}
        </select>
        <ChevronDown aria-hidden="true" className="pointer-events-none absolute right-3 top-1/2 size-3.5 -translate-y-1/2 text-zinc-400" />
      </span>
    </label>
  );
}

function Toggle({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  hint?: string;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-white/[0.06] bg-black/10 px-3 py-3 transition-colors hover:border-white/[0.12]">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-0.5 size-4 accent-[#c52b68]"
      />
      <span className="min-w-0">
        <span className="block text-xs text-zinc-300">{label}</span>
        {hint && <span className="mt-1 block text-[10px] leading-relaxed text-zinc-600">{hint}</span>}
      </span>
    </label>
  );
}

export function ConverterView({
  settings,
  runtime,
  events,
  access,
  selectedCapture,
  running,
  progress,
  status,
  onSettings,
  onStart,
  onCancel,
  onCreateAccess,
  onClearAccess,
  onStatus,
}: {
  settings: ConverterSettings;
  runtime: RuntimeInfo | null;
  events: ConverterEvent[];
  access: AccessStatus;
  selectedCapture?: FetchedMedia | null;
  running: boolean;
  progress: number;
  status: string;
  onSettings: (next: ConverterSettings) => void;
  onStart: (source: string, playlistIndexes?: string) => Promise<void>;
  onCancel: () => Promise<void>;
  onCreateAccess: (source: string) => Promise<AccessStatus>;
  onClearAccess: () => Promise<void>;
  onStatus: (message: string) => void;
}) {
  const [source, setSource] = useState("");
  const [playlist, setPlaylist] = useState<PlaylistCatalog | null>(null);
  const [loadingPlaylist, setLoadingPlaylist] = useState(false);
  const [notesOpen, setNotesOpen] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [selectedPresetId, setSelectedPresetId] = useState<string | null>(null);
  const [accessBusy, setAccessBusy] = useState(false);
  const [accessNotice, setAccessNotice] = useState("");
  const [accessNoticeTone, setAccessNoticeTone] = useState<"neutral" | "success" | "error">("neutral");

  // Queue and completion state
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [queueRunning, setQueueRunning] = useState(false);
  const activeQueueIndexRef = useRef<number>(-1);
  const [completedItem, setCompletedItem] = useState<{ name: string; path?: string } | null>(null);
  const [copiedCompleted, setCopiedCompleted] = useState(false);
  const [isDraggingOver, setIsDraggingOver] = useState(false);

  const capturedCategory = selectedCapture?.mediaKind
    ? selectedCapture.mediaKind === "image"
      ? "Image"
      : selectedCapture.mediaKind === "audio"
      ? "Audio"
      : "Video"
    : null;
  const capturedFormat = selectedCapture?.mediaKind
    ? selectedCapture.mediaKind === "image"
      ? "jpg"
      : selectedCapture.mediaKind === "audio"
      ? "mp3"
      : "mp4"
    : null;

  const activeCategory = (capturedCategory || settings.category) === "Music" ? "Audio" : (capturedCategory || settings.category);
  const activeFormat = capturedFormat || settings.format;
  const formats = useMemo(() => formatsFor(activeCategory), [activeCategory]);
  const qualities = useMemo(() => qualitiesFor(activeFormat), [activeFormat]);
  const isVideo = videoFormats.includes(activeFormat);
  const isImage = imageFormats.includes(activeFormat);
  const isAudio = !isVideo && !isImage;
  const lastEvent = events.length ? events[events.length - 1] : null;

  useEffect(() => {
    if (!formats.includes(settings.format)) {
      onSettings({ ...settings, format: formats[0], bitrate: qualitiesFor(formats[0])[0] });
    }
  }, [formats, settings, onSettings]);

  useEffect(() => {
    if (access.bridgeConnected) {
      setAccessBusy(false);
      setAccessNotice(`Browser capture received through ${access.browser || "your browser"}. The selected media is ready to convert.`);
      setAccessNoticeTone("success");
      return;
    }
    if (access.browser) {
      setAccessBusy(false);
      setAccessNotice(`Access confirmed in ${access.browser}. Open the JaneConverter Browser Capture extension and capture the visible media before converting.`);
      setAccessNoticeTone("success");
    }
  }, [access.bridgeConnected, access.browser]);

  useEffect(() => {
    if (!selectedCapture?.mediaKind) return;
    const nextCategory = selectedCapture.mediaKind === "image" ? "Image" : selectedCapture.mediaKind === "audio" ? "Audio" : "Video";
    const nextFormat = selectedCapture.mediaKind === "image" ? "jpg" : selectedCapture.mediaKind === "audio" ? "mp3" : "mp4";
    if (settings.category !== nextCategory || settings.format !== nextFormat) {
      onSettings({ ...settings, category: nextCategory, format: nextFormat, bitrate: qualitiesFor(nextFormat)[0] });
    }
  }, [selectedCapture?.mediaKind]);

  // Track finished completions and queue progress
  useEffect(() => {
    if (!lastEvent) return;
    if (lastEvent.kind === "finished") {
      let outName = "media file";
      if (lastEvent.message.startsWith("Conversion complete: ")) {
        outName = lastEvent.message.replace("Conversion complete: ", "").trim();
      } else if (lastEvent.output) {
        outName = lastEvent.output.replace(/^.*[\\/]/, "");
      }
      const outPath = lastEvent.output || (settings.outputDir ? `${settings.outputDir.replace(/[\\/]+$/, "")}/${outName}` : undefined);
      setCompletedItem({ name: outName, path: outPath });

      if (queueRunning && activeQueueIndexRef.current >= 0) {
        setQueue((curr) =>
          curr.map((item, idx) => {
            if (idx === activeQueueIndexRef.current) {
              return { ...item, status: "completed", progress: 1.0, outputPath: outPath };
            }
            return item;
          })
        );
      }
    } else if (lastEvent.kind === "failed") {
      if (queueRunning && activeQueueIndexRef.current >= 0) {
        setQueue((curr) =>
          curr.map((item, idx) => {
            if (idx === activeQueueIndexRef.current) {
              return { ...item, status: "failed", errorMessage: lastEvent.message };
            }
            return item;
          })
        );
      }
    }
  }, [lastEvent, queueRunning, settings.outputDir]);

  // Sequential queue runner
  useEffect(() => {
    if (!queueRunning) return;
    if (running) return;

    const nextIdx = queue.findIndex((item) => item.status === "queued");
    if (nextIdx === -1) {
      setQueueRunning(false);
      activeQueueIndexRef.current = -1;
      onStatus("Batch conversion queue completed.");
      return;
    }

    activeQueueIndexRef.current = nextIdx;
    setQueue((curr) =>
      curr.map((item, idx) => (idx === nextIdx ? { ...item, status: "converting", progress: 0.05 } : item))
    );
    const targetItem = queue[nextIdx];
    void onStart(targetItem.source);
  }, [queueRunning, running, queue, onStart, onStatus]);

  const update = (patch: Partial<ConverterSettings>) => {
    setSelectedPresetId(null);
    onSettings({ ...settings, ...patch });
  };

  function handleSourceInput(val: string) {
    setSource(val);
    const detected = detectCategoryFromPath(val);
    if (detected && detected !== settings.category) {
      update({ category: detected });
    }
  }

  async function paste() {
    try {
      const value = await navigator.clipboard.readText();
      handleSourceInput(value.trim());
      onStatus("Source pasted from clipboard.");
    } catch {
      onStatus("Clipboard access was unavailable. Paste directly into the source field.");
    }
  }

  async function browseFile() {
    try {
      if (bridge.chooseFiles) {
        const paths = await bridge.chooseFiles();
        if (paths && paths.length > 1) {
          const newItems: QueueItem[] = paths.map((p, idx) => ({
            id: `${Date.now()}-${idx}`,
            source: p,
            name: p.replace(/^.*[\\/]/, ""),
            category: detectCategoryFromPath(p) || activeCategory,
            status: "queued",
            progress: 0,
          }));
          setQueue((curr) => [...curr, ...newItems]);
          onStatus(`Added ${paths.length} items to conversion queue.`);
          return;
        }
        if (paths && paths.length === 1) {
          handleSourceInput(paths[0]);
          onStatus("Local media file selected.");
          return;
        }
      }
    } catch {
      // Fallback to single chooseFile
    }
    const path = await bridge.chooseFile();
    if (path) {
      handleSourceInput(path);
      onStatus("Local media file selected.");
    }
  }

  async function browseBatch() {
    try {
      const paths = bridge.chooseFiles ? await bridge.chooseFiles() : [];
      if (!paths || paths.length === 0) return;
      const newItems: QueueItem[] = paths.map((p, idx) => ({
        id: `${Date.now()}-${idx}`,
        source: p,
        name: p.replace(/^.*[\\/]/, ""),
        category: detectCategoryFromPath(p) || activeCategory,
        status: "queued",
        progress: 0,
      }));
      setQueue((curr) => [...curr, ...newItems]);
      onStatus(`Added ${paths.length} items to conversion queue.`);
    } catch (error) {
      onStatus(error instanceof Error ? error.message : String(error));
    }
  }

  function handleSingleSource(rawInput: string) {
    let clean = rawInput.trim();
    if (clean.startsWith("file://")) {
      try {
        clean = decodeURIComponent(clean.replace(/^file:\/\/\/?/, ""));
        if (/^[a-zA-Z]:/.test(clean)) {
          clean = clean.replace(/\//g, "\\");
        }
      } catch {}
    }
    handleSourceInput(clean);
    onStatus(`Source set to: ${clean.replace(/^.*[\\/]/, "") || clean}`);
  }

  function handleDroppedPaths(paths: string[]) {
    if (!paths || paths.length === 0) return;
    if (paths.length === 1) {
      handleSingleSource(paths[0]);
    } else {
      const newItems: QueueItem[] = paths.map((p, idx) => {
        let clean = p.trim().replace(/^file:\/\/\/?/, "");
        if (/^[a-zA-Z]:/.test(clean)) clean = clean.replace(/\//g, "\\");
        return {
          id: `${Date.now()}-${idx}`,
          source: clean,
          name: clean.replace(/^.*[\\/]/, "") || clean,
          category: detectCategoryFromPath(clean) || activeCategory,
          status: "queued",
          progress: 0,
        };
      });
      setQueue((curr) => [...curr, ...newItems]);
      onStatus(`Added ${paths.length} dropped items to conversion queue.`);
    }
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingOver(true);
  }

  function handleDragLeave(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;
    setIsDraggingOver(false);
  }

  function handleDropEvent(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingOver(false);

    // 1. Files dropped via browser/webview
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const fileList = Array.from(e.dataTransfer.files);
      const filePaths = fileList
        .map((f) => (f as any).path || (f as any).webkitRelativePath || f.name)
        .filter(Boolean);
      if (filePaths.length > 0) {
        handleDroppedPaths(filePaths);
        return;
      }
    }

    // 2. URLs or plain text dragged from browser
    const uriList = e.dataTransfer.getData("text/uri-list");
    const plainText = e.dataTransfer.getData("text/plain") || e.dataTransfer.getData("text");
    const droppedText = (uriList || plainText || "").trim();

    if (droppedText) {
      const lines = droppedText.split(/[\r\n]+/).map((l) => l.trim()).filter(Boolean);
      if (lines.length > 1) {
        handleDroppedPaths(lines);
      } else {
        handleSingleSource(lines[0]);
      }
    }
  }

  // Native Tauri drag-and-drop listener
  useEffect(() => {
    let unlisten: (() => void) | undefined;
    if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
      void import("@tauri-apps/api/webview")
        .then(({ getCurrentWebview }) => {
          return getCurrentWebview().onDragDropEvent((event) => {
            if (event.payload.type === "over" || event.payload.type === "enter") {
              setIsDraggingOver(true);
            } else if (event.payload.type === "leave") {
              setIsDraggingOver(false);
            } else if (event.payload.type === "drop") {
              setIsDraggingOver(false);
              if (event.payload.paths && event.payload.paths.length > 0) {
                handleDroppedPaths(event.payload.paths);
              }
            }
          });
        })
        .then((fn) => {
          unlisten = fn;
        })
        .catch(() => {});
    }
    return () => {
      unlisten?.();
    };
  }, [activeCategory]);

  async function browseOutput() {
    const path = await bridge.chooseFolder();
    if (path) update({ outputDir: path });
  }

  async function loadPlaylist() {
    if (!source.trim()) {
      onStatus("Paste a playlist or album URL first.");
      return;
    }
    setLoadingPlaylist(true);
    try {
      const catalog = await bridge.loadPlaylist(source.trim());
      setPlaylist(catalog);
      onStatus(`Loaded ${catalog.items.length} tracks from ${catalog.title}.`);
    } catch (error) {
      onStatus(error instanceof Error ? error.message : String(error));
    } finally {
      setLoadingPlaylist(false);
    }
  }

  async function createAccess() {
    setAccessBusy(true);
    const sourceUrl = source.trim();
    setAccessNotice(sourceUrl ? "Creating a temporary access page and opening your browser..." : "Creating a browser capture session and opening your browser...");
    setAccessNoticeTone("neutral");
    try {
      const nextAccess = await onCreateAccess(sourceUrl);
      if (nextAccess.browser) {
        setAccessNotice(`Access page opened in ${nextAccess.browser}. Confirm access there, then use the Browser Capture extension to capture the visible media.`);
        setAccessNoticeTone("success");
      } else {
        setAccessNotice("Access page opened. Sign in there if needed, confirm access, then use the Browser Capture extension.");
        setAccessNoticeTone("neutral");
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setAccessNotice(message);
      setAccessNoticeTone("error");
    } finally {
      setAccessBusy(false);
    }
  }

  async function clearAccess() {
    setAccessBusy(true);
    try {
      await onClearAccess();
      setAccessNotice("Account access cleared. Future conversions will use public-only extraction.");
      setAccessNoticeTone("neutral");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setAccessNotice(message);
      setAccessNoticeTone("error");
    } finally {
      setAccessBusy(false);
    }
  }

  async function copyAccessLink() {
    try {
      await navigator.clipboard.writeText(access.link);
      setAccessNotice("Temporary access link copied to the clipboard.");
      setAccessNoticeTone("success");
    } catch {
      setAccessNotice("The link could not be copied. Use Open link instead.");
      setAccessNoticeTone("error");
    }
  }

  async function openAccessLink() {
    try {
      await bridge.openUrl(access.link);
      setAccessNotice("Access page opened in your browser. Confirm it there, then use Browser Capture on the source page.");
      setAccessNoticeTone("neutral");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setAccessNotice(message);
      setAccessNoticeTone("error");
    }
  }

  async function convert(indexes?: string) {
    if (queue.length > 0) {
      setQueueRunning(true);
      return;
    }
    if (!source.trim() && !access.bridgeConnected) {
      onStatus("Paste a source URL, choose a local file, or capture media in the browser first.");
      return;
    }
    await onStart(source.trim(), indexes);
  }

  function applyPreset(preset: IntentPreset) {
    if (preset.preserveQuality) {
      update({
        category: (["Audio", "Video", "Image"].includes(activeCategory) ? activeCategory : preset.category) as Category,
        format: preset.format,
        resolution: "original",
        normalize: false,
        useGpu: false,
        bitrate: qualitiesFor(preset.format)[0],
      });
      setSelectedPresetId(preset.id);
      onStatus(`Applied ${preset.name} preset: ${preset.description}.`);
      return;
    }
    update({
      category: preset.category,
      format: preset.format,
      bitrate: preset.bitrate,
      sampleRate: preset.sampleRate,
      resolution: preset.resolution,
      normalize: preset.normalize,
      useGpu: preset.useGpu,
    });
    setSelectedPresetId(preset.id);
    onStatus(`Applied ${preset.name} preset: ${preset.description}.`);
  }

  return (
    <div className="mx-auto max-w-[1180px] space-y-3.5 pb-2">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }} className="flex items-end justify-between gap-5">
        <div>
          <div className="mono-label">Universal media studio</div>
          <h1 className="mt-1 text-2xl font-semibold tracking-[-.04em] text-white">Convert with less friction.</h1>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-zinc-500">Keep the source behavior you already trust, with a calmer workspace around it.</p>
        </div>
        <div className="hidden rounded-full border border-white/[0.07] bg-white/[0.025] px-3 py-1.5 text-[11px] text-zinc-500 md:block">
          <span className={`mr-2 inline-block size-1.5 rounded-full ${runtime?.pythonReady ? "bg-emerald-400" : "bg-amber-400"}`} />
          {runtime?.pythonReady ? "Python engine ready" : "Engine setup required"}
        </div>
      </motion.div>

      {/* Source Input Section */}
      <section
        onDragOver={handleDragOver}
        onDragEnter={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDropEvent}
        className={`panel p-4 relative transition-all duration-200 ${
          isDraggingOver
            ? "border-[#c52b68] bg-[#c52b68]/[0.08] shadow-[0_0_30px_rgba(197,43,104,0.22)] ring-1 ring-[#c52b68]"
            : ""
        }`}
      >
        {isDraggingOver && (
          <div className="pointer-events-none absolute inset-0 z-20 flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-[#c52b68] bg-black/65 backdrop-blur-sm">
            <ArrowDownToLine className="size-8 animate-bounce text-pink-400" />
            <div className="mt-2 text-sm font-semibold text-white">Drop media or web links here</div>
            <div className="mt-0.5 text-xs text-pink-300">Drop a file or URL to set source, or multiple files for batch queue</div>
          </div>
        )}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-medium text-zinc-200">Source media</div>
            <div className="mt-1 text-xs text-zinc-600">Paste or drag a public URL, choose or drop files, or queue a batch.</div>
          </div>
          <span className="text-[11px] text-zinc-600">{queue.length > 0 ? `${queue.length} items queued` : source ? "Source provided" : "Ready for URL, drop, or path"}</span>
        </div>
        <div className="mt-4 flex gap-2">
          <input
            aria-label="Source media URL or local path"
            value={source}
            onChange={(event) => handleSourceInput(event.target.value)}
            onDragOver={handleDragOver}
            onDrop={handleDropEvent}
            placeholder="Paste or drag YouTube, Spotify, SoundCloud link, or drop local files..."
            className="field min-w-0 flex-1 px-3.5 py-3 text-sm placeholder:text-zinc-700"
          />
          <button type="button" onClick={() => void paste()} className="subtle-button flex items-center gap-2 px-3 text-xs">
            <Clipboard className="size-3.5" /> Paste
          </button>
          <button type="button" onClick={() => void browseFile()} className="subtle-button flex items-center gap-2 px-3 text-xs">
            <FilePlus2 className="size-3.5" /> Browse
          </button>
          <button type="button" onClick={() => void browseBatch()} className="subtle-button flex items-center gap-2 px-3 text-xs">
            <Files className="size-3.5" /> Batch
          </button>
          <button
            type="button"
            disabled={loadingPlaylist || running}
            onClick={() => void loadPlaylist()}
            className="subtle-button flex items-center gap-2 px-3 text-xs disabled:opacity-50"
          >
            <ListMusic className="size-3.5" /> {loadingPlaylist ? "Loading..." : "Playlist tracks"}
          </button>
        </div>

        {/* Account Access */}
        <div className="mt-5 border-t border-white/[0.06] pt-4">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-xs text-zinc-400">
              <LockKeyhole className="size-3.5 text-zinc-600" /> Optional account access <span className="text-zinc-700">- session only</span>
            </div>
            <span
              className={`text-[11px] ${
                access.bridgeConnected
                  ? "text-emerald-400"
                  : access.browser
                  ? "text-emerald-400"
                  : access.active
                  ? "text-amber-300"
                  : "text-zinc-600"
              }`}
            >
              {access.bridgeConnected
                ? `Browser capture received through ${access.browser || "browser"}`
                : access.browser
                ? `Access confirmed in ${access.browser}`
                : access.active
                ? "Access page open"
                : "Public-only extraction"}
            </span>
          </div>
          <p className="mt-2 max-w-3xl text-[11px] leading-relaxed text-zinc-600">
            {selectedCapture
              ? "Fetched media selected from the browser capture inbox. Choose your output settings and convert it whenever you are ready."
              : access.bridgeConnected
              ? "Browser Capture connected for this session. Keep capturing from the active browser page; every item is kept temporarily in the Fetched Media tab. This access session does not affect unrelated URL or local-file conversions."
              : access.active
              ? "Open the media in this browser, sign in if needed, confirm access here, then open the JaneConverter Browser Capture extension. Choose Capture current media or Capture story sequence. Unrelated URL and local-file conversions remain public/local."
              : "Create a temporary local link with or without a source URL. JaneConverter receives only media you explicitly capture with the optional extension; it never reads or stores your password, cookies, cache, or browser profile."}
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {access.link && (
              <button type="button" disabled={accessBusy} onClick={() => void copyAccessLink()} className="subtle-button flex items-center gap-2 px-3 py-2 text-xs disabled:cursor-not-allowed disabled:opacity-50">
                <Link2 className="size-3.5" /> Copy link
              </button>
            )}
            {access.link && (
              <button type="button" disabled={accessBusy} onClick={() => void openAccessLink()} className="subtle-button px-3 py-2 text-xs disabled:cursor-not-allowed disabled:opacity-50">
                Open link
              </button>
            )}
            {access.active ? (
              <button type="button" disabled={accessBusy} onClick={() => void clearAccess()} className="subtle-button px-3 py-2 text-xs disabled:cursor-not-allowed disabled:opacity-50">
                {accessBusy ? "Working..." : "Clear access"}
              </button>
            ) : (
              <button
                type="button"
                disabled={accessBusy || running}
                onClick={() => void createAccess()}
                className="subtle-button flex items-center gap-2 px-3 py-2 text-xs disabled:cursor-not-allowed disabled:opacity-50"
              >
                {accessBusy ? <LoaderCircle className="size-3.5 animate-spin" /> : <ShieldCheck className="size-3.5" />}{" "}
                {accessBusy ? "Opening access page..." : "Create access link"}
              </button>
            )}
            {access.link && <span className="max-w-[420px] truncate text-[11px] text-zinc-700">{access.link}</span>}
          </div>
          {accessNotice && (
            <div
              role="status"
              aria-live="polite"
              className={`mt-3 flex items-start gap-2 rounded-lg border px-3 py-2.5 text-[11px] leading-relaxed ${
                accessNoticeTone === "success"
                  ? "border-emerald-400/20 bg-emerald-400/[0.05] text-emerald-300"
                  : accessNoticeTone === "error"
                  ? "border-rose-400/20 bg-rose-400/[0.05] text-rose-300"
                  : "border-white/[0.08] bg-white/[0.025] text-zinc-400"
              }`}
            >
              {accessNoticeTone === "success" ? (
                <CheckCircle2 className="mt-0.5 size-3.5 shrink-0" />
              ) : accessNoticeTone === "error" ? (
                <AlertCircle className="mt-0.5 size-3.5 shrink-0" />
              ) : (
                <Info className="mt-0.5 size-3.5 shrink-0" />
              )}
              <span>{accessNotice}</span>
            </div>
          )}
        </div>

        <button
          type="button"
          onClick={() => setNotesOpen((value) => !value)}
          className="mt-4 flex items-center gap-2 text-xs text-zinc-500 transition-colors hover:text-zinc-300"
        >
          <Info className="size-3.5" /> Source notes and common failures <span className="text-zinc-700">{notesOpen ? "Hide" : "Show"}</span>
        </button>
        {notesOpen && (
          <div className="mt-3 grid gap-3 rounded-xl border border-white/[0.06] bg-black/15 p-4 text-[11px] leading-relaxed text-zinc-500 md:grid-cols-3">
            <div>
              <div className="mb-1 text-zinc-300">Apple Music</div>
              Public catalog links provide metadata and artwork, not a normal downloadable subscription stream. Region restrictions, removed tracks, music videos, alternate versions, and missing public matches can fail. Direct song links with a track selector work best.
            </div>
            <div>
              <div className="mb-1 text-zinc-300">Spotify</div>
              Spotify provides metadata; JaneConverter searches supported public sources for a matching stream. Private, deleted, region-locked, or mismatched tracks can fail.
            </div>
            <div>
              <div className="mb-1 text-zinc-300">Other sources and files</div>
              Age gates, login walls, bot checks, rate limits, provider changes, unreadable local files, FFmpeg availability, permissions, and free disk space can affect conversion. Console has the exact detail.
            </div>
          </div>
        )}
      </section>

      {/* Lightweight Batch Queue Section */}
      {queue.length > 0 && (
        <section className="panel p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Files className="size-4 text-[#c52b68]" />
              <div className="text-sm font-medium text-zinc-200">Conversion Queue</div>
              <span className="rounded-full bg-white/[0.08] px-2 py-0.5 text-[10px] text-zinc-400">{queue.length} items</span>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setQueue([])}
                disabled={queueRunning}
                className="subtle-button px-2.5 py-1 text-xs text-zinc-500 hover:text-rose-400 disabled:opacity-50"
              >
                Clear queue
              </button>
            </div>
          </div>
          <div className="mt-3 divide-y divide-white/[0.05] rounded-xl border border-white/[0.06] bg-black/15">
            {queue.map((item) => (
              <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 p-3 text-xs">
                <div className="flex items-center gap-2.5 min-w-0 flex-1">
                  {item.category === "Image" ? (
                    <FileImage className="size-4 text-sky-400 shrink-0" />
                  ) : item.category === "Video" ? (
                    <FileVideo className="size-4 text-[#c52b68] shrink-0" />
                  ) : (
                    <FileAudio className="size-4 text-emerald-400 shrink-0" />
                  )}
                  <div className="min-w-0">
                    <div className="truncate text-zinc-200">{item.name}</div>
                    <div className="truncate text-[10px] text-zinc-600">{item.source}</div>
                  </div>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  {item.status === "converting" && (
                    <span className="flex items-center gap-1.5 text-[11px] text-amber-300">
                      <LoaderCircle className="size-3 animate-spin" /> Converting...
                    </span>
                  )}
                  {item.status === "completed" && (
                    <div className="flex items-center gap-2">
                      <span className="flex items-center gap-1 text-[11px] text-emerald-400">
                        <CheckCircle2 className="size-3" /> Done
                      </span>
                      {item.outputPath && (
                        <button
                          type="button"
                          onClick={() => void bridge.openFile(item.outputPath!)}
                          className="subtle-button px-2 py-0.5 text-[10px] text-emerald-300"
                        >
                          Open
                        </button>
                      )}
                    </div>
                  )}
                  {item.status === "failed" && (
                    <div className="flex items-center gap-2">
                      <span className="flex items-center gap-1 text-[11px] text-rose-400" title={item.errorMessage}>
                        <AlertCircle className="size-3" /> Failed
                      </span>
                      <button
                        type="button"
                        onClick={() => {
                          setQueue((curr) =>
                            curr.map((it) => (it.id === item.id ? { ...it, status: "queued", errorMessage: undefined } : it))
                          );
                          if (!queueRunning) setQueueRunning(true);
                        }}
                        className="subtle-button px-2 py-0.5 text-[10px] text-zinc-400 hover:text-white"
                      >
                        <RotateCcw className="size-2.5" /> Retry
                      </button>
                    </div>
                  )}
                  {item.status === "queued" && <span className="text-[11px] text-zinc-600">Queued</span>}
                  <button
                    type="button"
                    disabled={item.status === "converting"}
                    onClick={() => setQueue((curr) => curr.filter((it) => it.id !== item.id))}
                    className="text-zinc-600 hover:text-rose-400 disabled:opacity-30"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Output & Presets Parameters */}
      <section className="panel p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-medium text-zinc-200">Output and conversion presets</div>
            <div className="mt-0.5 text-xs text-zinc-600">Select an intent goal or fine-tune settings below.</div>
          </div>
          <div className="flex items-center gap-1 rounded-xl border border-white/[0.07] bg-black/15 p-1">
            {(["Audio", "Video", "Image"] as const).map((category) => (
              <button
                key={category}
                type="button"
                onClick={() => update({ category })}
                className={`rounded-lg px-3 py-1.5 text-[11px] transition-colors ${
                  activeCategory === category ? "bg-white/[0.09] text-white" : "text-zinc-600 hover:text-zinc-300"
                }`}
              >
                {category}
              </button>
            ))}
          </div>
        </div>

        {/* Intent Presets Toolbar */}
        <div className="mt-3 rounded-xl border border-white/[0.05] bg-black/15 p-2.5">
          <div className="flex items-center gap-2 mb-1.5">
            <Wand2 className="size-3.5" style={{ color: "var(--accent-color, #c52b68)" }} />
            <span className="text-[11px] font-medium text-zinc-400">1-Click Presets:</span>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={() => {
                setSelectedPresetId(null);
                setShowAdvanced(true);
                onStatus("No preset selected. Choose your own conversion settings.");
              }}
              className={`rounded-lg px-2.5 py-1 text-xs transition-colors ${
                selectedPresetId === null
                  ? "text-white font-medium"
                  : "border border-white/[0.08] bg-black/20 text-zinc-400 hover:border-white/[0.18] hover:text-white"
              }`}
              style={selectedPresetId === null ? { backgroundColor: "var(--accent-color, #c52b68)", boxShadow: "0 1px 6px var(--accent-glow, rgba(197,43,104,0.3))" } : undefined}
              title="Pick quality and parameters manually"
            >
              No preset
            </button>
            {intentPresets.map((preset) => {
              const isSelected = selectedPresetId === preset.id;
              return (
                <button
                  key={preset.id}
                  type="button"
                  onClick={() => applyPreset(preset)}
                  className={`rounded-lg px-2.5 py-1 text-xs transition-colors ${
                    isSelected
                      ? "text-white font-medium"
                      : "border border-white/[0.08] bg-black/20 text-zinc-400 hover:border-white/[0.18] hover:text-white"
                  }`}
                  style={isSelected ? { backgroundColor: "var(--accent-color, #c52b68)", boxShadow: "0 1px 6px var(--accent-glow, rgba(197,43,104,0.3))" } : undefined}
                  title={preset.description}
                >
                  {preset.name}
                </button>
              );
            })}
          </div>
        </div>

        {/* Primary Controls */}
        <div className="mt-3.5 grid gap-3 md:grid-cols-2">
          <SelectField
            label="Container format"
            value={activeFormat}
            values={formats}
            formatValue={(format) => (format === "source" ? "Source (preserve original)" : String(format).toUpperCase())}
            onChange={(format) => update({ format, bitrate: qualitiesFor(format)[0] })}
          />
          <div className="flex items-end">
            <button
              type="button"
              onClick={() => setShowAdvanced((v) => !v)}
              className="subtle-button flex w-full items-center justify-between px-3 py-2.5 text-xs text-zinc-400 hover:text-white"
            >
              <span>{showAdvanced ? "Hide advanced parameters" : "Show advanced parameters (bitrate, sample rate, GPU)"}</span>
              {showAdvanced ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
            </button>
          </div>
        </div>

        {/* Collapsible Advanced Parameters */}
        <AnimatePresence>
          {showAdvanced && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="overflow-hidden"
            >
              <div className="mt-4 border-t border-white/[0.06] pt-4">
                <div className="grid gap-3 md:grid-cols-3">
                  <SelectField
                    label={isVideo ? "Picture quality (compression)" : isImage ? "Image quality" : "Audio bitrate / quality"}
                    value={isImage ? "best" : settings.bitrate}
                    values={qualities}
                    formatValue={(v) => (isVideo ? videoQualityLabel(String(v)) : isImage ? imageQualityLabel(String(v)) : String(v))}
                    onChange={(bitrate) => update({ bitrate })}
                  />
                  {isVideo && (
                    <SelectField
                      label="Picture size (resolution)"
                      value={settings.resolution}
                      values={resolutions}
                      formatValue={(v) => resolutionLabel(String(v))}
                      onChange={(resolution) => update({ resolution })}
                    />
                  )}
                  {isAudio && (
                    <SelectField
                      label="Audio sample rate"
                      value={settings.sampleRate}
                      values={[44100, 48000, 96000]}
                      onChange={(sampleRate) => update({ sampleRate: Number(sampleRate) })}
                    />
                  )}
                </div>
                <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
                  {isAudio && (
                    <Toggle
                      checked={settings.normalize}
                      onChange={(normalize) => update({ normalize })}
                      label="EBU R128 normalization"
                      hint="-14 LUFS streaming target"
                    />
                  )}
                  {isVideo && (
                    <Toggle
                      checked={settings.useGpu}
                      onChange={(useGpu) => update({ useGpu })}
                      label="Hardware acceleration"
                      hint={runtime?.gpuAvailable ? runtime.gpuLabel : "CPU mode available"}
                    />
                  )}
                  {!isImage && (
                    <>
                      <Toggle
                        checked={settings.saveCover}
                        onChange={(saveCover) => update({ saveCover })}
                        label="Embed and save cover art"
                        hint="Artwork / thumbnail where available"
                      />
                      <Toggle
                        checked={settings.saveMetadata}
                        onChange={(saveMetadata) => update({ saveMetadata })}
                        label="Export metadata and credits"
                        hint="Human-readable .txt metadata"
                      />
                    </>
                  )}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </section>

      {/* 1-Click Completion Banner */}
      {completedItem && (
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-xl border border-emerald-500/20 bg-emerald-500/[0.06] p-3.5 text-xs text-zinc-200"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <CheckCircle2 className="size-4 text-emerald-400 shrink-0" />
              <div>
                <div className="font-medium text-white">{completedItem.name}</div>
                <div className="text-[11px] text-zinc-400">Conversion finished and verified via ffprobe.</div>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {completedItem.path && (
                <button
                  type="button"
                  onClick={() => void bridge.openFile(completedItem.path!)}
                  className="subtle-button flex items-center gap-1.5 px-3 py-1.5 text-xs text-emerald-300 hover:text-white"
                >
                  <ExternalLink className="size-3.5" /> Open file
                </button>
              )}
              <button
                type="button"
                onClick={() => void bridge.openPath(settings.outputDir)}
                className="subtle-button flex items-center gap-1.5 px-3 py-1.5 text-xs"
              >
                <FolderOpen className="size-3.5" /> Open folder
              </button>
              {completedItem.path && (
                <button
                  type="button"
                  onClick={async () => {
                    await navigator.clipboard.writeText(completedItem.path!);
                    setCopiedCompleted(true);
                    setTimeout(() => setCopiedCompleted(false), 2000);
                  }}
                  className="subtle-button flex items-center gap-1.5 px-3 py-1.5 text-xs"
                >
                  <Copy className="size-3.5" /> {copiedCompleted ? "Copied!" : "Copy path"}
                </button>
              )}
              {completedItem.path && (
                <button
                  type="button"
                  onClick={() => {
                    handleSourceInput(completedItem.path!);
                    setCompletedItem(null);
                    onStatus("Output file loaded as new conversion source.");
                  }}
                  className="subtle-button flex items-center gap-1.5 px-3 py-1.5 text-xs"
                >
                  Use as source
                </button>
              )}
            </div>
          </div>
        </motion.div>
      )}

      {/* Unified Export Destination & Convert Action Panel */}
      <section className="panel overflow-hidden p-4">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-12 lg:items-center">
          {/* Left Column: Export Destination */}
          <div className="lg:col-span-7">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-xs font-medium text-zinc-200">
                <FolderOpen className="size-3.5 text-zinc-400" /> Export folder
              </div>
              <span className="hidden sm:inline text-[10px] text-zinc-500 truncate">Default: project-local converted media</span>
            </div>
            <div className="mt-2 flex gap-2">
              <input
                aria-label="Export folder"
                value={settings.outputDir}
                onChange={(event) => update({ outputDir: event.target.value })}
                className="field min-w-0 flex-1 px-3 py-2 text-xs"
              />
              <button type="button" onClick={() => void browseOutput()} className="subtle-button px-3 py-2 text-xs whitespace-nowrap">
                Browse
              </button>
              <button type="button" onClick={() => void bridge.openPath(settings.outputDir)} className="subtle-button flex items-center gap-1.5 px-3 py-2 text-xs whitespace-nowrap">
                <FolderOpen className="size-3.5" /> Open
              </button>
            </div>
          </div>

          {/* Right Column: Compact Convert Action & High-Visibility Progress Bar */}
          <div className="flex flex-col justify-center border-t border-white/[0.06] pt-3 lg:col-span-5 lg:border-t-0 lg:border-l lg:pl-5 lg:pt-0">
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={running || (queue.length > 0 && queueRunning)}
                onClick={() => void convert()}
                className="primary-button flex h-9.5 flex-1 items-center justify-center gap-2 px-4 text-xs font-semibold shadow-sm transition-all disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Play className="size-3.5 fill-current" />
                {running
                  ? "Conversion running"
                  : queue.length > 0
                  ? `Convert queue (${queue.filter((q) => q.status === "queued").length} remaining)`
                  : "Convert media"}
              </button>
              {running && (
                <button type="button" onClick={() => void onCancel()} className="danger-button flex h-9.5 items-center gap-1.5 px-3 text-xs">
                  <Square className="size-3" /> Abort
                </button>
              )}
            </div>

            {/* High-visibility progress bar & percentage */}
            <div className="mt-2">
              <div className="flex items-center justify-between gap-2 text-[11px]">
                <span className={`truncate ${running ? "text-zinc-200 font-medium" : "text-zinc-500"}`}>
                  {status || "Ready to convert"}
                </span>
                <span
                  className="shrink-0 font-mono font-bold text-xs"
                  style={{ color: running ? "var(--accent-color, #ec4899)" : "#71717a" }}
                >
                  {Math.round(progress * 100)}%
                </span>
              </div>
              <div className="mt-1 h-2 overflow-hidden rounded-full bg-white/[0.06] p-[1px] ring-1 ring-white/10">
                <motion.div
                  className="h-full rounded-full"
                  style={{
                    background: "linear-gradient(to right, var(--accent-color, #c52b68), var(--accent-hover, #e0407b))",
                    boxShadow: "0 0 8px var(--accent-glow, rgba(197,43,104,0.4))",
                  }}
                  animate={{ width: `${Math.round(progress * 100)}%` }}
                  transition={{ ease: "easeOut", duration: 0.25 }}
                />
              </div>
              {lastEvent && (
                <div className="mt-1 flex items-center gap-1.5 text-[10px] text-zinc-500 truncate">
                  <RefreshCw
                    className={`size-2.5 shrink-0 ${running ? "animate-spin" : ""}`}
                    style={running ? { color: "var(--accent-color, #ec4899)" } : undefined}
                  />
                  <span className="truncate">Engine: {lastEvent.message}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      {playlist && <PlaylistDialog catalog={playlist} onClose={() => setPlaylist(null)} onConfirm={(indexes) => { setPlaylist(null); void convert(indexes); }} />}
      {loadingPlaylist && (
        <div className="fixed inset-0 z-40 grid place-items-center bg-black/45 backdrop-blur-sm">
          <div className="panel flex items-center gap-3 px-5 py-4 text-sm text-zinc-300">
            <RefreshCw className="size-4 animate-spin text-zinc-500" /> Reading playlist catalog...
          </div>
        </div>
      )}
    </div>
  );
}
