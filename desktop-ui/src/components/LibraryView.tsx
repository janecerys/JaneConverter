import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ExternalLink,
  FileAudio,
  Folder,
  FolderInput,
  FolderOpen,
  ImageIcon,
  RefreshCw,
  Trash2,
  Video,
} from "lucide-react";
import { motion } from "framer-motion";
import type { ConverterSettings, LibraryEntry } from "../bridge";
import { bridge } from "../bridge";

function size(value: number) {
  return value < 1024 * 1024
    ? Math.round(value / 1024) + " KB"
    : (value / (1024 * 1024)).toFixed(1) + " MB";
}

function pathKey(value: string) {
  return value.replace(/\//g, "\\").replace(/\\+$/, "").toLowerCase();
}

function isInside(root: string, candidate: string) {
  const rootKey = pathKey(root);
  const candidateKey = pathKey(candidate);
  return candidateKey === rootKey || candidateKey.startsWith(rootKey + "\\");
}

function parentPath(value: string) {
  const index = Math.max(value.lastIndexOf("\\"), value.lastIndexOf("/"));
  return index > 0 ? value.slice(0, index) : value;
}

function baseName(value: string) {
  const trimmed = value.replace(/[\\/]+$/, "");
  const index = Math.max(trimmed.lastIndexOf("\\"), trimmed.lastIndexOf("/"));
  return index >= 0 ? trimmed.slice(index + 1) : trimmed;
}

function joinPath(parent: string, name: string) {
  return parent.replace(/[\\/]+$/, "") + "\\" + name;
}

type PendingAction =
  | { kind: "move"; destination: string }
  | { kind: "delete"; entry: LibraryEntry };

function mediaIcon(entry: LibraryEntry) {
  if (entry.extension === "MP4" || entry.extension === "MKV" || entry.extension === "WEBM" || entry.extension === "MOV" || entry.extension === "GIF") {
    return <Video size={17} />;
  }
  return <FileAudio size={17} />;
}

export function LibraryView({
  settings,
  onSettings,
  onStatus,
}: {
  settings: ConverterSettings;
  onSettings: (settings: ConverterSettings) => void;
  onStatus: (message: string) => void;
}) {
  const [root, setRoot] = useState(settings.outputDir);
  const [currentPath, setCurrentPath] = useState(settings.outputDir);
  const [entries, setEntries] = useState<LibraryEntry[]>([]);
  const [previews, setPreviews] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [moving, setMoving] = useState(false);
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const refreshSequence = useRef(0);
  const cancelConfirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!pendingAction) return;
    cancelConfirmRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPendingAction(null);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [pendingAction]);

  async function loadPreviews(scanned: LibraryEntry[], libraryRoot: string, token: number) {
    const candidates = scanned.slice(0, 24);
    let nextIndex = 0;
    async function worker() {
      while (nextIndex < candidates.length) {
        const entry = candidates[nextIndex++];
        try {
          const preview = await bridge.getThumbnail(libraryRoot, entry.path);
          if (preview && token === refreshSequence.current) {
            setPreviews((current) => ({ ...current, [entry.path]: preview }));
          }
        } catch {
          // A missing cover, unsupported codec, or unavailable FFmpeg should not block browsing.
        }
      }
    }
    await Promise.all([worker(), worker(), worker()]);
  }

  async function refresh(path = currentPath, libraryRoot = root) {
    const token = ++refreshSequence.current;
    setLoading(true);
    try {
      const scanned = await bridge.scanLibrary(path);
      if (token !== refreshSequence.current) return;
      setEntries(scanned);
      setPreviews({});
      void loadPreviews(scanned, libraryRoot, token);
    } catch (error) {
      onStatus(error instanceof Error ? error.message : String(error));
    } finally {
      if (token === refreshSequence.current) setLoading(false);
    }
  }

  useEffect(() => {
    setRoot(settings.outputDir);
    setCurrentPath(settings.outputDir);
    void refresh(settings.outputDir, settings.outputDir);
  }, [settings.outputDir]);

  function navigate(path: string) {
    if (!isInside(root, path)) {
      onStatus("For safety, the library browser cannot leave the configured export folder.");
      return;
    }
    setCurrentPath(path);
    void refresh(path);
  }

  function goBack() {
    if (pathKey(currentPath) === pathKey(root)) return;
    const parent = parentPath(currentPath);
    navigate(isInside(root, parent) ? parent : root);
  }

  async function openPath(path: string) {
    try {
      await bridge.openPath(path);
    } catch (error) {
      onStatus(error instanceof Error ? error.message : String(error));
    }
  }

  async function moveLibrary() {
    const destinationParent = await bridge.chooseFolder();
    if (!destinationParent) return;
    const destination = joinPath(destinationParent, baseName(root));
    if (pathKey(destinationParent) === pathKey(parentPath(root))) {
      onStatus("Choose a different parent folder for the library.");
      return;
    }
    if (isInside(root, destinationParent)) {
      onStatus("The new library location cannot be inside the current library.");
      return;
    }
    setPendingAction({ kind: "move", destination });
  }

  async function confirmPendingAction() {
    const action = pendingAction;
    if (!action) return;
    setPendingAction(null);

    if (action.kind === "move") {
      setMoving(true);
      try {
        const movedTo = await bridge.moveLibrary(root, parentPath(action.destination));
        const nextSettings = { ...settings, outputDir: movedTo };
        onSettings(nextSettings);
        onStatus("Library moved to " + movedTo + ".");
      } catch (error) {
        onStatus(error instanceof Error ? error.message : String(error));
      } finally {
        setMoving(false);
      }
      return;
    }

    try {
      await bridge.deleteLibraryEntry(root, action.entry.path);
      onStatus(action.entry.name + " deleted.");
      await refresh(currentPath);
    } catch (error) {
      onStatus(error instanceof Error ? error.message : String(error));
    }
  }

  function remove(entry: LibraryEntry) {
    setPendingAction({ kind: "delete", entry });
  }

  /*
   * Keep confirmation inside the Tauri surface so it matches the design
   * system instead of looking like a browser-owned localhost dialog.
   */
  function pendingActionCopy() {
    if (!pendingAction) return null;
    if (pendingAction.kind === "delete") {
      return {
        title: "Delete media?",
        message: "Delete " + pendingAction.entry.name + "? This cannot be undone.",
        confirm: "Delete file",
      };
    }
    return {
      title: "Move converted library?",
      message: "Move the converted library to " + pendingAction.destination + "? JaneConverter will keep the same library folder name.",
      confirm: "Move library",
    };
  }

  const confirmation = pendingActionCopy();
  const atRoot = pathKey(currentPath) === pathKey(root);

  return (
    <div className="mx-auto max-w-[1180px] space-y-5 pb-10">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="mono-label">Project library</div>
          <h1 className="mt-2 text-3xl font-semibold tracking-[-.04em] text-white">Converted media.</h1>
          <p className="mt-2 text-sm text-zinc-500">Browse the organized folders produced by the existing engine.</p>
        </div>
        <button type="button" onClick={() => void refresh()} className="subtle-button flex items-center gap-2 px-3 py-2 text-xs">
          <RefreshCw className={"size-3.5 " + (loading ? "animate-spin" : "")} /> Refresh
        </button>
      </motion.div>

      <section className="panel space-y-3 p-4">
        <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-500">
          <button
            type="button"
            disabled={atRoot}
            title={atRoot ? "Already at the library root" : "Go to the parent folder"}
            onClick={goBack}
            className={"subtle-button flex items-center gap-2 px-3 py-2 " + (atRoot ? "cursor-not-allowed opacity-40" : "")}
          >
            <ArrowLeft className="size-3.5" /> Back
          </button>
          <span className="truncate font-mono text-[11px] text-zinc-700">{currentPath}</span>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.06] pt-3">
          <div>
            <div className="text-xs text-zinc-400">Library root</div>
            <div className="mt-1 truncate font-mono text-[11px] text-zinc-600">{root}</div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => void openPath(root)} className="subtle-button flex items-center gap-2 px-3 py-2 text-xs">
              <ExternalLink className="size-3.5" /> Open folder
            </button>
            <button type="button" disabled={moving} onClick={() => void moveLibrary()} className="subtle-button flex items-center gap-2 px-3 py-2 text-xs disabled:cursor-wait disabled:opacity-60">
              <FolderInput className={"size-3.5 " + (moving ? "animate-pulse" : "")} /> {moving ? "Moving library..." : "Move library"}
            </button>
          </div>
        </div>
      </section>

      <section className="space-y-2">
        {!entries.length && <div className="panel py-14 text-center text-sm text-zinc-600">{loading ? "Scanning converted media..." : "No converted media found in this folder."}</div>}
        {entries.slice(0, 500).map((entry) => {
          const preview = previews[entry.path];
          const details = entry.isDirectory
            ? entry.mediaCount + " media item" + (entry.mediaCount === 1 ? "" : "s") + " - " + size(entry.totalBytes)
            : entry.extension + " - " + size(entry.totalBytes);
          return (
            <motion.div key={entry.path} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="panel flex flex-wrap items-center gap-3 px-4 py-3">
              <div className="grid size-12 shrink-0 place-items-center overflow-hidden rounded-xl border border-white/[0.07] bg-black/15 text-zinc-500">
                {preview ? (
                  <img src={preview} alt="" className="size-full object-cover" onError={() => setPreviews((current) => { const next = { ...current }; delete next[entry.path]; return next; })} />
                ) : entry.isDirectory ? (
                  <Folder className={entry.isPlaylist ? "text-[#d75b88]" : ""} size={17} />
                ) : (
                  mediaIcon(entry)
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm text-zinc-300">{entry.name}</div>
                <div className="mt-1 text-[11px] text-zinc-600">{details}{entry.isPlaylist ? " - playlist" : ""}</div>
              </div>
              {entry.isDirectory ? (
                <button type="button" onClick={() => navigate(entry.path)} className="subtle-button flex items-center gap-2 px-3 py-2 text-xs">
                  <FolderOpen className="size-3.5" /> Open
                </button>
              ) : (
                <button type="button" onClick={() => void openPath(entry.path)} className="subtle-button px-3 py-2 text-xs">Show file</button>
              )}
              <button type="button" onClick={() => remove(entry)} className="grid size-8 place-items-center rounded-lg text-zinc-600 transition-colors hover:bg-red-500/10 hover:text-red-300" aria-label={"Delete " + entry.name}>
                <Trash2 size={14} />
              </button>
            </motion.div>
          );
        })}
        {entries.length > 500 && <div className="text-center text-[11px] text-zinc-700">Showing the first 500 items to keep the library responsive.</div>}
        {!loading && entries.length > 0 && Object.keys(previews).length === 0 && (
          <div className="flex items-center justify-center gap-2 pt-2 text-[11px] text-zinc-700">
            <ImageIcon size={13} /> Covers and previews appear when embedded artwork or a supported video frame is available.
          </div>
        )}
      </section>

      {pendingAction && confirmation && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="fixed inset-0 z-[80] grid place-items-center bg-black/70 p-4 backdrop-blur-sm"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setPendingAction(null);
          }}
        >
          <motion.div
            initial={{ opacity: 0, y: 8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            role="dialog"
            aria-modal="true"
            aria-labelledby="library-confirm-title"
            aria-describedby="library-confirm-description"
            className="panel w-full max-w-md border border-white/[0.10] bg-[#090812]/95 p-5 shadow-2xl shadow-black/60"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="flex items-start gap-3">
              <div className={"grid size-10 shrink-0 place-items-center rounded-xl border " + (pendingAction.kind === "delete" ? "border-red-400/20 bg-red-400/10 text-red-300" : "border-[#d75b88]/20 bg-[#d75b88]/10 text-[#e68aae]")}>
                {pendingAction.kind === "delete" ? <Trash2 size={17} /> : <AlertTriangle size={17} />}
              </div>
              <div className="min-w-0">
                <h2 id="library-confirm-title" className="text-base font-medium text-white">{confirmation.title}</h2>
                <p id="library-confirm-description" className="mt-2 break-words text-sm leading-6 text-zinc-400">{confirmation.message}</p>
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button ref={cancelConfirmRef} type="button" onClick={() => setPendingAction(null)} className="subtle-button px-3 py-2 text-xs">
                Cancel
              </button>
              <button type="button" onClick={() => void confirmPendingAction()} className={"rounded-lg border px-3 py-2 text-xs transition-colors " + (pendingAction.kind === "delete" ? "border-red-400/25 bg-red-400/10 text-red-200 hover:bg-red-400/20" : "border-[#d75b88]/25 bg-[#d75b88]/10 text-[#f0b0c8] hover:bg-[#d75b88]/20")}>
                {confirmation.confirm}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </div>
  );
}
