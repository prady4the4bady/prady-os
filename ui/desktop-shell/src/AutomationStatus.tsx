import { useEffect, useState } from "react";

type ScreenInfo = {
  width: number;
  height: number;
  scale: number;
};

type AutomationStats = {
  actions_last_minute: number;
  rate_limit: number;
};

const AUTOMATION_URL = "http://localhost:8101";

export function AutomationStatus() {
  const [online, setOnline] = useState(false);
  const [screen, setScreen] = useState<ScreenInfo | null>(null);
  const [stats, setStats] = useState<AutomationStats | null>(null);

  useEffect(() => {
    let mounted = true;

    async function poll() {
      try {
        const [screenRes, statsRes] = await Promise.all([
          fetch(`${AUTOMATION_URL}/automation/screen/info`),
          fetch(`${AUTOMATION_URL}/automation/stats`),
        ]);
        if (!screenRes.ok || !statsRes.ok) {
          throw new Error("automation service unavailable");
        }
        const screenData = (await screenRes.json()) as ScreenInfo;
        const statsData = (await statsRes.json()) as AutomationStats;
        if (!mounted) {
          return;
        }
        setOnline(true);
        setScreen(screenData);
        setStats(statsData);
      } catch {
        if (!mounted) {
          return;
        }
        setOnline(false);
      }
    }

    void poll();
    const interval = globalThis.setInterval(() => {
      void poll();
    }, 5000);

    return () => {
      mounted = false;
      globalThis.clearInterval(interval);
    };
  }, []);

  return (
    <aside className="fixed bottom-4 left-4 z-50 w-[200px] rounded-2xl glass p-3 text-xs shadow-xl">
      <div className="flex items-center justify-between">
        <span className="font-semibold">Automation</span>
        <span className={`h-2.5 w-2.5 rounded-full ${online ? "bg-emerald-400" : "bg-red-500"}`} />
      </div>
      <div className="mt-2 space-y-1 opacity-80">
        <div>
          {screen ? `${screen.width} x ${screen.height} @ ${screen.scale.toFixed(1)}x` : "Screen info unavailable"}
        </div>
        <div>
          {stats ? `${stats.actions_last_minute}/${stats.rate_limit} actions/min` : "Stats unavailable"}
        </div>
      </div>
    </aside>
  );
}
