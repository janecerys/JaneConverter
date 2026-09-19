import { useEffect, useState } from "react";
import { CheckCircle2, ExternalLink, HardDrive, RefreshCw, RotateCw, Terminal } from "lucide-react";
import type { FrontendPreference, RuntimeInfo } from "../bridge";
import { bridge } from "../bridge";

export function SettingsView({ runtime, onStatus }: { runtime: RuntimeInfo | null; onStatus: (message: string) => void }) {
  const [checking, setChecking] = useState(false);
  const [relaunching, setRelaunching] = useState(false);
  const [message, setMessage] = useState("");
  const [selected, setSelected] = useState<FrontendPreference>(runtime?.frontendPreference ?? "tauri");

  useEffect(() => {
    if (runtime?.frontendPreference) setSelected(runtime.frontendPreference);
  }, [runtime?.frontendPreference]);

  async function preference(value: FrontendPreference) {
    try {
      await bridge.setFrontendPreference(value);
      setSelected(value);
      const label = value === "tauri" ? "Main UI" : value === "rust" ? "Legacy Rust" : "Legacy Python";
      const nextMessage = `${label} is saved for the next launch.`;
      setMessage(nextMessage);
      onStatus(nextMessage);
    } catch (error) {
      const nextMessage = error instanceof Error ? error.message : String(error);
      setMessage(nextMessage);
      onStatus(nextMessage);
    }
  }

  async function relaunch() {
    setRelaunching(true);
    setMessage("Relaunching JaneConverter...");
    try {
      await bridge.relaunch();
    } catch (error) {
      const nextMessage = error instanceof Error ? error.message : String(error);
      setRelaunching(false);
      setMessage(nextMessage);
      onStatus(nextMessage);
    }
  }

  async function updates() {
    setChecking(true);
    setMessage("Checking for updates...");
    try {
      const nextMessage = await bridge.checkUpdates();
      setMessage(nextMessage);
      onStatus(nextMessage);
    } catch (error) {
      const nextMessage = error instanceof Error ? error.message : String(error);
      setMessage(nextMessage);
      onStatus(nextMessage);
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="mx-auto max-w-[980px] space-y-5 pb-10">
      <div><div className="mono-label">Runtime and preferences</div><h1 className="mt-2 text-3xl font-semibold tracking-[-.04em] text-white">Keep control of the surface.</h1><p className="mt-2 text-sm text-zinc-500">The Main UI is the default, but the older launchers remain one selection away.</p></div>
      <section className="panel p-5"><div className="flex items-center gap-2 text-sm text-zinc-200"><HardDrive size={16} className="text-zinc-500" /> Runtime readiness</div><div className="mt-4 grid gap-2 md:grid-cols-2">{[["Python", runtime?.pythonReady, runtime?.pythonPath], ["FFmpeg", runtime?.ffmpegReady, "Required by conversion and media probing"], ["GPU", runtime?.gpuAvailable, runtime?.gpuLabel], ["Data root", true, runtime?.dataRoot]].map(([label, ready, detail]) => <div key={String(label)} className="rounded-xl border border-white/[0.06] bg-black/10 px-3 py-3"><div className="flex items-center gap-2 text-xs text-zinc-300">{ready ? <CheckCircle2 className="size-3.5 text-emerald-400" /> : <span className="size-3.5 rounded-full border border-amber-400/50" />}{label}</div><div className="mt-1 truncate font-mono text-[10px] text-zinc-700">{String(detail ?? "Checking...")}</div></div>)}</div></section>
            <section className="panel p-5">
        <div className="flex items-center gap-2 text-sm text-zinc-200"><Terminal size={16} className="text-zinc-500" /> Launch preference</div>
        <p className="mt-2 text-xs leading-relaxed text-zinc-600">Choose which interface JaneConverter.exe opens next time. Your choice is saved beside the launcher; the legacy Python launcher remains available.</p>
        <div className="mt-4 grid gap-2 md:grid-cols-3">
          {([['tauri', 'Main UI', 'Tauri + React interface'], ['rust', 'Legacy Rust', 'Existing native egui interface'], ['python', 'Legacy Python', 'Existing CustomTkinter interface']] as const).map(([value, label, detail]) => (
            <button key={value} type="button" onClick={() => void preference(value)} aria-pressed={selected === value} className={`rounded-xl border p-3 text-left transition-colors ${selected === value ? "border-[#c52b68]/45 bg-[#c52b68]/[0.08]" : "border-white/[0.07] bg-black/10 hover:border-white/[0.14]"}`}>
              <div className="text-xs text-zinc-200">{label}</div>
              <div className="mt-1 text-[11px] text-zinc-600">{detail}</div>
            </button>
          ))}
        </div>
        <div className={`mt-3 rounded-lg border px-3 py-2 text-[11px] ${message ? "border-[#3b82f6]/15 bg-[#3b82f6]/[0.04] text-zinc-300" : "border-transparent text-zinc-600"}`} role="status" aria-live="polite">{message || 'Select an interface to save the next-launch preference.'}</div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/[0.06] bg-black/10 px-3 py-3">
          <div>
            <div className="text-xs text-zinc-300">Apply interface preference</div>
            <div className="mt-1 text-[11px] text-zinc-600">Relaunch JaneConverter to open the selected interface now.</div>
          </div>
          <button type="button" disabled={relaunching} onClick={() => void relaunch()} className="subtle-button flex items-center gap-2 px-3 py-2 text-xs disabled:cursor-wait disabled:opacity-60">
            <RotateCw className={"size-3.5 " + (relaunching ? "animate-spin" : "")} /> {relaunching ? "Relaunching..." : "Relaunch now"}
          </button>
        </div>      </section>
      <section className="panel flex flex-wrap items-center justify-between gap-4 p-5"><div><div className="text-sm text-zinc-200">Check for updates</div><div className="mt-1 text-xs text-zinc-600">Checks the existing read-only application and extractor update services.</div></div><button type="button" disabled={checking} onClick={() => void updates()} className="subtle-button flex items-center gap-2 px-4 py-2 text-xs"><RefreshCw className={`size-3.5 ${checking ? "animate-spin" : ""}`} /> {checking ? "Checking..." : "Check now"}</button></section>
      <div className="flex items-center gap-2 text-[11px] text-zinc-700"><ExternalLink size={12} /> Project-local storage is the default. User-selected folders are always respected.</div>
    </div>
  );
}
