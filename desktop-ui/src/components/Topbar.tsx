import { useEffect, useState } from "react";
import { CircleHelp, Cpu, HardDrive, X } from "lucide-react";
import type { RuntimeInfo } from "../bridge";

export function Topbar({ runtime }: { runtime: RuntimeInfo | null }) {
  const [helpOpen, setHelpOpen] = useState(false);


  useEffect(() => {
    if (!helpOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setHelpOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [helpOpen]);

  return (
    <>
      <header className="flex h-16 shrink-0 items-center justify-end border-b border-white/[0.06] px-8">
        <div className="flex items-center gap-2">
          <div className="hidden items-center gap-2 rounded-full border border-white/[0.07] bg-white/[0.025] px-3 py-1.5 text-[11px] text-zinc-500 xl:flex">
            <span className={`size-1.5 rounded-full ${runtime?.mode === "tauri" ? "bg-emerald-400" : "bg-amber-400"}`} />
            {runtime?.mode === "tauri" ? "Native shell connected" : "Preview mode"}
          </div>
          {runtime && <div className="hidden items-center gap-2 rounded-full border border-white/[0.07] bg-white/[0.025] px-3 py-1.5 text-[11px] text-zinc-500 lg:flex"><HardDrive className="size-3.5" /> {runtime.ffmpegReady ? "FFmpeg ready" : "FFmpeg missing"}</div>}
          {runtime && <div className="hidden items-center gap-2 rounded-full border border-white/[0.07] bg-white/[0.025] px-3 py-1.5 text-[11px] text-zinc-500 lg:flex"><Cpu className="size-3.5" /> {runtime.gpuAvailable ? runtime.gpuLabel : "CPU mode"}</div>}
          <button type="button" onClick={() => setHelpOpen(true)} className="grid size-8 place-items-center rounded-lg text-zinc-600 transition-colors hover:bg-white/[0.05] hover:text-zinc-200 focus-visible:outline-2 focus-visible:outline-[#3b82f6]" aria-label="JaneConverter help" aria-expanded={helpOpen} title="Open JaneConverter help"><CircleHelp className="size-4" /></button>
        </div>
      </header>
      {helpOpen && <div className="fixed inset-0 z-50 grid place-items-center bg-black/55 p-6" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setHelpOpen(false); }}>
        <section className="panel relative w-full max-w-lg p-6" role="dialog" aria-modal="true" aria-labelledby="janeconverter-help-title">
          <button type="button" onClick={() => setHelpOpen(false)} className="absolute right-4 top-4 grid size-8 place-items-center rounded-lg text-zinc-500 hover:bg-white/[0.06] hover:text-zinc-200" aria-label="Close help"><X className="size-4" /></button>
          <div className="mono-label">Quick guide</div>
          <h2 id="janeconverter-help-title" className="mt-2 text-xl font-semibold text-white">Using JaneConverter</h2>
          <div className="mt-4 space-y-3 text-xs leading-relaxed text-zinc-500">
            <p><span className="text-zinc-200">Convert:</span> paste a supported public link or choose a local media file, select your output settings, then start the conversion.</p>
            <p><span className="text-zinc-200">Need details?</span> Open Live console to see extraction, FFmpeg, and failure messages.</p>
            <p><span className="text-zinc-200">Switch interfaces:</span> Settings lets you choose Main UI, Legacy Rust, or Legacy Python for the next launch.</p>
            <p><span className="text-zinc-200">Where are files?</span> Converted media uses the project-local <code className="font-mono text-zinc-300">converted</code> folder unless you choose another export folder.</p>
          </div>
          <button type="button" onClick={() => setHelpOpen(false)} className="subtle-button mt-5 px-3 py-2 text-xs">Close</button>
        </section>
      </div>}
    </>
  );
}