import { useMemo, useState } from "react";
import { Check, ListMusic, Search, X } from "lucide-react";
import type { PlaylistCatalog } from "../bridge";

export function PlaylistDialog({ catalog, onClose, onConfirm }: { catalog: PlaylistCatalog; onClose: () => void; onConfirm: (indexes: string) => void }) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Set<number>>(() => new Set(catalog.items.map((item) => item.index)));
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return catalog.items;
    return catalog.items.filter((item) => `${item.title} ${item.artist}`.toLowerCase().includes(needle));
  }, [catalog.items, query]);

  function toggle(index: number) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(index)) next.delete(index); else next.add(index);
      return next;
    });
  }

  function invert() {
    setSelected((current) => {
      const next = new Set(current);
      catalog.items.forEach((item) => next.has(item.index) ? next.delete(item.index) : next.add(item.index));
      return next;
    });
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-6 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label="Playlist track selector">
      <div className="panel flex max-h-[82vh] w-full max-w-3xl flex-col overflow-hidden bg-[#090812] shadow-2xl shadow-black/50">
        <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-4">
          <div className="flex items-center gap-3"><div className="grid size-9 place-items-center rounded-xl border border-white/[0.08] bg-white/[0.03]"><ListMusic className="size-4 text-[#d75b88]" /></div><div><div className="text-sm font-medium text-white">{catalog.title}</div><div className="mt-1 text-[11px] text-zinc-600">{selected.size} of {catalog.items.length} tracks selected</div></div></div>
          <button type="button" onClick={onClose} className="grid size-8 place-items-center rounded-lg text-zinc-600 hover:bg-white/[0.05] hover:text-zinc-200" aria-label="Close playlist selector"><X className="size-4" /></button>
        </div>
        <div className="flex flex-wrap gap-2 border-b border-white/[0.06] px-5 py-3">
          <div className="relative min-w-[220px] flex-1"><Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-zinc-600" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter tracks..." className="field w-full py-2 pl-9 pr-3 text-xs" /></div>
          <button type="button" onClick={() => setSelected(new Set(catalog.items.map((item) => item.index)))} className="subtle-button px-3 py-2 text-xs">Select all</button>
          <button type="button" onClick={() => setSelected(new Set())} className="subtle-button px-3 py-2 text-xs">Deselect</button>
          <button type="button" onClick={invert} className="subtle-button px-3 py-2 text-xs">Invert</button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-3">
          {visible.map((item) => <label key={item.index} className="flex cursor-pointer items-center gap-3 border-b border-white/[0.04] py-3 text-xs hover:bg-white/[0.02]"><input type="checkbox" checked={selected.has(item.index)} onChange={() => toggle(item.index)} className="size-4 accent-[#c52b68]" /><span className="w-8 font-mono text-[10px] text-zinc-700">{item.index}</span><span className="min-w-0 flex-1 truncate text-zinc-300">{item.title}<span className="ml-2 text-zinc-600">{item.artist}</span></span><span className="font-mono text-[10px] text-zinc-600">{item.duration}</span>{selected.has(item.index) && <Check className="size-3.5 text-emerald-400" />}</label>)}
          {!visible.length && <div className="py-10 text-center text-xs text-zinc-600">No tracks match this filter.</div>}
        </div>
        <div className="flex items-center justify-between border-t border-white/[0.06] px-5 py-4">
          <button type="button" onClick={onClose} className="subtle-button px-4 py-2 text-xs">Cancel</button>
          <button type="button" disabled={!selected.size} onClick={() => onConfirm(Array.from(selected).sort((a, b) => a - b).join(","))} className="primary-button px-4 py-2 text-xs disabled:opacity-40">Convert selected tracks</button>
        </div>
      </div>
    </div>
  );
}
