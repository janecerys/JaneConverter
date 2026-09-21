import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowDown, Check, Clipboard, Filter, Layers, Play, Search, TerminalSquare, Trash2, X } from "lucide-react";
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
  const [filter, setFilter] = useState<"clean" | "all" | "failed" | "progress">("clean");
  const [searchQuery, setSearchQuery] = useState("");
  const [lineLimit, setLineLimit] = useState<number | null>(150);
  const [autoScroll, setAutoScroll] = useState(true);
  const [userHasScrolledUp, setUserHasScrolledUp] = useState(false);
  const logContainerRef = useRef<HTMLDivElement>(null);

  // 1. Process and collapse repetitive progress frames when in "clean" mode
  const processedEvents = useMemo(() => {
    let list: ConverterEvent[];
    if (filter === "failed") {
      list = events.filter((e) => e.kind === "failed");
    } else if (filter === "progress") {
      list = events.filter((e) => e.progress !== undefined || e.kind === "progress");
    } else if (filter === "all") {
      list = events;
    } else {
      // Default: "clean" mode - collapse consecutive progress updates in-place
      const collapsed: ConverterEvent[] = [];
      let lastWasProgress = false;
      for (const event of events) {
        const isProgress =
          event.kind === "progress" ||
          (event.progress !== undefined && event.kind === "status") ||
          event.message.includes("[download]") ||
          event.message.includes("Downloading stream:");
        if (isProgress) {
          if (lastWasProgress && collapsed.length > 0) {
            collapsed[collapsed.length - 1] = event;
          } else {
            collapsed.push(event);
            lastWasProgress = true;
          }
        } else {
          collapsed.push(event);
          lastWasProgress = false;
        }
      }
      list = collapsed;
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter((e) => e.message.toLowerCase().includes(q) || e.jobId.toLowerCase().includes(q));
    }

    return list;
  }, [events, filter, searchQuery]);

  // 2. Windowing buffer to prevent infinite scroll DOM bloat
  const totalProcessedCount = processedEvents.length;
  const isTruncated = lineLimit !== null && totalProcessedCount > lineLimit;
  const visibleEvents = useMemo(() => {
    if (!isTruncated || lineLimit === null) return processedEvents;
    return processedEvents.slice(-lineLimit);
  }, [processedEvents, isTruncated, lineLimit]);

  // Auto-scroll to bottom on new logs when autoScroll is active
  useEffect(() => {
    if (!autoScroll || userHasScrolledUp) return;
    const el = logContainerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [visibleEvents.length, autoScroll, userHasScrolledUp]);

  function handleScroll() {
    const el = logContainerRef.current;
    if (!el) return;
    const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    // If user scrolled up more than 36px from the bottom, pause auto-scroll
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
      await navigator.clipboard.writeText(processedEvents.map((event) => event.message).join("\n"));
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
            Real-time engine messages and conversion streams with smart progress collapsing.
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
              autoScroll && !userHasScrolledUp ? "border-[var(--accent-color,#c52b68)]/40 text-[var(--accent-color,#c52b68)]" : "text-zinc-500"
            }`}
            title={autoScroll ? "Auto-scroll is enabled" : "Auto-scroll is paused"}
          >
            <span
              className={`size-1.5 rounded-full ${
                autoScroll && !userHasScrolledUp ? "" : "bg-zinc-600"
              }`}
              style={autoScroll && !userHasScrolledUp ? { backgroundColor: "var(--accent-color, #c52b68)", boxShadow: "0 0 8px var(--accent-glow, rgba(197,43,104,0.6))" } : undefined}
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
        {/* Toolbar with Filter pills & Search input */}
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-white/[0.06] bg-black/20 px-4 py-2.5">
          <div className="flex items-center gap-1.5">
            <Filter size={13} className="mr-1 text-zinc-500" />
            {(
              [
                { key: "clean", label: "Clean" },
                { key: "all", label: "All (Raw)" },
                { key: "failed", label: "Errors" },
                { key: "progress", label: "Progress" },
              ] as const
            ).map(({ key, label }) => (
              <button
                key={key}
                type="button"
                onClick={() => setFilter(key)}
                className={`rounded-lg px-2.5 py-1 text-[11px] transition-colors ${
                  filter === key
                    ? "bg-white/[0.09] font-medium text-pink-300 shadow-sm"
                    : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            {/* Search Bar */}
            <div className="relative flex items-center">
              <Search size={11} className="pointer-events-none absolute left-2 text-zinc-500" />
              <input
                type="text"
                placeholder="Filter logs..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="field h-6 w-32 rounded-md bg-black/30 pl-6 pr-5 text-[11px] text-zinc-200 placeholder:text-zinc-600 focus:w-44 transition-all"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery("")}
                  className="absolute right-1 text-zinc-500 hover:text-zinc-300"
                >
                  <X size={10} />
                </button>
              )}
            </div>

            {/* Buffer Window Selector */}
            <button
              type="button"
              onClick={() => setLineLimit((curr) => (curr === null ? 150 : null))}
              className="subtle-button flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] text-zinc-400"
              title={lineLimit === null ? "Buffer limit is disabled (showing all)" : "Buffer is capped to latest 150 lines to prevent infinite scroll"}
            >
              <Layers size={10} />
              {lineLimit === null ? "Buffer: All" : `Buffer: 150`}
            </button>

            <span className="font-mono text-[10px] text-zinc-600">
              {visibleEvents.length} {visibleEvents.length === 1 ? "line" : "lines"}
            </span>
          </div>
        </div>

        {/* Truncation / Infinite Scroll Warning Banner */}
        {isTruncated && lineLimit !== null && (
          <div className="flex shrink-0 items-center justify-between border-b border-pink-500/15 bg-pink-950/20 px-4 py-1.5 text-[10.5px] text-pink-300/80">
            <span>
              Showing latest {lineLimit} of {totalProcessedCount} lines. Earlier output collapsed to prevent infinite scroll.
            </span>
            <button
              type="button"
              onClick={() => setLineLimit(null)}
              className="font-medium underline hover:text-pink-200"
            >
              Show all earlier lines
            </button>
          </div>
        )}

        {/* Log Entries Container */}
        <div
          ref={logContainerRef}
          onScroll={handleScroll}
          className="relative flex-1 min-h-0 overflow-y-auto bg-[#06050c] p-4 select-text font-mono"
        >
          {visibleEvents.length ? (
            <div className="space-y-0.5">
              {visibleEvents.map((event, index) => (
                <div
                  key={`${event.jobId}-${index}`}
                  className={`console-line border-b border-white/[0.02] py-0.5 text-[11px] leading-relaxed ${
                    event.kind === "failed"
                      ? "text-red-300 font-medium"
                      : event.kind === "finished"
                      ? "text-emerald-300 font-medium"
                      : ""
                  }`}
                >
                  {event.progress !== undefined && (
                    <span className="mr-2 inline-block rounded bg-white/[0.05] px-1 text-[10px] font-semibold text-pink-300">
                      {Math.round(event.progress * 100)}%
                    </span>
                  )}
                  {event.message.replace(/^\[\d+%\]\s*/, "")}
                </div>
              ))}
            </div>
          ) : (
            <div className="grid h-full place-items-center text-center text-xs text-zinc-600">
              <div>
                <TerminalSquare className="mx-auto mb-2 size-6 text-zinc-700" />
                {searchQuery
                  ? "No log entries match the search query."
                  : "Ready. Conversion logs and real-time engine output will appear here."}
              </div>
            </div>
          )}
        </div>

        {/* Floating Jump to Latest Button */}
        {userHasScrolledUp && visibleEvents.length > 0 && (
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
