import { useEffect, useMemo, useState } from "react";
import { Clipboard, FilePlus2, FolderOpen, Info, Link2, ListMusic, LockKeyhole, Play, RefreshCw, ShieldCheck, Square } from "lucide-react";
import { motion } from "framer-motion";
import type { AccessStatus, ConverterEvent, ConverterSettings, PlaylistCatalog, RuntimeInfo } from "../bridge";
import { bridge } from "../bridge";
import { formatsFor, qualitiesFor, resolutions, videoFormats } from "../options";
import { PlaylistDialog } from "./PlaylistDialog";

function SelectField({ label, value, values, onChange, disabled = false }: { label: string; value: string | number; values: Array<string | number>; onChange: (value: string) => void; disabled?: boolean }) {
  return (
    <label className="block min-w-0">
      <span className="mb-2 block text-[11px] font-medium text-zinc-500">{label}</span>
      <select disabled={disabled} value={value} onChange={(event) => onChange(event.target.value)} className="field w-full px-3 py-2.5 text-sm disabled:cursor-not-allowed disabled:opacity-50">
        {values.map((item) => <option key={item} value={item}>{String(item)}</option>)}
      </select>
    </label>
  );
}

function Toggle({ checked, onChange, label, hint }: { checked: boolean; onChange: (value: boolean) => void; label: string; hint?: string }) {
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-white/[0.06] bg-black/10 px-3 py-3 transition-colors hover:border-white/[0.12]">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="mt-0.5 size-4 accent-[#c52b68]" />
      <span className="min-w-0"><span className="block text-xs text-zinc-300">{label}</span>{hint && <span className="mt-1 block text-[10px] leading-relaxed text-zinc-600">{hint}</span>}</span>
    </label>
  );
}

export function ConverterView({
  settings,
  runtime,
  events,
  access,
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
  running: boolean;
  progress: number;
  status: string;
  onSettings: (next: ConverterSettings) => void;
  onStart: (source: string, playlistIndexes?: string) => Promise<void>;
  onCancel: () => Promise<void>;
  onCreateAccess: (source: string) => Promise<void>;
  onClearAccess: () => Promise<void>;
  onStatus: (message: string) => void;
}) {
  const [source, setSource] = useState("");
  const [playlist, setPlaylist] = useState<PlaylistCatalog | null>(null);
  const [loadingPlaylist, setLoadingPlaylist] = useState(false);
  const [notesOpen, setNotesOpen] = useState(false);
  const formats = useMemo(() => formatsFor(settings.category), [settings.category]);
  const qualities = useMemo(() => qualitiesFor(settings.format), [settings.format]);
  const isVideo = videoFormats.includes(settings.format);
  const lastEvent = events.length ? events[events.length - 1] : null;

  useEffect(() => {
    if (!formats.includes(settings.format)) onSettings({ ...settings, format: formats[0], bitrate: qualitiesFor(formats[0])[0] });
  }, [formats, settings, onSettings]);

  const update = (patch: Partial<ConverterSettings>) => onSettings({ ...settings, ...patch });

  async function paste() {
    try {
      const value = await navigator.clipboard.readText();
      setSource(value.trim());
      onStatus("Source pasted from clipboard.");
    } catch {
      onStatus("Clipboard access was unavailable. Paste directly into the source field.");
    }
  }

  async function browseFile() {
    const path = await bridge.chooseFile();
    if (path) { setSource(path); onStatus("Local media file selected."); }
  }

  async function browseOutput() {
    const path = await bridge.chooseFolder();
    if (path) update({ outputDir: path });
  }

  async function loadPlaylist() {
    if (!source.trim()) { onStatus("Paste a playlist or album URL first."); return; }
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

  async function convert(indexes?: string) {
    if (!source.trim()) { onStatus("Paste a source URL or choose a local file first."); return; }
    await onStart(source.trim(), indexes);
  }

  return (
    <div className="mx-auto max-w-[1180px] space-y-5 pb-10">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .35 }} className="flex items-end justify-between gap-5">
        <div>
          <div className="mono-label">Universal media studio</div>
          <h1 className="mt-2 text-3xl font-semibold tracking-[-.04em] text-white">Convert with less friction.</h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-zinc-500">Keep the source behavior you already trust, with a calmer workspace around it.</p>
        </div>
        <div className="hidden rounded-full border border-white/[0.07] bg-white/[0.025] px-3 py-2 text-[11px] text-zinc-500 md:block">
          <span className={`mr-2 inline-block size-1.5 rounded-full ${runtime?.pythonReady ? "bg-emerald-400" : "bg-amber-400"}`} />
          {runtime?.pythonReady ? "Python engine ready" : "Engine setup required"}
        </div>
      </motion.div>

      <section className="panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><div className="text-sm font-medium text-zinc-200">Source media</div><div className="mt-1 text-xs text-zinc-600">Paste a public URL or choose a local file.</div></div>
          <span className="text-[11px] text-zinc-600">{source ? "Source provided" : "Ready for URL or path"}</span>
        </div>
        <div className="mt-4 flex gap-2">
          <input aria-label="Source media URL or local path" value={source} onChange={(event) => setSource(event.target.value)} placeholder="YouTube, Spotify, Apple Music, SoundCloud, TikTok, X, or a local path..." className="field min-w-0 flex-1 px-3.5 py-3 text-sm placeholder:text-zinc-700" />
          <button type="button" onClick={() => void paste()} className="subtle-button flex items-center gap-2 px-3 text-xs"><Clipboard className="size-3.5" /> Paste</button>
          <button type="button" onClick={() => void browseFile()} className="subtle-button flex items-center gap-2 px-3 text-xs"><FilePlus2 className="size-3.5" /> Browse</button>
          <button type="button" disabled={loadingPlaylist || running} onClick={() => void loadPlaylist()} className="subtle-button flex items-center gap-2 px-3 text-xs disabled:opacity-50"><ListMusic className="size-3.5" /> {loadingPlaylist ? "Loading..." : "Playlist tracks"}</button>
        </div>

        <div className="mt-5 border-t border-white/[0.06] pt-4">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-xs text-zinc-400"><LockKeyhole className="size-3.5 text-zinc-600" /> Optional account access <span className="text-zinc-700">- session only</span></div>
            <span className={`text-[11px] ${access.browser ? "text-emerald-400" : "text-zinc-600"}`}>{access.browser ? `Connected through ${access.browser}` : "Public-only extraction"}</span>
          </div>
          <p className="mt-2 max-w-3xl text-[11px] leading-relaxed text-zinc-600">Create a temporary local link and open it in the browser whose session you want to use. JaneConverter never asks for or stores your password or cookies.</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {access.link && <button type="button" onClick={() => void navigator.clipboard.writeText(access.link)} className="subtle-button flex items-center gap-2 px-3 py-2 text-xs"><Link2 className="size-3.5" /> Copy link</button>}
            {access.link && <button type="button" onClick={() => void bridge.openUrl(access.link)} className="subtle-button px-3 py-2 text-xs">Open link</button>}
            {access.active ? <button type="button" onClick={() => void onClearAccess()} className="subtle-button px-3 py-2 text-xs">Clear access</button> : <button type="button" onClick={() => void onCreateAccess(source)} className="subtle-button flex items-center gap-2 px-3 py-2 text-xs"><ShieldCheck className="size-3.5" /> Create access link</button>}
            {access.link && <span className="max-w-[420px] truncate text-[11px] text-zinc-700">{access.link}</span>}
          </div>
        </div>

        <button type="button" onClick={() => setNotesOpen((value) => !value)} className="mt-4 flex items-center gap-2 text-xs text-zinc-500 transition-colors hover:text-zinc-300"><Info className="size-3.5" /> Source notes and common failures <span className="text-zinc-700">{notesOpen ? "Hide" : "Show"}</span></button>
        {notesOpen && <div className="mt-3 grid gap-3 rounded-xl border border-white/[0.06] bg-black/15 p-4 text-[11px] leading-relaxed text-zinc-500 md:grid-cols-3">
          <div><div className="mb-1 text-zinc-300">Apple Music</div>Public catalog links provide metadata and artwork, not a normal downloadable subscription stream. Region restrictions, removed tracks, music videos, alternate versions, and missing public matches can fail. Direct song links with a track selector work best.</div>
          <div><div className="mb-1 text-zinc-300">Spotify</div>Spotify provides metadata; JaneConverter searches supported public sources for a matching stream. Private, deleted, region-locked, or mismatched tracks can fail.</div>
          <div><div className="mb-1 text-zinc-300">Other sources and files</div>Age gates, login walls, bot checks, rate limits, provider changes, unreadable local files, FFmpeg availability, permissions, and free disk space can affect conversion. Console has the exact detail.</div>
        </div>}
      </section>

      <section className="panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><div className="text-sm font-medium text-zinc-200">Output and transcode parameters</div><div className="mt-1 text-xs text-zinc-600">Every legacy format and quality control remains available.</div></div>
          <div className="flex items-center gap-1 rounded-xl border border-white/[0.07] bg-black/15 p-1">
            {(["Music", "Video", "Miscellaneous"] as const).map((category) => <button key={category} type="button" onClick={() => update({ category })} className={`rounded-lg px-3 py-1.5 text-[11px] transition-colors ${settings.category === category ? "bg-white/[0.09] text-white" : "text-zinc-600 hover:text-zinc-300"}`}>{category}</button>)}
          </div>
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-3">
          <SelectField label="Container format" value={settings.format} values={formats} onChange={(format) => update({ format, bitrate: qualitiesFor(format)[0] })} />
          <SelectField label={isVideo ? "Video quality" : "Audio bitrate / quality"} value={settings.bitrate} values={qualities} onChange={(bitrate) => update({ bitrate })} />
          <SelectField label="Video resolution" value={settings.resolution} values={resolutions} onChange={(resolution) => update({ resolution })} disabled={!isVideo} />
        </div>
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <SelectField label="Audio sample rate" value={settings.sampleRate} values={[44100, 48000, 96000]} onChange={(sampleRate) => update({ sampleRate: Number(sampleRate) })} disabled={isVideo} />
          <div className="md:col-span-2 flex items-end text-[11px] leading-relaxed text-zinc-600">Use the quality menu for WAV/FLAC bit depth, OGG quality, or video quality. The selected values are sent directly to the existing Python engine.</div>
        </div>
        <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
          <Toggle checked={settings.normalize} onChange={(normalize) => update({ normalize })} label="EBU R128 normalization" hint="-14 LUFS streaming target" />
          <Toggle checked={settings.useGpu} onChange={(useGpu) => update({ useGpu })} label="Hardware acceleration" hint={runtime?.gpuAvailable ? runtime.gpuLabel : "CPU mode available"} />
          <Toggle checked={settings.saveCover} onChange={(saveCover) => update({ saveCover })} label="Embed and save cover art" hint="Artwork / thumbnail where available" />
          <Toggle checked={settings.saveMetadata} onChange={(saveMetadata) => update({ saveMetadata })} label="Export metadata and credits" hint="Human-readable .txt metadata" />
        </div>
      </section>

      <section className="panel p-5">
        <div className="flex items-center gap-2 text-sm font-medium text-zinc-200"><FolderOpen className="size-4 text-zinc-500" /> Export folder</div>
        <div className="mt-3 flex gap-2">
          <input aria-label="Export folder" value={settings.outputDir} onChange={(event) => update({ outputDir: event.target.value })} className="field min-w-0 flex-1 px-3 py-2.5 text-sm" />
          <button type="button" onClick={() => void browseOutput()} className="subtle-button px-3 text-xs">Browse</button>
          <button type="button" onClick={() => void bridge.openPath(settings.outputDir)} className="subtle-button flex items-center gap-2 px-3 text-xs"><FolderOpen className="size-3.5" /> Open folder</button>
        </div>
        <div className="mt-2 text-[11px] text-zinc-700">Default: project-local converted media. Choose another folder when you explicitly want exports elsewhere.</div>
      </section>

      <section className="panel overflow-hidden p-5">
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" disabled={running} onClick={() => void convert()} className="primary-button flex min-h-11 flex-1 items-center justify-center gap-2 px-5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"><Play className="size-4" /> {running ? "Conversion running" : "Convert media"}</button>
          {running && <button type="button" onClick={() => void onCancel()} className="danger-button flex min-h-11 items-center gap-2 px-4 text-sm"><Square className="size-3.5" /> Abort</button>}
        </div>
        <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-white/[0.06]"><motion.div className="h-full rounded-full bg-[#c52b68]" animate={{ width: `${Math.round(progress * 100)}%` }} transition={{ ease: "easeOut", duration: .25 }} /></div>
        <div className="mt-3 flex items-center justify-between gap-3 text-xs">
          <span className={`truncate ${running ? "text-zinc-300" : "text-zinc-500"}`}>{status || "Ready. Paste a link or choose a file to begin."}</span>
          <span className="shrink-0 font-mono text-zinc-700">{Math.round(progress * 100)}%</span>
        </div>
        {lastEvent && <div className="mt-3 flex items-center gap-2 text-[11px] text-zinc-700"><RefreshCw className={`size-3 ${running ? "animate-spin" : ""}`} /> Latest engine message: {lastEvent.message}</div>}
      </section>

      {playlist && <PlaylistDialog catalog={playlist} onClose={() => setPlaylist(null)} onConfirm={(indexes) => { setPlaylist(null); void convert(indexes); }} />}
      {loadingPlaylist && <div className="fixed inset-0 z-40 grid place-items-center bg-black/45 backdrop-blur-sm"><div className="panel flex items-center gap-3 px-5 py-4 text-sm text-zinc-300"><RefreshCw className="size-4 animate-spin text-zinc-500" /> Reading playlist catalog...</div></div>}
    </div>
  );
}
