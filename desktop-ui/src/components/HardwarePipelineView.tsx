import { Activity, Cpu, MemoryStick, MonitorCog, Thermometer } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { bridge, type ConverterSettings, type HardwareSnapshot, type RuntimeInfo } from "../bridge";

const PIPELINE_STAGES = [
  { label: "Input & validation", threshold: 0.05, detail: "Check the pasted link or selected local media file" },
  { label: "Source discovery", threshold: 0.15, detail: "Identify the provider and available media streams" },
  { label: "Download & extraction", threshold: 0.68, detail: "Fetch media or public photo collections into local staging" },
  { label: "Convert or preserve", threshold: 0.9, detail: "Apply the selected output format and quality settings" },
  { label: "Metadata & organization", threshold: 0.98, detail: "Write requested metadata and prepare the export folder" },
  { label: "Save to library", threshold: 1, detail: "Place completed media in the converted library" },
] as const;

function Meter({
  label,
  value,
  detail,
  color = "blue",
}: {
  label: string;
  value: number;
  detail: string;
  color?: "blue" | "pink" | "green";
}) {
  const fill = color === "pink" ? "bg-[var(--accent-color)]" : color === "green" ? "bg-emerald-500" : "bg-blue-500";
  const width = Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-3 text-[10px]">
        <span className="text-zinc-500">{label}</span>
        <span className="font-mono text-zinc-500">{detail}</span>
      </div>
      <div
        className="h-1.5 overflow-hidden rounded-full bg-white/[0.06]"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(width)}
      >
        <div className={`h-full rounded-full transition-[width] duration-500 ${fill}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function MetricCard({ icon: Icon, label, value }: { icon: typeof Cpu; label: string; value: string }) {
  return (
    <div className="panel-raised flex min-w-0 items-center gap-3 p-4">
      <Icon size={17} className="shrink-0 text-[var(--accent-color)]" />
      <span className="truncate text-[11px] text-zinc-500">
        {label}<strong className="ml-1 text-white">{value}</strong>
      </span>
    </div>
  );
}

export function HardwarePipelineView({
  runtime,
  settings,
  active,
  progress,
  progressMessage,
}: {
  runtime: RuntimeInfo | null;
  settings: ConverterSettings;
  active: boolean;
  progress: number;
  progressMessage: string;
}) {
  const [snapshot, setSnapshot] = useState<HardwareSnapshot | null>(null);
  const [snapshotError, setSnapshotError] = useState("");
  const requestInFlight = useRef(false);

  useEffect(() => {
    let mounted = true;
    const sample = async () => {
      if (requestInFlight.current) return;
      requestInFlight.current = true;
      try {
        const next = await bridge.hardwareSnapshot();
        if (mounted) {
          setSnapshot(next);
          setSnapshotError("");
        }
      } catch (error) {
        if (mounted) setSnapshotError(error instanceof Error ? error.message : String(error));
      } finally {
        requestInFlight.current = false;
      }
    };
    void sample();
    const timer = window.setInterval(() => void sample(), 2800);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, []);

  const current = snapshot;
  const finished = !active && progress >= 1;
  const stopped = !active && progress > 0 && progress < 1;
  const gpuTelemetry = current?.telemetrySource === "nvidia-smi";
  const accelerator = settings.useGpu
    ? runtime?.gpuAvailable ? runtime.gpuLabel : "No supported GPU encoder detected; CPU mode is available"
    : runtime?.gpuAvailable ? "GPU available, disabled in current settings" : "CPU multi-core mode";
  const outputPath = settings.outputDir || "—";
  const fetchedPath = settings.fetchedDir || "—";

  return (
    <section className="muted-scroll min-h-full overflow-y-auto">
      <header className="mb-6">
        <p className="eyebrow">System insight</p>
        <h1 className="page-title">Hardware &amp; Pipeline</h1>
        <p className="page-subtitle">Local hardware telemetry and JaneConverter’s media processing stages.</p>
      </header>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,.85fr)_minmax(0,1.15fr)]">
        <section className="panel p-5" aria-labelledby="detected-hardware-title">
          <div className="mb-5 flex items-center gap-3">
            <div className="grid size-10 place-items-center rounded-lg border border-blue-400/20 bg-blue-400/[0.06] text-blue-400">
              <MonitorCog size={19} />
            </div>
            <div>
              <h2 id="detected-hardware-title" className="section-title">Detected hardware</h2>
              <p className="hint">Names and specifications are read locally from this computer.</p>
            </div>
          </div>

          <div className="space-y-3">
            <div className="rounded-lg border border-white/[0.07] bg-black/[0.12] p-3">
              <div className="field-label">Processor</div>
              <div className="mt-1 text-[13px] text-white">{current?.cpuName || "Detecting processor…"}</div>
              <div className="mt-1 text-[10px] text-zinc-500">{current?.logicalCores || "—"} logical cores</div>
            </div>
            <div className="rounded-lg border border-white/[0.07] bg-black/[0.12] p-3">
              <div className="field-label">Accelerator</div>
              <div className="mt-1 text-[13px] text-white">{accelerator}</div>
              <div className="mt-1 text-[10px] text-zinc-500">{current?.gpuName && current.gpuName !== "Not available" ? current.gpuName : runtime?.gpuLabel || "GPU not detected"}</div>
            </div>
            <div className="rounded-lg border border-white/[0.07] bg-black/[0.12] p-3">
              <div className="field-label">Runtime paths</div>
              <div className="mt-2 space-y-1 break-all font-mono text-[10px] leading-5 text-zinc-500">
                <div>Project: {runtime?.projectRoot || "—"}</div>
                <div>Data: {runtime?.dataRoot || "—"}</div>
                <div>Converted library: {outputPath}</div>
                <div>Fetched media: {fetchedPath}</div>
                <div>Python engine: {runtime?.pythonPath || "—"}</div>
                <div>FFmpeg: {runtime?.ffmpegPath || "—"}</div>
              </div>
            </div>
          </div>
        </section>

        <section className="panel p-5" aria-labelledby="hardware-monitor-title">
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 id="hardware-monitor-title" className="section-title">Live hardware monitor</h2>
              <p className="hint">Refreshes while this tab is open and includes conversion workers.</p>
            </div>
            <div className={`flex items-center gap-2 text-[10px] uppercase tracking-[.1em] ${active ? "text-amber-400" : "text-emerald-400"}`}>
              <span className="size-1.5 rounded-full bg-current" />
              {active ? "Conversion active" : current ? "Monitoring idle system" : "Connecting"}
            </div>
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            <div className="space-y-4">
              <Meter label="System CPU" value={current?.cpuSystemPct || 0} detail={current ? `${current.cpuSystemPct.toFixed(1)}%` : "—"} />
              <Meter label="JaneConverter CPU" value={current?.cpuAppPct || 0} detail={current ? `${current.cpuAppPct.toFixed(1)}%` : "—"} color="pink" />
              <Meter label="System RAM" value={current?.ramSystemPct || 0} detail={current ? `${current.ramUsedGb.toFixed(1)} / ${current.ramTotalGb.toFixed(1)} GB` : "—"} />
            </div>
            <div className="space-y-4">
              <Meter label="GPU utilization" value={current?.gpuSystemPct || 0} detail={gpuTelemetry ? `${current.gpuSystemPct.toFixed(1)}%` : "Unavailable"} color="green" />
              <Meter label="VRAM" value={gpuTelemetry && current.gpuVramTotalMb ? current.gpuVramUsedMb / current.gpuVramTotalMb * 100 : 0} detail={gpuTelemetry ? `${current.gpuVramUsedMb} / ${current.gpuVramTotalMb} MB` : "Unavailable"} />
              <div className="flex items-center gap-2 text-[10px] text-zinc-500">
                <Thermometer size={13} />
                GPU temperature: {current?.gpuTempC == null ? "Unavailable" : `${current.gpuTempC}°C`} · source: {current?.telemetrySource || "pending"}
              </div>
            </div>
          </div>
          {snapshotError && <p role="status" className="mt-4 text-[10px] text-amber-300">Live telemetry unavailable: {snapshotError}</p>}
        </section>
      </div>

      <section className="panel mt-4 p-5" aria-labelledby="pipeline-tracker-title">
        <div className="mb-4 flex items-end justify-between gap-4">
          <div>
            <h2 id="pipeline-tracker-title" className="section-title">Conversion pipeline tracker</h2>
            <p className="hint">{active ? progressMessage : finished ? "The latest conversion completed." : stopped ? progressMessage : "Waiting for a conversion request."}</p>
          </div>
          <div className="font-mono text-[11px] text-amber-300">{`${Math.round(Math.max(0, Math.min(1, progress)) * 100)}`.padStart(3, "0")}%</div>
        </div>
        <ol className="space-y-2">
          {PIPELINE_STAGES.map((stage, index) => {
            const previousThreshold = PIPELINE_STAGES[index - 1]?.threshold || 0;
            const complete = finished || (active && progress >= stage.threshold);
            const currentStage = active && progress >= previousThreshold && progress < stage.threshold;
            const stoppedStage = stopped && progress >= previousThreshold && progress < stage.threshold;
            const stateLabel = complete ? "Complete" : currentStage ? "Active" : stoppedStage ? "Stopped" : "Waiting";
            const stateColor = complete ? "text-emerald-400" : currentStage ? "text-blue-300" : stoppedStage ? "text-rose-400" : "text-zinc-600";
            const rowColor = currentStage ? "border-blue-400/30 bg-blue-400/[0.04]" : "border-white/[0.06] bg-black/[0.1]";
            return (
              <li key={stage.label} className={`flex items-center gap-3 rounded-lg border px-3 py-3 ${rowColor}`}>
                <span className={`grid size-5 shrink-0 place-items-center rounded-full border text-[9px] ${complete ? "border-emerald-400 text-emerald-400" : currentStage ? "border-blue-300 text-blue-300" : stoppedStage ? "border-rose-400 text-rose-400" : "border-white/[0.12] text-zinc-600"}`}>
                  {complete ? "✓" : index + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-[11px] font-semibold text-white">{stage.label}</div>
                  <div className="mt-0.5 text-[10px] text-zinc-600">{stage.detail}</div>
                </div>
                <span className={`shrink-0 text-[9px] uppercase tracking-[.1em] ${stateColor}`}>{stateLabel}</span>
              </li>
            );
          })}
        </ol>
      </section>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <MetricCard icon={Cpu} label="JaneConverter memory" value={current ? `${current.ramAppMb.toFixed(0)} MB` : "—"} />
        <MetricCard icon={MemoryStick} label="App VRAM" value={gpuTelemetry ? `${current.gpuAppVramMb} MB` : "Unavailable"} />
        <MetricCard icon={Activity} label="Telemetry source" value={current?.telemetrySource || "Connecting"} />
      </div>
    </section>
  );
}
