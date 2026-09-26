import { Activity, Cpu, FileAudio, FolderOpen, Inbox, PanelLeftClose, PanelLeftOpen, Settings2, TerminalSquare } from "lucide-react";
import { motion } from "framer-motion";
import { useState } from "react";

export type ViewKey = "converter" | "fetched" | "library" | "hardware" | "console" | "settings";

const items: Array<{ key: ViewKey; label: string; icon: typeof FileAudio }> = [
  { key: "converter", label: "Converter", icon: FileAudio },
  { key: "fetched", label: "Fetched media.", icon: Inbox },
  { key: "library", label: "Converted library", icon: FolderOpen },
  { key: "hardware", label: "Hardware & Pipeline", icon: Cpu },
  { key: "console", label: "Console", icon: TerminalSquare },
  { key: "settings", label: "Settings", icon: Settings2 },
];

const SIDEBAR_COLLAPSED_KEY = "janecoverter.sidebar.collapsed";

function readCollapsedPreference() {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true";
  } catch {
    return false;
  }
}

export function Sidebar({ activeView, onChange }: { activeView: ViewKey; onChange: (view: ViewKey) => void }) {
  const [collapsed, setCollapsed] = useState(readCollapsedPreference);

  function toggleCollapsed() {
    setCollapsed((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next));
      } catch {
        // The layout remains usable when browser storage is unavailable.
      }
      return next;
    });
  }

  return (
    <motion.aside
      data-collapsed={collapsed}
      animate={{ width: collapsed ? 76 : 232 }}
      transition={{ type: "spring", stiffness: 420, damping: 38 }}
      className="flex shrink-0 flex-col overflow-hidden border-r border-white/[0.06] bg-[#05040d]/85 px-4 py-5 backdrop-blur-xl"
    >
      <div className={["flex min-h-9 items-center gap-3", collapsed ? "justify-center" : "justify-start"].join(" ")}>
        <div className="grid size-9 shrink-0 place-items-center rounded-xl border border-white/10 bg-[#11101b] shadow-[0_8px_24px_rgba(0,0,0,.28)]">
          <span
            className="size-2 rounded-full"
            style={{ backgroundColor: "var(--accent-color, #c52b68)", boxShadow: "0 0 14px var(--accent-glow, rgba(197,43,104,.55))" }}
          />
        </div>
        {!collapsed && <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold tracking-tight text-white">JaneConverter</div>
          <div className="mono-label mt-1">LOCAL / STUDIO</div>
        </div>}
      </div>

      {!collapsed && <div className="mono-label mt-12 px-3">Workspace</div>}
      <nav className="mt-3 space-y-1" aria-label="Primary">
        {items.map(({ key, label, icon: Icon }) => {
          const active = activeView === key;
          return (
            <button
              key={key}
              type="button"
              aria-current={active ? "page" : undefined}
              aria-label={label}
              title={collapsed ? label : undefined}
              onClick={() => onChange(key)}
              className={["group relative flex w-full items-center rounded-xl py-2.5 text-left text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#3b82f6]", collapsed ? "justify-center px-2" : "gap-3 px-3", active ? "text-white" : "text-zinc-500 hover:bg-white/[0.035] hover:text-zinc-200"].join(" ")}
            >
              {active && (
                <motion.span
                  layoutId="active-nav"
                  className="absolute inset-0 rounded-xl border bg-white/[0.045]"
                  style={{ borderColor: "var(--accent-glow, rgba(197,43,104,0.35))" }}
                  transition={{ type: "spring", stiffness: 420, damping: 34 }}
                />
              )}
              <Icon
                className={["relative z-10 size-4", active ? "" : "text-zinc-600 group-hover:text-zinc-300"].join(" ")}
                style={active ? { color: "var(--accent-color, #d75b88)" } : undefined}
                strokeWidth={1.8}
              />
              {!collapsed && <span className="relative z-10 truncate">{label}</span>}
            </button>
          );
        })}
        <div className="mt-2 border-t border-white/[0.06] pt-2">
          <button
            type="button"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={!collapsed}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            onClick={toggleCollapsed}
            className={["group flex w-full items-center rounded-xl py-2.5 text-left text-sm text-zinc-500 transition-colors hover:bg-white/[0.035] hover:text-zinc-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#3b82f6]", collapsed ? "justify-center px-2" : "gap-3 px-3"].join(" ")}
          >
            {collapsed ? <PanelLeftOpen className="size-4 text-zinc-600 group-hover:text-zinc-300" /> : <PanelLeftClose className="size-4 text-zinc-600 group-hover:text-zinc-300" />}
            {!collapsed && <span>Collapse sidebar</span>}
          </button>
        </div>
      </nav>

      {!collapsed && <div className="mt-4 rounded-2xl border border-white/[0.07] bg-white/[0.025] p-3">
        <div className="flex items-center gap-2 text-xs text-zinc-300"><Activity className="size-3.5 text-zinc-500" /> Project-local workspace</div>
        <p className="mt-2 text-[11px] leading-relaxed text-zinc-600">Media, temporary files, settings, and logs stay beside JaneConverter whenever possible.</p>
      </div>}
    </motion.aside>
  );
}
