import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { bridge, type AccessStatus, type ConverterEvent, type ConverterSettings, type RuntimeInfo } from "./bridge";
import { Sidebar, type ViewKey } from "./components/Sidebar";
import { Topbar } from "./components/Topbar";
import { ConverterView } from "./components/ConverterView";
import { LibraryView } from "./components/LibraryView";
import { ConsoleView } from "./components/ConsoleView";
import { SettingsView } from "./components/SettingsView";

const defaultSettings: ConverterSettings = {
  outputDir: "converted",
  category: "Music",
  format: "mp3",
  bitrate: "320k",
  sampleRate: 48000,
  resolution: "original",
  normalize: false,
  useGpu: false,
  saveCover: true,
  saveMetadata: true,
  retries: 2,
};

export default function App() {
  const [activeView, setActiveView] = useState<ViewKey>("converter");
  const [runtime, setRuntime] = useState<RuntimeInfo | null>(null);
  const [settings, setSettings] = useState<ConverterSettings>(defaultSettings);
  const [events, setEvents] = useState<ConverterEvent[]>([]);
  const [access, setAccess] = useState<AccessStatus>({ active: false, link: "", browser: "", bridgeConnected: false });
  const [jobId, setJobId] = useState("");
  const activeJobRef = useRef("");
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState("Ready. Paste a link or choose a file to begin.");

  useEffect(() => {
    let mounted = true;
    void Promise.all([bridge.runtimeInfo(), bridge.settingsGet(), bridge.accessStatus()]).then(([nextRuntime, nextSettings, nextAccess]) => {
      if (!mounted) return;
      setRuntime(nextRuntime);
      setSettings(nextSettings);
      setAccess(nextAccess);
    }).catch((error) => {
      if (mounted) setStatus(error instanceof Error ? error.message : String(error));
    });
    let cleanup: (() => void) | undefined;
    void bridge.subscribe((event) => {
      if (!mounted) return;
      setEvents((current) => [...current.slice(-1499), event]);
      if (event.kind === "started" && !activeJobRef.current) {
        activeJobRef.current = event.jobId;
        setJobId(event.jobId);
      }
      if (event.jobId && event.jobId === activeJobRef.current) {
        if (event.progress !== undefined) setProgress(event.progress);
        setStatus(event.message);
        if (event.kind === "finished" || event.kind === "failed" || event.kind === "cancelled") {
          activeJobRef.current = "";
          setJobId("");
        }
      }
    }).then((unlisten) => { cleanup = unlisten; });
    return () => { mounted = false; cleanup?.(); };
  }, []);

  useEffect(() => {
    if (!access.active) return;
    const timer = window.setInterval(() => { void bridge.accessStatus().then(setAccess); }, 700);
    return () => window.clearInterval(timer);
  }, [access.active]);

  useEffect(() => {
    let mounted = true;
    const timer = window.setTimeout(() => {
      void bridge.checkUpdates().then((message) => {
        if (!mounted || !/update available|check unavailable/i.test(message)) return;
        setStatus(message);
        setEvents((current) => [...current.slice(-1499), { jobId: "ui", kind: "status", message }]);
      }).catch(() => {
        // Startup checks stay quiet when the machine is offline. The Settings
        // view remains available for an explicit retry and full status text.
      });
    }, 1200);
    return () => { mounted = false; window.clearTimeout(timer); };
  }, []);

  function statusMessage(message: string) {
    setStatus(message);
    setEvents((current) => [...current.slice(-1499), { jobId: "ui", kind: "status", message }]);
  }

  function updateSettings(next: ConverterSettings) {
    setSettings(next);
    void bridge.settingsSave(next).catch((error) => statusMessage(error instanceof Error ? error.message : String(error)));
  }

  async function start(source: string, playlistIndexes?: string) {
    try {
      const nextJob = await bridge.startConversion({ ...settings, source, playlistIndexes, browserSession: access.browser || undefined });
      activeJobRef.current = nextJob;
      setJobId(nextJob);
      setProgress(.02);
      setStatus("Starting conversion...");
      setActiveView("console");
    } catch (error) {
      statusMessage(error instanceof Error ? error.message : String(error));
    }
  }

  async function cancel() {
    if (!jobId) return;
    try { await bridge.cancelConversion(jobId); setStatus("Aborting conversion..."); }
    catch (error) { statusMessage(error instanceof Error ? error.message : String(error)); }
  }

  async function createAccess(source: string): Promise<AccessStatus> {
    try {
      const nextAccess = await bridge.createAccessLink(source);
      setAccess(nextAccess);
      await bridge.openUrl(nextAccess.link);
      statusMessage("Temporary access link opened in your browser.");
      return nextAccess;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      statusMessage(message);
      throw error;
    }
  }

  async function clearAccess() {
    try {
      await bridge.clearAccessLink();
      setAccess({ active: false, link: "", browser: "", bridgeConnected: false });
      statusMessage("Account access cleared. Public-only extraction is active.");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      statusMessage(message);
      throw error;
    }
  }

  const content = activeView === "converter"
    ? <ConverterView settings={settings} runtime={runtime} events={events} access={access} running={Boolean(jobId)} progress={progress} status={status} onSettings={updateSettings} onStart={start} onCancel={cancel} onCreateAccess={createAccess} onClearAccess={clearAccess} onStatus={statusMessage} />
    : activeView === "library"
      ? <LibraryView settings={settings} onSettings={updateSettings} onStatus={statusMessage} />
      : activeView === "console"
        ? <ConsoleView events={events} onClear={() => setEvents([])} onStatus={statusMessage} />
        : <SettingsView runtime={runtime} onStatus={statusMessage} />;

  return (
    <div className="relative flex min-h-screen overflow-hidden bg-[#02000a] text-zinc-200">
      <div className="pointer-events-none absolute -left-32 -top-24 size-[460px] rounded-full bg-[#c52b68]/[0.055] blur-3xl ambient-orb" />
      <div className="pointer-events-none absolute -right-28 -top-36 h-[390px] w-[700px] rounded-full top-right-glow ambient-orb" style={{ animationDelay: "-6s" }} />
      <div className="pointer-events-none absolute right-0 top-16 h-px w-[58%] top-right-glow-line" />
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(120deg,rgba(255,255,255,.018),transparent_35%)]" />
      <Sidebar activeView={activeView} onChange={setActiveView} />
      <div className="relative flex min-w-0 flex-1 flex-col"><Topbar runtime={runtime} /><main className="min-h-0 flex-1 overflow-y-auto px-8 py-8"><motion.div key={activeView} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .25 }}>{content}</motion.div></main></div>
    </div>
  );
}
