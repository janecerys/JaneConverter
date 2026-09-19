import { useMemo, useState } from "react";
import { Clipboard, Filter, Trash2 } from "lucide-react";
import type { ConverterEvent } from "../bridge";

export function ConsoleView({ events, onClear, onStatus }: { events: ConverterEvent[]; onClear: () => void; onStatus: (message: string) => void }) {
  const [filter, setFilter] = useState<"all" | "progress" | "failed">("all");
  const visible = useMemo(() => events.filter((event) => filter === "all" || (filter === "progress" ? event.progress !== undefined : event.kind === "failed")), [events, filter]);
  async function copy() {
    try { await navigator.clipboard.writeText(events.map((event) => event.message).join("\n")); onStatus("Console copied to clipboard."); }
    catch { onStatus("Could not copy the console."); }
  }
  return (
    <div className="mx-auto flex min-h-[calc(100vh-7rem)] max-w-[1180px] flex-col gap-5 pb-10">
      <div className="flex flex-wrap items-end justify-between gap-4"><div><div className="mono-label">Diagnostics</div><h1 className="mt-2 text-3xl font-semibold tracking-[-.04em] text-white">Live console.</h1><p className="mt-2 text-sm text-zinc-500">Conversion details stay visible without forcing an external terminal window.</p></div><div className="flex gap-2"><button type="button" onClick={() => void copy()} className="subtle-button flex items-center gap-2 px-3 py-2 text-xs"><Clipboard size={14} /> Copy logs</button><button type="button" onClick={onClear} className="subtle-button flex items-center gap-2 px-3 py-2 text-xs"><Trash2 size={14} /> Clear</button></div></div>
      <section className="panel flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b border-white/[0.06] px-4 py-3"><Filter size={14} className="text-zinc-600" />{(["all", "progress", "failed"] as const).map((value) => <button key={value} type="button" onClick={() => setFilter(value)} className={`rounded-lg px-3 py-1.5 text-[11px] ${filter === value ? "bg-white/[0.08] text-zinc-200" : "text-zinc-600 hover:text-zinc-300"}`}>{value}</button>)}<span className="ml-auto font-mono text-[10px] text-zinc-700">{visible.length} lines</span></div>
        <div className="min-h-[420px] flex-1 overflow-y-auto bg-[#06050c] p-4">{visible.length ? visible.map((event, index) => <div key={`${event.jobId}-${index}`} className={`console-line border-b border-white/[0.025] py-1 ${event.kind === "failed" ? "text-red-300" : event.kind === "finished" ? "text-emerald-300" : ""}`}>{event.progress !== undefined && <span className="mr-2 text-zinc-700">[{Math.round(event.progress * 100)}%]</span>}{event.message}</div>) : <div className="console-line text-zinc-700">Ready - conversion output will appear here.</div>}</div>
      </section>
    </div>
  );
}
