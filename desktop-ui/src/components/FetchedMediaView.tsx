import { useEffect, useRef, useState } from "react";
import { ArrowRight, FileAudio, FileImage, FileVideo, FolderOpen, Inbox, LoaderCircle, RefreshCw, Trash2 } from "lucide-react";
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
  const [loading, setLoading] = useState(false);
  const thumbnailPaths = useRef(new Set<string>());

  useEffect(() => {
    let mounted = true;
    const refresh = async () => {
      setLoading(true);
      try {
        const next = await bridge.fetchedMedia();
        if (!mounted) return;
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
        if (mounted) {
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
        if (mounted) onStatus(error instanceof Error ? error.message : String(error));
      } finally {
        if (mounted) setLoading(false);
      }
    };
    void refresh();
    const timer = window.setInterval(() => { void refresh(); }, 1000);
    return () => { mounted = false; window.clearInterval(timer); };
  }, [access.active, access.captureCount]);

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
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-white">Fetched Media</h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-zinc-500">Captured media is saved in the folder below. The browser session controls what can be fetched; the files remain here until you open, convert, or discard them.</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-zinc-500">
          {loading && <LoaderCircle className="size-3.5 animate-spin" />}
          <RefreshCw className="size-3.5" />
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
    </section>
  );
}
