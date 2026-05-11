import { useCallback, useEffect, useState } from "react";

const SWARM_BASE = (import.meta.env as Record<string, string>)
  .VITE_SWARM_URL ?? "http://localhost:8000";

interface ProcessInfo {
  pid: number;
  name: string;
  cpu_percent: number;
  memory_mb: number;
  status: string;
}

interface WindowInfo {
  pid: number;
  title: string;
  x: number;
  y: number;
  width: number;
  height: number;
  focused: boolean;
}

export function ProcessViewer() {
  const [processes, setProcesses] = useState<ProcessInfo[]>([]);
  const [windows, setWindows] = useState<WindowInfo[]>([]);
  const [launchName, setLaunchName] = useState("");
  const [launchArgs, setLaunchArgs] = useState("");
  const [launching, setLaunching] = useState(false);
  const [launchError, setLaunchError] = useState("");
  const [killTarget, setKillTarget] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [pRes, wRes] = await Promise.all([
        fetch(`${SWARM_BASE}/processes/list`),
        fetch(`${SWARM_BASE}/processes/windows`),
      ]);
      if (pRes.ok) {
        const d = (await pRes.json()) as { processes: ProcessInfo[] };
        setProcesses(d.processes ?? []);
      }
      if (wRes.ok) {
        const d = (await wRes.json()) as { windows: WindowInfo[] };
        setWindows(d.windows ?? []);
      }
    } catch (error: unknown) {
      void error;
      // keep stale
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = globalThis.setInterval(() => void refresh(), 3000);
    return () => globalThis.clearInterval(timer);
  }, [refresh]);

  const handleKill = useCallback(
    async (pid: number) => {
      if (killTarget === pid) {
        // confirmed
        setKillTarget(null);
        try {
          await fetch(`${SWARM_BASE}/processes/${pid}`, { method: "DELETE" });
          void refresh();
        } catch (error: unknown) {
          void error;
        }
      } else {
        setKillTarget(pid);
        // auto-cancel after 3s
        setTimeout(() => setKillTarget((t) => (t === pid ? null : t)), 3000);
      }
    },
    [killTarget, refresh]
  );

  const handleLaunch = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!launchName.trim()) return;
      setLaunching(true);
      setLaunchError("");
      try {
        const args = launchArgs
          .trim()
          .split(/\s+/)
          .filter(Boolean);
        const res = await fetch(`${SWARM_BASE}/processes/launch`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ app_name: launchName.trim(), args }),
        });
        if (res.ok) {
          setLaunchName("");
          setLaunchArgs("");
          void refresh();
        } else {
          const e = (await res.json()) as { detail?: string };
          setLaunchError(e.detail ?? `Error ${res.status}`);
        }
      } catch (err) {
        setLaunchError(String(err));
      } finally {
        setLaunching(false);
      }
    },
    [launchName, launchArgs, refresh]
  );

  return (
    <div className="h-full p-3 flex flex-col gap-3 text-sm overflow-auto">
      <div className="font-semibold text-base">Process Viewer</div>

      {/* Launch form */}
      <form onSubmit={handleLaunch} className="flex gap-2 flex-wrap">
        <input
          className="flex-1 min-w-32 rounded-lg px-2 py-1 bg-white/20 focus:outline-none focus:ring-2 focus:ring-blue-400"
          placeholder="App name (e.g. firefox)"
          value={launchName}
          onChange={(e) => setLaunchName(e.target.value)}
        />
        <input
          className="flex-1 min-w-32 rounded-lg px-2 py-1 bg-white/20 focus:outline-none"
          placeholder="Args (optional)"
          value={launchArgs}
          onChange={(e) => setLaunchArgs(e.target.value)}
        />
        <button
          type="submit"
          disabled={launching || !launchName.trim()}
          className="px-3 py-1 rounded-lg bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-40"
        >
          {launching ? "…" : "Launch"}
        </button>
      </form>
      {launchError && (
        <div className="text-red-400 text-xs">{launchError}</div>
      )}

      {/* Process table */}
      <div className="overflow-x-auto rounded-xl bg-white/10">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-white/10 text-left">
              <th className="p-2">PID</th>
              <th className="p-2">Name</th>
              <th className="p-2">CPU%</th>
              <th className="p-2">Mem MB</th>
              <th className="p-2">Status</th>
              <th className="p-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {processes.map((p) => (
              <tr key={p.pid} className="border-b border-white/5 hover:bg-white/5">
                <td className="p-2 font-mono">{p.pid}</td>
                <td className="p-2">{p.name}</td>
                <td className="p-2">{p.cpu_percent.toFixed(1)}</td>
                <td className="p-2">{p.memory_mb.toFixed(0)}</td>
                <td className="p-2">
                  <span
                    className={`px-1.5 py-0.5 rounded text-xs ${
                      p.status === "running"
                        ? "bg-emerald-500/30 text-emerald-300"
                        : "bg-zinc-500/30 text-zinc-300"
                    }`}
                  >
                    {p.status}
                  </span>
                </td>
                <td className="p-2">
                  <button
                    onClick={() => void handleKill(p.pid)}
                    className={`px-2 py-0.5 rounded text-xs ${
                      killTarget === p.pid
                        ? "bg-red-600 text-white"
                        : "bg-red-500/30 hover:bg-red-500/60 text-red-300"
                    }`}
                  >
                    {killTarget === p.pid ? "Confirm?" : "Kill"}
                  </button>
                </td>
              </tr>
            ))}
            {processes.length === 0 && (
              <tr>
                <td colSpan={6} className="p-4 text-center opacity-50">
                  No processes
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Windows section */}
      {windows.length > 0 && (
        <div>
          <div className="font-medium mb-1 text-xs opacity-70 uppercase tracking-wide">Open Windows</div>
          <div className="grid grid-cols-2 gap-2">
            {windows.map((w) => (
              <div
                key={`${w.pid}-${w.title}`}
                className={`rounded-lg p-2 text-xs ${
                  w.focused ? "bg-blue-500/20 border border-blue-400/40" : "bg-white/10"
                }`}
              >
                <div className="font-medium truncate">{w.title}</div>
                <div className="opacity-60">PID {w.pid}</div>
                <div className="opacity-50">
                  {w.width}×{w.height}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
