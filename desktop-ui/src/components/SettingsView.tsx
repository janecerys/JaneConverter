import { useEffect, useState } from "react";
import { CheckCircle2, ExternalLink, FolderOpen, HardDrive, Paintbrush, Palette, Pipette, RefreshCw, RotateCcw, RotateCw } from "lucide-react";
import type { RuntimeInfo, UpdateCheckResult } from "../bridge";
import { bridge } from "../bridge";

const ACCENT_PRESETS = [
  { name: "Hot Pink (Default)", hex: "#c52b68" },
  { name: "Neon Rose", hex: "#f43f5e" },
  { name: "Electric Purple", hex: "#8b5cf6" },
  { name: "Cyber Cyan", hex: "#06b6d4" },
  { name: "Sky Blue", hex: "#3b82f6" },
  { name: "Emerald Green", hex: "#10b981" },
  { name: "Amber Gold", hex: "#f59e0b" },
  { name: "Sunset Coral", hex: "#f97316" },
];

const BG_PRESETS = [
  { name: "Void Black (Default)", hex: "#02000a" },
  { name: "Deep Obsidian", hex: "#09090b" },
  { name: "Midnight Navy", hex: "#0b0f17" },
  { name: "Abyssal Plum", hex: "#12071a" },
  { name: "Rosy Pearl (Light)", hex: "#fdf7fa" },
  { name: "Pure White", hex: "#ffffff" },
  { name: "Soft Zinc", hex: "#f4f4f5" },
  { name: "Warm Cream", hex: "#faf8f5" },
];

export function SettingsView({
  runtime,
  accentColor = "#c52b68",
  bgColor = "#02000a",
  onAccentColorChange,
  onBgColorChange,
  onResetColors,
  onStatus,
}: {
  runtime: RuntimeInfo | null;
  accentColor?: string;
  bgColor?: string;
  onAccentColorChange?: (color: string) => void;
  onBgColorChange?: (color: string) => void;
  onResetColors?: () => void;
  onStatus: (message: string) => void;
}) {
  const [checking, setChecking] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [updateResult, setUpdateResult] = useState<UpdateCheckResult | null>(null);
  const [updateDismissed, setUpdateDismissed] = useState(false);
  const [relaunching, setRelaunching] = useState(false);
  const [message, setMessage] = useState("");
  const [dataRootPath, setDataRootPath] = useState(runtime?.dataRoot ?? "");
  const [changingDataRoot, setChangingDataRoot] = useState(false);

  useEffect(() => {
    setDataRootPath(runtime?.dataRoot ?? "");
  }, [runtime?.dataRoot]);

  async function chooseDataRoot() {
    const path = await bridge.chooseFolder();
    if (path) setDataRootPath(path);
  }

  async function changeDataRoot() {
    const path = dataRootPath.trim();
    if (!path) {
      const nextMessage = "Choose a data root folder first.";
      setMessage(nextMessage);
      onStatus(nextMessage);
      return;
    }
    setChangingDataRoot(true);
    setMessage("Saving the data root and relaunching JaneConverter...");
    try {
      const saved = await bridge.setDataRoot(path);
      await bridge.relaunch();
      setMessage("Data root changed to " + saved + ".");
      onStatus("Data root changed to " + saved + ".");
    } catch (error) {
      const nextMessage = error instanceof Error ? error.message : String(error);
      setMessage(nextMessage);
      onStatus(nextMessage);
    } finally {
      setChangingDataRoot(false);
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
      const result = await bridge.checkUpdates();
      setUpdateResult(result);
      setUpdateDismissed(false);
      setMessage(result.message);
      onStatus(result.message);
    } catch (error) {
      const nextMessage = error instanceof Error ? error.message : String(error);
      setMessage(nextMessage);
      onStatus(nextMessage);
    } finally {
      setChecking(false);
    }
  }

  async function installUpdate() {
    const repo = updateResult?.repo;
    if (!repo?.has_update || !repo.installer_available || !repo.installer_url || !repo.installer_checksum_url || !repo.latest_version) {
      const nextMessage = "This update cannot be installed automatically here. Open the published release to update manually.";
      setMessage(nextMessage);
      onStatus(nextMessage);
      return;
    }
    setInstalling(true);
    const nextMessage = `Downloading and verifying JaneConverter v${repo.latest_version}...`;
    setMessage(nextMessage);
    onStatus(nextMessage);
    try {
      await bridge.installUpdate({
        installerUrl: repo.installer_url,
        checksumUrl: repo.installer_checksum_url,
        version: repo.latest_version,
      });
      setMessage("The update is ready. JaneConverter will close and reopen to finish installing it.");
      onStatus("The JaneConverter update is being installed.");
    } catch (error) {
      const failure = error instanceof Error ? error.message : String(error);
      setMessage(`The update could not be installed: ${failure}`);
      onStatus(`The update could not be installed: ${failure}`);
    } finally {
      setInstalling(false);
    }
  }

  return (
    <div className="mx-auto max-w-[980px] space-y-5 pb-10">
      <div><div className="mono-label">Runtime and updates</div><h1 className="mt-2 text-3xl font-semibold tracking-[-.04em] text-white">Keep control of the application.</h1><p className="mt-2 text-sm text-zinc-500">{runtime?.packaged ? "Running from a production package." : "Running from a source checkout."}</p></div>
      <section className="panel p-5"><div className="flex items-center gap-2 text-sm text-zinc-200"><HardDrive size={16} className="text-zinc-500" /> Runtime readiness</div><div className="mt-4 grid gap-2 md:grid-cols-2">{[["Python", runtime?.pythonReady, runtime?.pythonPath], ["FFmpeg", runtime?.ffmpegReady, runtime?.ffmpegPath || "Required by conversion and media probing"], ["GPU", runtime?.gpuAvailable, runtime?.gpuLabel], ["Data root", true, runtime?.dataRoot]].map(([label, ready, detail]) => <div key={String(label)} className="rounded-xl border border-white/[0.06] bg-black/10 px-3 py-3"><div className="flex items-center gap-2 text-xs text-zinc-300">{ready ? <CheckCircle2 className="size-3.5 text-emerald-400" /> : <span className="size-3.5 rounded-full border border-amber-400/50" />}{label}</div><div className="mt-1 truncate font-mono text-[10px] text-zinc-700">{String(detail ?? "Checking...")}</div></div>)}</div></section>
      <section className="panel p-5">
        <div className="flex items-center gap-2 text-sm text-zinc-200"><FolderOpen size={16} className="text-zinc-500" /> Application data folder</div>
        <p className="mt-2 text-xs leading-relaxed text-zinc-600">Choose where JaneConverter keeps its settings, fetched media, and converted-library defaults. Existing files stay where they are; the application will relaunch after you apply the new location.</p>
        <div className="mt-3 flex gap-2">
          <input aria-label="Application data folder" value={dataRootPath} onChange={(event) => setDataRootPath(event.target.value)} className="field min-w-0 flex-1 px-3 py-2.5 text-sm" />
          <button type="button" className="subtle-button px-3 text-xs" onClick={() => void chooseDataRoot()}>Browse</button>
          <button type="button" disabled={changingDataRoot} className="primary-button flex items-center gap-2 px-3 text-xs disabled:cursor-wait disabled:opacity-60" onClick={() => void changeDataRoot()}><FolderOpen className={"size-3.5 " + (changingDataRoot ? "animate-pulse" : "")} /> {changingDataRoot ? "Applying..." : "Apply and relaunch"}</button>
        </div>
      </section>

      {/* Interface Theme & Custom Color Suite */}
      <section className="panel p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-sm font-medium text-zinc-200">
              <Palette size={16} style={{ color: "var(--accent-color, #c52b68)" }} />
              Interface Theme & Color Palette
            </div>
            <div className="mt-1 text-xs text-zinc-500">
              Personalize JaneConverter in real-time. Pick custom accent & background colors or choose preset styles.
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => {
                onResetColors?.();
                onStatus("Theme colors reset to default palette.");
              }}
              className="subtle-button flex items-center gap-1.5 px-3 py-2 text-xs text-zinc-400 hover:text-white"
              title="Reset accent and background to default"
            >
              <RotateCcw className="size-3" /> Reset colors
            </button>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 pt-2 border-t border-white/[0.06]">
          {/* Accent Color Customizer */}
          <div className="rounded-xl border border-white/[0.06] bg-black/10 p-3.5">
            <div className="flex items-center justify-between gap-2">
              <div className="text-xs font-medium text-zinc-200 flex items-center gap-1.5">
                <Pipette className="size-3.5" style={{ color: "var(--accent-color, #c52b68)" }} />
                Accent Color
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  aria-label="Accent color picker"
                  value={accentColor}
                  onChange={(event) => onAccentColorChange?.(event.target.value)}
                  className="size-7 cursor-pointer rounded-lg border border-white/20 bg-transparent p-0.5"
                />
                <span className="font-mono text-xs uppercase text-zinc-400">{accentColor}</span>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              {ACCENT_PRESETS.map((swatch) => (
                <button
                  key={swatch.hex}
                  type="button"
                  onClick={() => onAccentColorChange?.(swatch.hex)}
                  title={swatch.name}
                  className={`size-6 rounded-lg transition-transform hover:scale-110 relative ${
                    accentColor.toLowerCase() === swatch.hex.toLowerCase()
                      ? "ring-2 ring-white ring-offset-2 ring-offset-black scale-105"
                      : "border border-white/10"
                  }`}
                  style={{ backgroundColor: swatch.hex }}
                />
              ))}
            </div>
          </div>

          {/* Main Theme Color (Background) Customizer */}
          <div className="rounded-xl border border-white/[0.06] bg-black/10 p-3.5">
            <div className="flex items-center justify-between gap-2">
              <div className="text-xs font-medium text-zinc-200 flex items-center gap-1.5">
                <Paintbrush className="size-3.5 text-zinc-400" />
                Main Theme Color (Background)
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  aria-label="Theme background color picker"
                  value={bgColor}
                  onChange={(event) => onBgColorChange?.(event.target.value)}
                  className="size-7 cursor-pointer rounded-lg border border-white/20 bg-transparent p-0.5"
                />
                <span className="font-mono text-xs uppercase text-zinc-400">{bgColor}</span>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              {BG_PRESETS.map((swatch) => (
                <button
                  key={swatch.hex}
                  type="button"
                  onClick={() => onBgColorChange?.(swatch.hex)}
                  title={swatch.name}
                  className={`size-6 rounded-lg transition-transform hover:scale-110 relative ${
                    bgColor.toLowerCase() === swatch.hex.toLowerCase()
                      ? "ring-2 ring-white ring-offset-2 ring-offset-black scale-105"
                      : "border border-white/10"
                  }`}
                  style={{ backgroundColor: swatch.hex }}
                />
              ))}
            </div>
          </div>
        </div>
      </section>
      <section className="panel flex flex-wrap items-center justify-between gap-4 p-5"><div><div className="text-sm text-zinc-200">Relaunch JaneConverter</div><div className="mt-1 text-xs text-zinc-600">Close this window and start the current desktop application again.</div></div><button type="button" disabled={relaunching} onClick={() => void relaunch()} className="subtle-button flex items-center gap-2 px-4 py-2 text-xs disabled:cursor-wait disabled:opacity-60"><RotateCw className={"size-3.5 " + (relaunching ? "animate-spin" : "")} /> {relaunching ? "Relaunching..." : "Relaunch now"}</button></section>
      <section className="panel space-y-4 p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div><div className="text-sm text-zinc-200">Check for updates</div><div className="mt-1 text-xs text-zinc-600">Checks the latest published JaneConverter release on GitHub and the extractor service. Nothing is installed until you choose Update now.</div></div>
          <button type="button" disabled={checking || installing} onClick={() => void updates()} className="subtle-button flex items-center gap-2 px-4 py-2 text-xs disabled:cursor-wait disabled:opacity-60"><RefreshCw className={`size-3.5 ${checking ? "animate-spin" : ""}`} /> {checking ? "Checking..." : "Check now"}</button>
        </div>
        {updateResult?.repo?.has_update && !updateDismissed && (
          <div className="rounded-xl border border-[var(--accent-color,#c52b68)]/30 bg-[var(--accent-color,#c52b68)]/[0.06] p-4" role="region" aria-label="JaneConverter application update">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="text-sm font-medium text-zinc-100">JaneConverter v{updateResult.repo.latest_version} is available</div>
                <p className="mt-1 max-w-xl text-xs leading-relaxed text-zinc-400">Download and verify the update, then JaneConverter will restart to finish installing it. Your files and settings stay in place.</p>
                {!updateResult.repo.installer_available && <p className="mt-2 text-xs text-amber-300">An automatic installer is not available for this package. Open the published release to update manually.</p>}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {updateResult.repo.installer_available ? <button type="button" disabled={installing} onClick={() => void installUpdate()} className="primary-button flex items-center gap-2 px-3 py-2 text-xs disabled:cursor-wait disabled:opacity-60"><RefreshCw className={`size-3.5 ${installing ? "animate-spin" : ""}`} /> {installing ? "Installing..." : "Update now"}</button> : null}
                {updateResult.repo.release_url ? <button type="button" onClick={() => void bridge.openUrl(updateResult.repo?.release_url ?? "")} className="subtle-button flex items-center gap-2 px-3 py-2 text-xs"><ExternalLink className="size-3.5" /> Open release</button> : null}
                <button type="button" disabled={installing} onClick={() => { setUpdateDismissed(true); setMessage("Update dismissed. You can check again anytime."); }} className="subtle-button px-3 py-2 text-xs disabled:opacity-60">Not now</button>
              </div>
            </div>
          </div>
        )}
      </section>
      <div className={`rounded-lg border px-3 py-2 text-[11px] ${message ? "border-[#3b82f6]/15 bg-[#3b82f6]/[0.04] text-zinc-300" : "border-transparent text-zinc-600"}`} role="status" aria-live="polite">{message || "Update and relaunch results appear here."}</div>
      <div className="flex items-center gap-2 text-[11px] text-zinc-700"><ExternalLink size={12} /> {runtime?.packaged ? "Application data uses your OS user-data directory." : "Project-local storage is the default."} User-selected folders are always respected.</div>
    </div>
  );
}
