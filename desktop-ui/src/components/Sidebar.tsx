import { Activity, FileAudio, FolderOpen, Settings2, TerminalSquare } from "lucide-react";
import { motion } from "framer-motion";

export type ViewKey = "converter" | "library" | "console" | "settings";

const items: Array<{ key: ViewKey; label: string; icon: typeof FileAudio }> = [
  { key: "converter", label: "Converter", icon: FileAudio },
  { key: "library", label: "Converted library", icon: FolderOpen },
  { key: "console", label: "Console", icon: TerminalSquare },
  { key: "settings", label: "Settings", icon: Settings2 },
];

export function Sidebar({ activeView, onChange }: { activeView: ViewKey; onChange: (view: ViewKey) => void }) {
  return (
    <aside className="flex w-[232px] shrink-0 flex-col border-r border-white/[0.06] bg-[#05040d]/85 px-4 py-5 backdrop-blur-xl">
      <div className="flex items-center gap-3 px-3">
        <div className="grid size-9 place-items-center rounded-xl border border-white/10 bg-[#11101b] shadow-[0_8px_24px_rgba(0,0,0,.28)]">
          <span className="size-2 rounded-full bg-[#c52b68] shadow-[0_0_14px_rgba(197,43,104,.55)]" />
        </div>
        <div>
          <div className="text-sm font-semibold tracking-tight text-white">JaneConverter</div>
          <div className="mono-label mt-1">LOCAL / STUDIO</div>
        </div>
      </div>

      <div className="mono-label mt-12 px-3">Workspace</div>
      <nav className="mt-3 space-y-1" aria-label="Primary">
        {items.map(({ key, label, icon: Icon }) => {
          const active = activeView === key;
          return (
            <button
              key={key}
              type="button"
              aria-current={active ? "page" : undefined}
              onClick={() => onChange(key)}
              className={`group relative flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#3b82f6] ${active ? "text-white" : "text-zinc-500 hover:bg-white/[0.035] hover:text-zinc-200"}`}
            >
              {active && <motion.span layoutId="active-nav" className="absolute inset-0 rounded-xl border border-[#c52b68]/35 bg-white/[0.045]" transition={{ type: "spring", stiffness: 420, damping: 34 }} />}
              <Icon className={`relative z-10 size-4 ${active ? "text-[#d75b88]" : "text-zinc-600 group-hover:text-zinc-300"}`} strokeWidth={1.8} />
              <span className="relative z-10">{label}</span>
            </button>
          );
        })}
      </nav>

      <div className="mt-auto rounded-2xl border border-white/[0.07] bg-white/[0.025] p-3">
        <div className="flex items-center gap-2 text-xs text-zinc-300"><Activity className="size-3.5 text-zinc-500" /> Project-local workspace</div>
        <p className="mt-2 text-[11px] leading-relaxed text-zinc-600">Media, temporary files, settings, and logs stay beside JaneConverter whenever possible.</p>
      </div>
    </aside>
  );
}
