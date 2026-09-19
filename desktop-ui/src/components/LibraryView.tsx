import { useEffect, useState } from "react";
import { ArrowLeft, FileAudio, Folder, FolderOpen, RefreshCw, Trash2, Video } from "lucide-react";
import { motion } from "framer-motion";
import type { ConverterSettings, LibraryEntry } from "../bridge";
import { bridge } from "../bridge";

function size(value: number) {
  return value < 1024 * 1024 ? `${Math.round(value / 1024)} KB` : `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function LibraryView({ settings, onStatus }: { settings: ConverterSettings; onStatus: (message: string) => void }) {
  const [root, setRoot] = useState(settings.outputDir);
  const [entries, setEntries] = useState<LibraryEntry[]>([]);
  const [loading, setLoading] = useState(false);

  async function refresh(path = root) {
    setLoading(true);
    try { setEntries(await bridge.scanLibrary(path)); }
    catch (error) { onStatus(error instanceof Error ? error.message : String(error)); }
    finally { setLoading(false); }
  }

  useEffect(() => { setRoot(settings.outputDir); void refresh(settings.outputDir); }, [settings.outputDir]);

  async function remove(entry: LibraryEntry) {
    if (!window.confirm(`Delete ${entry.name}? This cannot be undone.`)) return;
    try { await bridge.deleteLibraryEntry(root, entry.path); onStatus(`${entry.name} deleted.`); await refresh(); }
    catch (error) { onStatus(error instanceof Error ? error.message : String(error)); }
  }

  return (
    <div className="mx-auto max-w-[1180px] space-y-5 pb-10">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex flex-wrap items-end justify-between gap-4">
        <div><div className="mono-label">Project library</div><h1 className="mt-2 text-3xl font-semibold tracking-[-.04em] text-white">Converted media.</h1><p className="mt-2 text-sm text-zinc-500">Browse the organized folders produced by the existing engine.</p></div>
        <button type="button" onClick={() => void refresh()} className="subtle-button flex items-center gap-2 px-3 py-2 text-xs"><RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh</button>
      </motion.div>
      <section className="panel p-4">
        <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-500">
          <button type="button" onClick={() => { const parent = root.replace(/[\\/][^\\/]+$/, ""); if (parent && parent !== root) { setRoot(parent); void refresh(parent); } }} className="subtle-button flex items-center gap-2 px-3 py-2"><ArrowLeft className="size-3.5" /> Back</button>
          <span className="truncate font-mono text-[11px] text-zinc-700">{root}</span>
        </div>
      </section>
      <section className="space-y-2">
        {!entries.length && <div className="panel py-14 text-center text-sm text-zinc-600">{loading ? "Scanning converted media..." : "No converted media found in this folder."}</div>}
        {entries.slice(0, 500).map((entry) => <motion.div key={entry.path} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="panel flex flex-wrap items-center gap-3 px-4 py-3">
          <div className="grid size-9 shrink-0 place-items-center rounded-xl border border-white/[0.07] bg-black/15 text-zinc-500">{entry.isDirectory ? <Folder className={entry.isPlaylist ? "text-[#d75b88]" : ""} size={16} /> : (entry.extension === "MP4" || entry.extension === "MKV" || entry.extension === "WEBM" || entry.extension === "MOV" || entry.extension === "GIF" ? <Video size={16} /> : <FileAudio size={16} />)}</div>
          <div className="min-w-0 flex-1"><div className="truncate text-sm text-zinc-300">{entry.name}</div><div className="mt-1 text-[11px] text-zinc-600">{entry.isDirectory ? `${entry.mediaCount} media item${entry.mediaCount === 1 ? "" : "s"} - ${size(entry.totalBytes)}` : `${entry.extension} - ${size(entry.totalBytes)}`}{entry.isPlaylist ? " - playlist" : ""}</div></div>
          {entry.isDirectory ? <button type="button" onClick={() => { setRoot(entry.path); void refresh(entry.path); }} className="subtle-button flex items-center gap-2 px-3 py-2 text-xs"><FolderOpen className="size-3.5" /> Open</button> : <button type="button" onClick={() => void bridge.openPath(entry.path)} className="subtle-button px-3 py-2 text-xs">Show file</button>}
          <button type="button" onClick={() => void remove(entry)} className="grid size-8 place-items-center rounded-lg text-zinc-600 transition-colors hover:bg-red-500/10 hover:text-red-300" aria-label={`Delete ${entry.name}`}><Trash2 size={14} /></button>
        </motion.div>)}
        {entries.length > 500 && <div className="text-center text-[11px] text-zinc-700">Showing the first 500 items to keep the library responsive.</div>}
      </section>
    </div>
  );
}
