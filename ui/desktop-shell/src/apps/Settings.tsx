import { FormEvent, useEffect, useMemo, useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

const SWARM_BASE =
  (import.meta.env as Record<string, string>)
    .VITE_SWARM_URL ?? "http://localhost:8000";

type NavSection = "General" | "Appearance" | "AI" | "Models" | "Privacy" | "Hardware" | "About";
const NAV: NavSection[] = ["General", "Appearance", "AI", "Models", "Privacy", "Hardware", "About"];

interface ModelEntry {
  id: string;
  name: string;
  status: string;
}

interface Props {
  onWallpaperChange?: (url: string | undefined, dark: boolean) => void;
}

interface HardwareSnapshot {
  cpu: { temp_c: number | null; usage_pct: number; freq_mhz: number; cores: number; throttled: boolean };
  memory: { total_mb: number; used_mb: number; available_mb: number; swap_used_mb: number; pressure: "low" | "medium" | "high" };
  disks: Array<{ device: string; mount: string; total_gb: number; used_gb: number; pct: number; smart_status: "ok" | "warning" | "failing" | "unknown"; temp_c: number | null; reallocated_sectors: number }>;
  battery: { present: boolean; pct: number | null; status: "charging" | "discharging" | "full" | "unknown"; time_remaining_min: number | null; health_pct: number | null };
  network: Array<{ iface: string; bytes_sent_ps: number; bytes_recv_ps: number; latency_ms: number | null; link_up: boolean; speed_mbps: number }>;
  gpu: { present: boolean; vendor?: string | null; model?: string | null; temp_c?: number | null; usage_pct?: number | null; vram_used_mb?: number | null };
  health_score: number;
  anomaly_score: number;
  anomaly_detected: boolean;
}

interface HardwareAlert {
  alert_id: string;
  severity: "info" | "warning" | "critical";
  component: string;
  message: string;
  first_seen: string;
  last_seen: string;
  count: number;
}

interface HistoryPoint {
  ts: string;
  value: number;
}

function authHeaders(): HeadersInit {
  const authToken = globalThis.localStorage.getItem("kryos_auth_token") ?? "dev-token";
  return {
    Authorization: `Bearer ${authToken}`,
    "Content-Type": "application/json",
  };
}

export function SettingsApp({ onWallpaperChange }: Readonly<Props>) {
  const [section, setSection] = useState<NavSection>("General");
  const [wallpaperUrl, setWallpaperUrl] = useState("");
  const [darkMode, setDarkMode] = useState(false);
  const [accent, setAccent] = useState("#3b82f6");
  const [models, setModels] = useState<ModelEntry[]>([]);
  const [modelSource, setModelSource] = useState("");
  const [modelUrl, setModelUrl] = useState("");
  const [modelLoading, setModelLoading] = useState(false);
  const [modelMsg, setModelMsg] = useState("");
  const [contextWindow, setContextWindow] = useState(4096);
  const [temperature, setTemperature] = useState(0.7);
  const [selectedModel, setSelectedModel] = useState("");
  const [cloudInference, setCloudInference] = useState(false);
  const [policyMsg, setPolicyMsg] = useState("");
  const [hardware, setHardware] = useState<HardwareSnapshot | null>(null);
  const [alerts, setAlerts] = useState<HardwareAlert[]>([]);
  const [historyCpu, setHistoryCpu] = useState<HistoryPoint[]>([]);
  const [historyMem, setHistoryMem] = useState<HistoryPoint[]>([]);
  const [historyDisk, setHistoryDisk] = useState<HistoryPoint[]>([]);
  const [historyBattery, setHistoryBattery] = useState<HistoryPoint[]>([]);
  const [historyLoaded, setHistoryLoaded] = useState(false);

  useEffect(() => {
    void fetch(`${SWARM_BASE}/api/models/list`, { headers: authHeaders() })
      .then((r) => r.json())
      .then((data: { models?: ModelEntry[] }) => setModels(data.models ?? []))
      .catch(() => { /* backend may be unavailable */ });
  }, []);

  useEffect(() => {
    if (section !== "Hardware") {
      return;
    }

    let mounted = true;

    const loadCurrentAndAlerts = async (): Promise<void> => {
      try {
        const [currentResp, alertsResp] = await Promise.all([
          fetch("/api/hardware/current", { headers: authHeaders() }),
          fetch("/api/hardware/alerts", { headers: authHeaders() }),
        ]);

        if (!mounted) {
          return;
        }

        if (currentResp.ok) {
          setHardware((await currentResp.json()) as HardwareSnapshot);
        }
        if (alertsResp.ok) {
          setAlerts((await alertsResp.json()) as HardwareAlert[]);
        }
      } catch {
        // fail-open in settings panel
      }
    };

    void loadCurrentAndAlerts();
    const id = globalThis.setInterval(() => {
      void loadCurrentAndAlerts();
    }, 10000);

    return () => {
      mounted = false;
      globalThis.clearInterval(id);
    };
  }, [section]);

  useEffect(() => {
    if (section !== "Hardware" || historyLoaded) {
      return;
    }

    let mounted = true;

    const loadHistory = async (): Promise<void> => {
      try {
        const [cpuResp, memResp, diskResp, batteryResp] = await Promise.all([
          fetch("/api/hardware/history?metric=cpu_temp&hours=24", { headers: authHeaders() }),
          fetch("/api/hardware/history?metric=memory_used&hours=24", { headers: authHeaders() }),
          fetch("/api/hardware/history?metric=disk_pct&hours=24", { headers: authHeaders() }),
          fetch("/api/hardware/history?metric=battery_pct&hours=24", { headers: authHeaders() }),
        ]);

        if (!mounted) {
          return;
        }

        if (cpuResp.ok) {
          setHistoryCpu(((await cpuResp.json()) as { points: HistoryPoint[] }).points ?? []);
        }
        if (memResp.ok) {
          setHistoryMem(((await memResp.json()) as { points: HistoryPoint[] }).points ?? []);
        }
        if (diskResp.ok) {
          setHistoryDisk(((await diskResp.json()) as { points: HistoryPoint[] }).points ?? []);
        }
        if (batteryResp.ok) {
          setHistoryBattery(((await batteryResp.json()) as { points: HistoryPoint[] }).points ?? []);
        }
        setHistoryLoaded(true);
      } catch {
        // fail-open
      }
    };

    void loadHistory();

    return () => {
      mounted = false;
    };
  }, [section, historyLoaded]);

  async function loadModel(e: FormEvent) {
    e.preventDefault();
    if (!modelSource.trim()) return;
    setModelLoading(true);
    setModelMsg("");
    try {
      const resp = await fetch(`${SWARM_BASE}/api/models/load`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ source: modelSource, url: modelUrl || undefined }),
      });
      const data = (await resp.json()) as { model_id?: string; status?: string };
      setModelMsg(`Model ${data.model_id ?? "unknown"}: ${data.status ?? "queued"}`);
      setModelSource("");
      setModelUrl("");
    } catch {
      setModelMsg("Failed to load model.");
    } finally {
      setModelLoading(false);
    }
  }

  async function setPolicy(key: string, value: boolean) {
    try {
      await fetch(`${SWARM_BASE}/api/vyrex/policy`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ key, value }),
      });
      setPolicyMsg(`Policy "${key}" set to ${String(value)}`);
    } catch {
      setPolicyMsg("Failed to update policy.");
    }
  }

  const ACCENTS = ["#3b82f6", "#8b5cf6", "#ec4899", "#f97316", "#22c55e", "#06b6d4"];
  const healthPercent = useMemo(() => Math.round((hardware?.health_score ?? 0) * 100), [hardware?.health_score]);
  const gaugeColor = healthPercent > 80 ? "#22c55e" : healthPercent >= 50 ? "#f59e0b" : "#ef4444";

  async function dismissAlert(alertId: string): Promise<void> {
    try {
      const resp = await fetch(`/api/hardware/alerts/${alertId}/dismiss`, {
        method: "POST",
        headers: authHeaders(),
      });
      if (resp.ok) {
        setAlerts((prev) => prev.filter((a) => a.alert_id !== alertId));
      }
    } catch {
      // fail-open
    }
  }

  return (
    <div className="flex h-full text-sm">
      {/* Sidebar */}
      <nav className="w-44 shrink-0 bg-black/5 dark:bg-white/5 border-r border-black/10 py-4">
        {NAV.map((s) => (
          <button
            key={s}
            className={`w-full text-left px-4 py-2 rounded-lg mx-2 transition-colors ${section === s ? "bg-blue-500 text-white" : "hover:bg-black/10"}`}
            style={{ width: "calc(100% - 1rem)" }}
            onClick={() => setSection(s)}
          >
            {s}
          </button>
        ))}
      </nav>

      {/* Content */}
      <div className="flex-1 overflow-auto p-6 space-y-5">
        {section === "General" && (
          <>
            <h2 className="text-base font-semibold">General</h2>
            <label className="block">
              <span className="text-xs opacity-60 mb-1 block">Wallpaper Image URL</span>
              <div className="flex gap-2">
                <input
                  className="flex-1 border border-black/20 rounded-lg px-3 py-1.5 bg-transparent text-sm"
                  placeholder="https://…"
                  value={wallpaperUrl}
                  onChange={(e) => setWallpaperUrl(e.target.value)}
                />
                <button
                  className="px-3 py-1.5 rounded-lg bg-blue-500 text-white text-xs"
                  onClick={() => onWallpaperChange?.(wallpaperUrl || undefined, darkMode)}
                >
                  Apply
                </button>
              </div>
            </label>
          </>
        )}

        {section === "Appearance" && (
          <>
            <h2 className="text-base font-semibold">Appearance</h2>
            <div className="flex gap-3">
              {(["Light", "Dark", "Auto"] as const).map((m) => (
                <button
                  key={m}
                  className={`px-4 py-2 rounded-lg border text-xs transition-colors ${
                    (m === "Dark") === darkMode ? "bg-blue-500 text-white border-blue-500" : "border-black/20 hover:bg-black/10"
                  }`}
                  onClick={() => {
                    const d = m === "Dark";
                    setDarkMode(d);
                    onWallpaperChange?.(wallpaperUrl || undefined, d);
                  }}
                >
                  {m}
                </button>
              ))}
            </div>
            <div>
              <span className="text-xs opacity-60 block mb-2">Accent Colour</span>
              <div className="flex gap-2">
                {ACCENTS.map((c) => (
                  <button
                    key={c}
                    className={`w-7 h-7 rounded-full border-2 transition-transform hover:scale-110 ${accent === c ? "border-black/40 scale-110" : "border-transparent"}`}
                    style={{ backgroundColor: c }}
                    onClick={() => setAccent(c)}
                    aria-label={`Accent ${c}`}
                  />
                ))}
              </div>
            </div>
          </>
        )}

        {section === "AI" && (
          <>
            <h2 className="text-base font-semibold">AI Settings</h2>
            <label className="block">
              <span className="text-xs opacity-60 mb-1 block">Active Model</span>
              <select
                className="border border-black/20 rounded-lg px-3 py-1.5 bg-transparent w-full"
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
              >
                <option value="">— select —</option>
                {models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="text-xs opacity-60 mb-1 block">Context Window: {contextWindow}</span>
              <input type="range" min={512} max={32768} step={512} value={contextWindow}
                className="w-full" onChange={(e) => setContextWindow(Number(e.target.value))} />
            </label>
            <label className="block">
              <span className="text-xs opacity-60 mb-1 block">Temperature: {temperature.toFixed(2)}</span>
              <input type="range" min={0} max={2} step={0.05} value={temperature}
                className="w-full" onChange={(e) => setTemperature(Number(e.target.value))} />
            </label>
          </>
        )}

        {section === "Models" && (
          <>
            <h2 className="text-base font-semibold">Model Manager</h2>
            <form onSubmit={loadModel} className="space-y-3">
              <label className="block">
                <span className="text-xs opacity-60 mb-1 block">Model Source / ID</span>
                <input
                  className="w-full border border-black/20 rounded-lg px-3 py-1.5 bg-transparent"
                  placeholder="e.g. huggingface/mistral-7b"
                  value={modelSource}
                  onChange={(e) => setModelSource(e.target.value)}
                />
              </label>
              <label className="block">
                <span className="text-xs opacity-60 mb-1 block">Custom URL (optional)</span>
                <input
                  className="w-full border border-black/20 rounded-lg px-3 py-1.5 bg-transparent"
                  placeholder="https://…"
                  value={modelUrl}
                  onChange={(e) => setModelUrl(e.target.value)}
                />
              </label>
              <button
                type="submit"
                disabled={modelLoading}
                className="px-4 py-2 rounded-lg bg-blue-500 text-white text-xs disabled:opacity-50"
              >
                {modelLoading ? "Loading…" : "Load Model"}
              </button>
            </form>
            {modelMsg ? <div className="text-xs text-green-600">{modelMsg}</div> : null}
            <div className="mt-4 space-y-2">
              {models.map((m) => (
                <div key={m.id} className="rounded-lg px-3 py-2 bg-black/5 text-xs flex justify-between">
                  <span>{m.name}</span>
                  <span className="opacity-60">{m.status}</span>
                </div>
              ))}
            </div>
          </>
        )}

        {section === "Privacy" && (
          <>
            <h2 className="text-base font-semibold">Privacy</h2>
            <div className="flex items-center justify-between p-3 rounded-xl bg-black/5">
              <div>
                <div className="font-medium">Cloud Inference</div>
                <div className="text-xs opacity-60 mt-0.5">Allow model requests to cloud providers</div>
              </div>
              <button
                role="switch"
                aria-checked={cloudInference}
                className={`w-10 h-6 rounded-full transition-colors relative ${cloudInference ? "bg-green-500" : "bg-gray-300"}`}
                onClick={() => {
                  const next = !cloudInference;
                  setCloudInference(next);
                  void setPolicy("cloud_inference", next);
                }}
              >
                <span className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-all ${cloudInference ? "left-5" : "left-1"}`} />
              </button>
            </div>
            {policyMsg ? <div className="text-xs text-green-600">{policyMsg}</div> : null}
          </>
        )}

        {section === "Hardware" && (
          <>
            <h2 className="text-base font-semibold">Hardware</h2>

            <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
              <div className="rounded-xl border border-black/10 p-4 bg-white/60">
                <h3 className="font-semibold mb-3">Live Health</h3>
                <div className="flex items-center gap-4">
                  <div
                    className="w-28 h-28 rounded-full grid place-items-center text-xl font-bold"
                    style={{ border: `10px solid ${gaugeColor}`, color: gaugeColor }}
                  >
                    {healthPercent}
                  </div>
                  <div className="text-xs space-y-2">
                    <div className="px-2 py-1 rounded-full bg-black/5">CPU {Math.round(hardware?.cpu.temp_c ?? 0)}°C</div>
                    <div className="px-2 py-1 rounded-full bg-black/5">RAM {Math.round((hardware?.memory.used_mb ?? 0) / 1024)}/{Math.round((hardware?.memory.total_mb ?? 1) / 1024)}GB</div>
                    <div className="px-2 py-1 rounded-full bg-black/5">Disk {Math.round(hardware?.disks[0]?.pct ?? 0)}%</div>
                    <div className="px-2 py-1 rounded-full bg-black/5">Battery {Math.round(hardware?.battery.pct ?? 0)}%</div>
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-black/10 p-4 bg-white/60 xl:col-span-2">
                <h3 className="font-semibold mb-3">Active Alerts</h3>
                {alerts.length === 0 ? (
                  <div className="text-green-600 text-sm">No hardware alerts - system healthy</div>
                ) : (
                  <div className="space-y-2">
                    {alerts.map((a) => (
                      <div key={a.alert_id} className="flex items-start justify-between gap-3 p-2 rounded-lg bg-black/5">
                        <div>
                          <div className="text-xs font-semibold">
                            <span className={`px-2 py-0.5 rounded-full mr-2 ${a.severity === "critical" ? "bg-red-500 text-white" : a.severity === "warning" ? "bg-yellow-500 text-black" : "bg-blue-500 text-white"}`}>
                              {a.severity}
                            </span>
                            {a.component}
                          </div>
                          <div className="text-sm mt-1">{a.message}</div>
                          <div className="text-xs opacity-60 mt-1">since {new Date(a.first_seen).toLocaleString()}</div>
                        </div>
                        <button className="text-xs px-2 py-1 rounded bg-black/10" onClick={() => void dismissAlert(a.alert_id)}>X</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="rounded-xl border border-black/10 p-4 bg-white/60">
              <h3 className="font-semibold mb-3">History Charts</h3>
              <HistoryChart title="CPU Temperature (last 24h)" color="#ef4444" points={historyCpu} />
              <HistoryChart title="Memory Used MB (last 24h)" color="#3b82f6" points={historyMem} />
              <HistoryChart title="Disk Usage % (last 24h)" color="#f97316" points={historyDisk} />
              <HistoryChart title="Battery % (last 24h)" color="#22c55e" points={historyBattery} />
            </div>
          </>
        )}

        {section === "About" && (
          <>
            <h2 className="text-base font-semibold">About PradyOS</h2>
            <div className="space-y-3 text-xs">
              <Row label="Version" value="2.0.0-dev" />
              <Row label="Kernel" value="6.6.x-kryos" />
              <Row label="Compositor" value="Hyprland 0.41 (Kryos)" />
              <Row label="Shell" value="KryosShell 9.0" />
              <Row label="Build" value={new Date().toDateString()} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Row({ label, value }: Readonly<{ label: string; value: string }>) {
  return (
    <div className="flex justify-between py-1.5 border-b border-black/10">
      <span className="opacity-60">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}

function HistoryChart({ title, color, points }: Readonly<{ title: string; color: string; points: HistoryPoint[] }>) {
  return (
    <div className="h-36 mb-4">
      <div className="text-xs opacity-70 mb-1">{title}</div>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <XAxis dataKey="ts" hide />
          <YAxis hide domain={["dataMin", "dataMax"]} />
          <Tooltip />
          <Line type="monotone" dataKey="value" stroke={color} strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
