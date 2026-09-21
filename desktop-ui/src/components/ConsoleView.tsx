import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowDown, Check, Clipboard, Filter, Play, TerminalSquare, Trash2 } from "lucide-react";
import type { ConverterEvent } from "../bridge";

export function ConsoleView({
  events,
  onClear,
  onStatus,
}: {
  events: ConverterEvent[];
  onClear: () => void;
  onStatus: (message: string) => void;
}) {
  const [filter, setFilter] = useState<"all" | "progress" | "failed">("all");
  const [autoScroll, setAutoScroll] = useState(true);
  const [userHasScrolledUp, setUserHasScrolledUp] = useState(false);
  const logContainerRef = useRef<HTMLDivElement>(null);

  const visible = useMemo(
    () =>
      events.filter(
        (event) =>
          filter === "all" ||
          (filter === "progress" ? event.progress !== undefined : event.kind === "failed")
      ),
    [events, filter]
  );

  // Auto-scroll to bottom on new logs when autoScroll is active
  useEffect(() => {
    if (!autoScroll || userHasScrolledUp) return;
    const el = logContainerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [visible.length, autoScroll, userHasScrolledUp]);

  function handleScroll() {
    const el = logContainerRef.current;
    if (!el) return;
    const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    // If user is more than 36px from the bottom, pause auto-scroll
    const scrolledUp = distanceToBottom > 36;
    setUserHasScrolledUp(scrolledUp);
    if (!scrolledUp && !autoScroll) {
      setAutoScroll(true);
    }
  }

  function scrollToBottom() {
    const el = logContainerRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
    setUserHasScrolledUp(false);
    setAutoScroll(true);
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(events.map((event) => event.message).join("\n"));
      onStatus("Console copied to clipboard.");
    } catch {
      onStatus("Could not copy the console.");
    }
  }

  return (
    <div className="mx-auto flex h-full w-full max-w-[1180px] flex-1 flex-col gap-4 min-h-0">
      {/* Header */}
      <div className="flex shrink-0 flex-wrap items-end justify-between gap-4">
        <div>
          <div className="mono-label">Diagnostics</div>
          <h1 className="mt-1 text-2xl font-semibold tracking-[-.04em] text-white">Live console.</h1>
          <p className="mt-1 text-xs text-zinc-500">
            Real-time engine messages and conversion streams without forcing an external terminal.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              const next = !autoScroll;
              setAutoScroll(next);
              if (next) scrollToBottom();
            }}
            className={`subtle-button flex items-center gap-1.5 px-3 py-1.5 text-xs transition-colors ${
              autoScroll && !userHasScrolledUp ? "border-[#c52b68]/40 text-pink-300" : "text-zinc-500"
            }`}
            title={autoScroll ? "Auto-scroll is enabled" : "Auto-scroll is paused"}
          >
            <span
              className={`size-1.5 rounded-full ${
                autoScroll && !userHasScrolledUp ? "bg-[#c52b68] shadow-[0_0_8px_rgba(197,43,104,0.6)]" : "bg-zinc-600"
              }`}
            />
            {autoScroll && !userHasScrolledUp ? "Auto-scroll: On" : "Auto-scroll: Paused"}
          </button>
          <button
            type="button"
            onClick={() => void copy()}
            className="subtle-button flex items-center gap-1.5 px-3 py-1.5 text-xs"
          >
            <Clipboard size={13} /> Copy logs
          </button>
          <button
            type="button"
            onClick={onClear}
            className="subtle-button flex items-center gap-1.5 px-3 py-1.5 text-xs"
          >
            <Trash2 size={13} /> Clear
          </button>
        </div>
      </div>

      {/* Main Terminal Box */}
      <section className="panel relative flex flex-1 min-h-0 flex-col overflow-hidden shadow-2xl">
        {/* Toolbar */}
        <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-white/[0.06] bg-black/15 px-4 py-2.5">
          <Filter size={13} className="text-zinc-500" />
          {(["all", "progress", "failed"] as const).map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => setFilter(value)}
              className={`rounded-lg px-2.5 py-1 text-[11px] capitalize transition-colors ${
                filter === value
                  ? "bg-white/[0.09] font-medium text-zinc-100 shadow-sm"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {value}
            </button>
          ))}
          <span className="ml-auto font-mono text-[10px] text-zinc-600">
            {visible.length} line{visible.length === 1 ? "" : "s"}
          </span>
        </div>

        {/* Log Entries Container */}
        <div
          ref={logContainerRef}
          onScroll={handleScroll}
          className="relative flex-1 min-h-0 overflow-y-auto bg-[#06050c] p-4 select-text font-mono"
        >
          {visible.length ? (
            <div className="space-y-1">
              {visible.map((event, index) => (
                <div
                  key={`${event.jobId}-${index}`}
                  className={`console-line border-b border-white/[0.02] py-0.5 text-[11.5px] ${
                    event.kind === "failed"
                      ? "text-red-300 font-medium"
                      : event.kind === "finished"
                      ? "text-emerald-300 font-medium"
                      : ""
                  }`}
                >
                  {event.progress !== undefined && (
                    <span className="mr-2 inline-block rounded bg-white/[0.04] px-1 text-[10px] font-semibold text-zinc-400">
                      {Math.round(event.progress * 100)}%
                    </span>
                  )}
                  {event.message}
                </div>
              ))}
            </div>
          ) : (
            <div className="grid h-full place-items-center text-center text-xs text-zinc-600">
              <div>
                <TerminalSquare className="mx-auto mb-2 size-6 text-zinc-700" />
                Ready. Conversion logs and real-time engine output will appear here.
              </div>
            </div>
          )}
        </div>

        {/* Floating Jump to Latest Button */}
        {userHasScrolledUp && visible.length > 0 && (
          <div className="pointer-events-none absolute bottom-4 right-4 z-10">
            <button
              type="button"
              onClick={scrollToBottom}
              className="pointer-events-auto flex items-center gap-1.5 rounded-full border border-[#c52b68]/50 bg-[#160613]/95 px-3 py-1.5 text-[11px] font-medium text-pink-300 shadow-lg shadow-black/60 backdrop-blur transition-all hover:scale-105 hover:bg-[#20081c]"
            >
              <ArrowDown size={12} className="animate-bounce" /> Jump to latest
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
