import { useEffect, useRef, useState } from "react";
import { AlertTriangle, ArrowRight, Check, Copy, FileAudio, FileImage, FileVideo, FolderOpen, HelpCircle, Inbox, RefreshCw, Trash2, X } from "lucide-react";
import type { AccessStatus, ConverterSettings, FetchedMedia } from "../bridge";
import { bridge } from "../bridge";

function formatBytes(size: number) {
  if (!size) return "0 B";
  if (size < 1024) return size + " B";
  if (size < 1024 * 1024) return (size / 1024).toFixed(1) + " KB";
  return (size / (1024 * 1024)).toFixed(1) + " MB";
}

function MediaIcon({ kind }: { kind: FetchedMedia["mediaKind"] }) {
  if (kind === "image") return <FileImage className="size-5 text-sky-300" />;
  if (kind === "audio") return <FileAudio className="size-5 text-emerald-300" />;
  return <FileVideo className="size-5 text-[#d75b88]" />;
}

function pathKey(value: string) {
  return value.replace(/\//g, "\\").replace(/\\+$/, "").toLowerCase();
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

function isInside(root: string, candidate: string) {
  const rootKey = pathKey(root);
  const candidateKey = pathKey(candidate);
  return candidateKey === rootKey || candidateKey.startsWith(rootKey + "\\");
}

export function FetchedMediaView({ access, settings, onSettings, onSelect, onDiscard, onStatus }: {
  access: AccessStatus;
  settings: ConverterSettings;
  onSettings: (next: ConverterSettings) => void;
  onSelect: (item: FetchedMedia) => void;
  onDiscard: (item: FetchedMedia) => void;
  onStatus: (message: string) => void;
}) {
  const [items, setItems] = useState<FetchedMedia[]>([]);
  const [thumbnails, setThumbnails] = useState<Record<string, string>>({});
  const [discarding, setDiscarding] = useState<string | null>(null);
  const [moving, setMoving] = useState(false);
  const [pendingMove, setPendingMove] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [showGuide, setShowGuide] = useState(false);
  const [copiedPath, setCopiedPath] = useState(false);
  const refreshInFlight = useRef(false);
  const mountedRef = useRef(true);
  const thumbnailPaths = useRef(new Set<string>());

  useEffect(() => {
    if (!pendingMove) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPendingMove(null);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [pendingMove]);

  const refresh = async (manual = false) => {
    if (refreshInFlight.current) return;
    refreshInFlight.current = true;
    if (manual) setRefreshing(true);
    try {
      const next = await bridge.fetchedMedia();
      if (!mountedRef.current) return;
      setItems(next);
      setThumbnails((current) => Object.fromEntries(
        Object.entries(current).filter(([path]) => next.some((item) => item.path === path)),
      ));
      for (const path of Array.from(thumbnailPaths.current)) {
        if (!next.some((item) => item.path === path)) thumbnailPaths.current.delete(path);
      }
      const pending = next.filter((item) => !thumbnailPaths.current.has(item.path));
      const previews = await Promise.all(pending.map(async (item) => {
        try {
          return [item.path, await bridge.fetchedMediaThumbnail(item.path)] as const;
        } catch (_) {
          return [item.path, null] as const;
        }
      }));
      if (mountedRef.current) {
        setThumbnails((current) => {
          const updated = { ...current };
          for (const [path, preview] of previews) {
            thumbnailPaths.current.add(path);
            if (preview) updated[path] = preview;
          }
          return updated;
        });
      }
    } catch (error) {
      if (mountedRef.current) onStatus(error instanceof Error ? error.message : String(error));
    } finally {
      refreshInFlight.current = false;
      if (mountedRef.current && manual) setRefreshing(false);
    }
  };

  useEffect(() => {
    mountedRef.current = true;
    void refresh();
    const timer = window.setInterval(() => { void refresh(); }, 1000);
    return () => { mountedRef.current = false; window.clearInterval(timer); };
  }, [access.active, access.captureCount]);

  async function chooseMoveFolder() {
    const destinationParent = await bridge.chooseFolder();
    if (!destinationParent) return;
    if (pathKey(destinationParent) === pathKey(parentPath(settings.fetchedDir))) {
      onStatus("Choose a different parent folder for the fetched media folder.");
      return;
    }
    if (isInside(settings.fetchedDir, destinationParent)) {
      onStatus("The new fetched media location cannot be inside the current folder.");
      return;
    }
    setPendingMove(destinationParent);
  }

  async function confirmMove() {
    const destinationParent = pendingMove;
    if (!destinationParent) return;
    setPendingMove(null);
    setMoving(true);
    try {
      const movedTo = await bridge.moveFetchedFolder(settings.fetchedDir, destinationParent);
      onSettings({ ...settings, fetchedDir: movedTo });
      onStatus("Fetched media folder moved to " + movedTo + ".");
    } catch (error) {
      onStatus(error instanceof Error ? error.message : String(error));
    } finally {
      setMoving(false);
    }
  }

  const discard = async (item: FetchedMedia) => {
    setDiscarding(item.path);
    try {
      await bridge.discardFetchedMedia(item.path);
      setItems((current) => current.filter((entry) => entry.path !== item.path));
      setThumbnails((current) => {
        const updated = { ...current };
        delete updated[item.path];
        return updated;
      });
      thumbnailPaths.current.delete(item.path);
      onDiscard(item);
      onStatus(item.name + " discarded.");
    } catch (error) {
      onStatus(error instanceof Error ? error.message : String(error));
    } finally {
      setDiscarding(null);
    }
  };

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="mono-label">BROWSER CAPTURE INBOX</div>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-white">Fetched media.</h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-zinc-500">Captured media is saved in the folder below. The browser session controls what can be fetched; the files remain here until you open, convert, or discard them.</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-zinc-500">
          <button
            type="button"
            onClick={() => setShowGuide(true)}
            className="subtle-button flex items-center gap-1.5 px-3 py-1.5 text-xs text-pink-300 border-[#c52b68]/30 hover:border-[#c52b68]/60"
            title="How to install and use the browser extension"
          >
            <HelpCircle className="size-3.5 text-[#d75b88]" />
            Extension guide
          </button>
          <button type="button" aria-label="Refresh fetched media" title="Refresh fetched media" disabled={refreshing} onClick={() => void refresh(true)} className="subtle-button grid size-7 place-items-center rounded-full disabled:cursor-wait disabled:opacity-60"><RefreshCw className={"size-3.5 " + (refreshing ? "animate-spin" : "")} /></button>
          {items.length + (access.active ? " item" : " saved item") + (items.length === 1 ? "" : "s")}
        </div>
      </div>

      <div className="panel p-5">
        <div className="flex items-start gap-3">
          <div className="grid size-10 shrink-0 place-items-center rounded-xl border border-[#c52b68]/25 bg-[#c52b68]/[0.08]"><Inbox className="size-5 text-[#d75b88]" /></div>
          <div>
            <div className="text-sm font-medium text-zinc-200">One confirmed session, many captures</div>
            <p className="mt-1 text-xs leading-relaxed text-zinc-600">JaneConverter stores only the media you explicitly capture. The selected folder is persistent, so clearing access ends the browser session without deleting these fetched files.</p>
          </div>
        </div>
      </div>

      <div className="panel p-5">
        <div className="flex items-center gap-2 text-sm font-medium text-zinc-200"><FolderOpen className="size-4 text-zinc-500" /> Fetched media folder</div>
        <p className="mt-2 text-xs leading-relaxed text-zinc-600">New browser captures are saved here instead of a disposable session folder. You can change this location at any time; new access sessions will use the selected folder.</p>
        <div className="mt-3 flex gap-2">
          <input aria-label="Fetched media folder" value={settings.fetchedDir} onChange={(event) => onSettings({ ...settings, fetchedDir: event.target.value })} className="field min-w-0 flex-1 px-3 py-2.5 text-sm" />
          <button type="button" className="subtle-button px-3 text-xs" onClick={async () => { const path = await bridge.chooseFolder(); if (path) onSettings({ ...settings, fetchedDir: path }); }}>Browse</button>
          <button type="button" className="subtle-button flex items-center gap-2 px-3 text-xs" onClick={() => void bridge.openPath(settings.fetchedDir)}><FolderOpen className="size-3.5" /> Open folder</button>
          <button type="button" disabled={moving || access.active} title={access.active ? "Clear browser access before moving this folder" : "Move the fetched media folder"} className="subtle-button flex items-center gap-2 px-3 text-xs disabled:cursor-not-allowed disabled:opacity-50" onClick={() => void chooseMoveFolder()}><FolderOpen className={"size-3.5 " + (moving ? "animate-pulse" : "")} /> {moving ? "Moving folder..." : "Move fetched folder"}</button>
        </div>
      </div>
      {!items.length ? (
        <div className="panel p-10 text-center text-sm text-zinc-500">{access.active ? "Your inbox is ready. Capture media from the active browser page and it will appear here automatically." : "No fetched media is saved yet. Create and confirm browser access from the Converter tab to begin."}</div>
      ) : (
        <div className="space-y-2">
          {items.map((item, index) => (
            <div key={item.path} className="panel flex flex-wrap items-center gap-4 p-4">
              <div className="grid size-16 shrink-0 place-items-center overflow-hidden rounded-xl border border-white/[0.08] bg-black/20">
                {thumbnails[item.path]
                  ? <img src={thumbnails[item.path]} alt={item.title || item.name} className="size-full object-cover" />
                  : <MediaIcon kind={item.mediaKind} />}
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm text-zinc-200">{item.title || item.name || ("Capture " + (index + 1))}</div>
                <div className="mt-1 truncate text-xs text-zinc-600">{item.name} · {item.mediaKind} · {formatBytes(item.size)} · {item.captureMode === "sequence" ? "Story sequence" : item.captureMode === "collect" ? "Collect mode" : item.captureMode === "network" ? "Network compatibility" : "Saved file"}</div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <button type="button" className="subtle-button px-3 py-2 text-xs" onClick={() => void bridge.openFile(item.path)}>Open file</button>
                <button type="button" className="subtle-button flex items-center gap-2 px-3 py-2 text-xs" onClick={() => void bridge.openPath(item.path)}><FolderOpen className="size-3.5" /> Open path</button>
                <button type="button" className="primary-button flex items-center gap-2 px-3 py-2 text-xs" onClick={() => onSelect(item)}>Use for conversion <ArrowRight className="size-3.5" /></button>
                <button type="button" className="subtle-button px-3 py-2 text-xs text-rose-300" aria-label={"Discard " + item.name} disabled={discarding === item.path} onClick={() => void discard(item)}>
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
      {pendingMove && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-6" role="presentation">
          <div className="panel w-full max-w-md p-5" role="dialog" aria-modal="true" aria-labelledby="fetched-folder-move-title" aria-describedby="fetched-folder-move-description">
            <div className="flex items-start gap-3">
              <div className="grid size-10 shrink-0 place-items-center rounded-xl border border-[#d75b88]/20 bg-[#d75b88]/10 text-[#e68aae]"><AlertTriangle size={17} /></div>
              <div>
                <h2 id="fetched-folder-move-title" className="text-base font-medium text-white">Move fetched media folder?</h2>
                <p id="fetched-folder-move-description" className="mt-2 break-words text-sm leading-6 text-zinc-400">Move this folder to {joinPath(pendingMove, baseName(settings.fetchedDir))}? New captures will use the new location.</p>
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" className="subtle-button px-3 py-2 text-xs" onClick={() => setPendingMove(null)}>Cancel</button>
              <button type="button" disabled={moving} className="primary-button px-3 py-2 text-xs disabled:cursor-wait disabled:opacity-60" onClick={() => void confirmMove()}>{moving ? "Moving..." : "Move folder"}</button>
            </div>
          </div>
        </div>
      )}
      {showGuide && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/65 p-6" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) setShowGuide(false); }}>
          <div className="panel relative w-full max-w-xl p-6" role="dialog" aria-modal="true" aria-labelledby="extension-guide-title">
            <button type="button" onClick={() => setShowGuide(false)} className="absolute right-4 top-4 grid size-8 place-items-center rounded-lg text-zinc-500 hover:bg-white/[0.06] hover:text-zinc-200" aria-label="Close guide"><X className="size-4" /></button>
            <div className="mono-label">AIR-GAPPED BROWSER BRIDGE</div>
            <h2 id="extension-guide-title" className="mt-2 text-xl font-semibold text-white">How to Install & Use the Browser Extension</h2>
            <p className="mt-2 text-xs leading-relaxed text-zinc-400">
              The JaneConverter Browser Bridge lets you capture media directly from your active browser tabs. It operates with strict air-gapped privacy: <strong>it never reads, exports, or shares cookies, passwords, or session tokens</strong>.
            </p>
            <div className="mt-4 space-y-3 text-xs leading-relaxed text-zinc-300">
              <div className="rounded-xl border border-white/[0.06] bg-black/25 p-3">
                <div className="font-semibold text-pink-300">1. Open Extension Management in Your Browser</div>
                <div className="mt-1 text-zinc-400">Works in Chrome, Microsoft Edge, Brave, Vivaldi, or Opera:</div>
                <div className="mt-1 font-mono text-[11px] text-zinc-300">chrome://extensions &nbsp;|&nbsp; edge://extensions &nbsp;|&nbsp; vivaldi://extensions</div>
              </div>
              <div className="rounded-xl border border-white/[0.06] bg-black/25 p-3">
                <div className="font-semibold text-pink-300">2. Turn On Developer Mode</div>
                <div className="mt-1 text-zinc-400">Toggle the <strong>Developer mode</strong> switch in the top-right corner of the extensions page.</div>
              </div>
              <div className="rounded-xl border border-white/[0.06] bg-black/25 p-3">
                <div className="font-semibold text-pink-300">3. Click "Load Unpacked"</div>
                <div className="mt-1 text-zinc-400">Click the <strong>Load unpacked</strong> button and select the <code className="rounded bg-white/10 px-1 py-0.5 font-mono text-zinc-200">browser-extension</code> directory in your JaneConverter root.</div>
                <div className="mt-2">
                  <button
                    type="button"
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText("browser-extension");
                        setCopiedPath(true);
                        setTimeout(() => setCopiedPath(false), 2000);
                        onStatus("Copied 'browser-extension' folder name to clipboard.");
                      } catch {}
                    }}
                    className="subtle-button flex items-center gap-1.5 px-3 py-1.5 text-[11px]"
                  >
                    {copiedPath ? <Check className="size-3 text-emerald-400" /> : <Copy className="size-3 text-zinc-400" />}
                    {copiedPath ? "Copied folder name" : "Copy folder name: browser-extension"}
                  </button>
                </div>
              </div>
              <div className="rounded-xl border border-white/[0.06] bg-black/25 p-3">
                <div className="font-semibold text-pink-300">4. Capture Media with Zero Cookie Leakage</div>
                <div className="mt-1 text-zinc-400">Navigate to your media page, click the JaneConverter extension icon, and select <strong>Capture current media</strong>. Raw binary bytes transfer directly into this Fetched Media inbox!</div>
              </div>
            </div>
            <div className="mt-5 flex justify-end">
              <button type="button" onClick={() => setShowGuide(false)} className="primary-button px-5 py-2 text-xs">Got it</button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
