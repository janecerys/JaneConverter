import { useState } from "react";
import { CheckCircle2, ExternalLink, HardDrive, RefreshCw, RotateCw } from "lucide-react";
import type { RuntimeInfo } from "../bridge";
import { bridge } from "../bridge";

export function SettingsView({ runtime, onStatus }: { runtime: RuntimeInfo | null; onStatus: (message: string) => void }) {
  const [checking, setChecking] = useState(false);
  const [relaunching, setRelaunching] = useState(false);
  const [message, setMessage] = useState("");

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
      <div><div className="mono-label">Runtime and updates</div><h1 className="mt-2 text-3xl font-semibold tracking-[-.04em] text-white">Keep control of the application.</h1><p className="mt-2 text-sm text-zinc-500">{runtime?.packaged ? "Running from a production package." : "Running from a source checkout."}</p></div>
      <section className="panel p-5"><div className="flex items-center gap-2 text-sm text-zinc-200"><HardDrive size={16} className="text-zinc-500" /> Runtime readiness</div><div className="mt-4 grid gap-2 md:grid-cols-2">{[["Python", runtime?.pythonReady, runtime?.pythonPath], ["FFmpeg", runtime?.ffmpegReady, "Required by conversion and media probing"], ["GPU", runtime?.gpuAvailable, runtime?.gpuLabel], ["Data root", true, runtime?.dataRoot]].map(([label, ready, detail]) => <div key={String(label)} className="rounded-xl border border-white/[0.06] bg-black/10 px-3 py-3"><div className="flex items-center gap-2 text-xs text-zinc-300">{ready ? <CheckCircle2 className="size-3.5 text-emerald-400" /> : <span className="size-3.5 rounded-full border border-amber-400/50" />}{label}</div><div className="mt-1 truncate font-mono text-[10px] text-zinc-700">{String(detail ?? "Checking...")}</div></div>)}</div></section>
      <section className="panel flex flex-wrap items-center justify-between gap-4 p-5"><div><div className="text-sm text-zinc-200">Relaunch JaneConverter</div><div className="mt-1 text-xs text-zinc-600">Close this window and start the current desktop application again.</div></div><button type="button" disabled={relaunching} onClick={() => void relaunch()} className="subtle-button flex items-center gap-2 px-4 py-2 text-xs disabled:cursor-wait disabled:opacity-60"><RotateCw className={"size-3.5 " + (relaunching ? "animate-spin" : "")} /> {relaunching ? "Relaunching..." : "Relaunch now"}</button></section>
      <section className="panel flex flex-wrap items-center justify-between gap-4 p-5"><div><div className="text-sm text-zinc-200">Check for updates</div><div className="mt-1 text-xs text-zinc-600">Checks the latest published JaneConverter release on GitHub and the extractor service. Nothing is installed silently.</div></div><button type="button" disabled={checking} onClick={() => void updates()} className="subtle-button flex items-center gap-2 px-4 py-2 text-xs"><RefreshCw className={`size-3.5 ${checking ? "animate-spin" : ""}`} /> {checking ? "Checking..." : "Check now"}</button></section>
      <div className={`rounded-lg border px-3 py-2 text-[11px] ${message ? "border-[#3b82f6]/15 bg-[#3b82f6]/[0.04] text-zinc-300" : "border-transparent text-zinc-600"}`} role="status" aria-live="polite">{message || "Update and relaunch results appear here."}</div>
      <div className="flex items-center gap-2 text-[11px] text-zinc-700"><ExternalLink size={12} /> {runtime?.packaged ? "Application data uses your OS user-data directory." : "Project-local storage is the default."} User-selected folders are always respected.</div>
    </div>
  );
}
