import { useCallback, useEffect, useMemo, useState } from "react";
import { getVyrexEnabled } from "../api/models";
import { getSwarmStatus } from "../api/swarm";
import { ActivityMonitor } from "../apps/ActivityMonitor";
import { AIAssistant } from "../apps/AIAssistant";
import { BrowserApp, FilesApp } from "../apps/SimpleApps";
import { ModelManager } from "../apps/ModelManager";
import { ScreenViewer } from "../apps/ScreenViewer";
import { TerminalApp } from "../apps/Terminal";
import { LumynConsole } from "../apps/LumynConsole";
import { DesktopAgent } from "../apps/DesktopAgent";
import { ProcessViewer } from "../apps/ProcessViewer";
import { MemoryBrowser } from "../apps/MemoryBrowser";
import { SettingsApp } from "../apps/Settings";
import type { AppId, SwarmState, WindowItem } from "../types";
import { Dock } from "./Dock";
import { MenuBar } from "./MenuBar";
import { MissionControl } from "./MissionControl";
import { NotificationCentre } from "./NotificationCentre";
import { Spotlight } from "./Spotlight";
import { Wallpaper } from "./Wallpaper";
import { WindowManager } from "./WindowManager";

const APP_META: Record<AppId, { title: string; icon: string }> = {
  terminal: { title: "Terminal", icon: "💻" },
  browser: { title: "Browser", icon: "🌐" },
  files: { title: "Files", icon: "📁" },
  assistant: { title: "AI Assistant", icon: "🤖" },
  settings: { title: "Settings", icon: "⚙️" },
  activity: { title: "Activity Monitor", icon: "📊" },
  models: { title: "Model Manager", icon: "🧠" },
  screen: { title: "Screen Viewer", icon: "🖥️" },
  lumyn: { title: "Lumyn Console", icon: "⚡" },
  "desktop-agent": { title: "Desktop Agent", icon: "🤖" },
  "process-viewer": { title: "Process Viewer", icon: "🖥" },
  "memory-browser": { title: "Memory Browser", icon: "🗄️" },
};

let zCounter = 100;

function createWindow(appId: AppId): WindowItem {
  zCounter += 1;
  return {
    id: `${appId}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    appId,
    title: APP_META[appId].title,
    icon: APP_META[appId].icon,
    x: 120 + Math.random() * 80,
    y: 70 + Math.random() * 80,
    width: 720,
    height: 460,
    zIndex: zCounter,
    minimized: false,
    maximized: false,
  };
}

export function Desktop() {
  const [windows, setWindows] = useState<WindowItem[]>([
    createWindow("assistant"),
    createWindow("activity"),
  ]);
  const [activeWindowId, setActiveWindowId] = useState<string | null>(null);
  const [spotlightOpen, setSpotlightOpen] = useState(false);
  const [missionControlOpen, setMissionControlOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [swarms, setSwarms] = useState<SwarmState[]>([]);
  const [nemoEnabled, setNemoEnabled] = useState(false);
  const [wallpaperUrl, setWallpaperUrl] = useState<string | undefined>(undefined);
  const [darkWallpaper, setDarkWallpaper] = useState(false);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.code === "Space") {
        event.preventDefault();
        setSpotlightOpen((v) => !v);
      }
      if (event.ctrlKey && event.key === "ArrowUp") {
        event.preventDefault();
        setMissionControlOpen((v) => !v);
      }
    }
    globalThis.addEventListener("keydown", onKey);
    return () => globalThis.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    let mounted = true;
    async function tick() {
      try {
        const status = await getSwarmStatus();
        if (mounted) {
          setSwarms(status.swarms);
        }
      } catch {
        // Keep desktop responsive even if backend is temporarily unavailable.
      }
    }
    void tick();
    const timer = globalThis.setInterval(() => void tick(), 2000);
    return () => {
      mounted = false;
      globalThis.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    let mounted = true;
    void (async () => {
      const enabled = await getVyrexEnabled();
      if (mounted) {
        setNemoEnabled(enabled);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const openApp = useCallback((appId: AppId) => {
    setWindows((prev) => {
      const existing = prev.find((w) => w.appId === appId);
      if (existing) {
        zCounter += 1;
        return prev.map((w) =>
          w.id === existing.id ? { ...w, minimized: false, zIndex: zCounter } : w
        );
      }
      return [...prev, createWindow(appId)];
    });
  }, []);

  function focusWindow(id: string) {
    zCounter += 1;
    setActiveWindowId(id);
    setWindows((prev) => prev.map((w) => (w.id === id ? { ...w, zIndex: zCounter } : w)));
  }

  function closeWindow(id: string) {
    setWindows((prev) => prev.filter((w) => w.id !== id));
    if (activeWindowId === id) {
      setActiveWindowId(null);
    }
  }

  function minimizeWindow(id: string) {
    setWindows((prev) => prev.map((w) => (w.id === id ? { ...w, minimized: true } : w)));
  }

  function maximizeWindow(id: string) {
    setWindows((prev) =>
      prev.map((w) =>
        w.id === id ? { ...w, maximized: !w.maximized, x: 24, y: 24, width: 1100, height: 700 } : w
      )
    );
  }

  function updateWindow(id: string, patch: Partial<WindowItem>) {
    setWindows((prev) => prev.map((w) => (w.id === id ? { ...w, ...patch } : w)));
  }

  const runningApps = useMemo(() => windows.map((w) => w.appId), [windows]);

  useEffect(() => {
    const event = new CustomEvent("kryos:desktop-running-apps", {
      detail: {
        appIds: windows.filter((windowItem) => !windowItem.minimized).map((windowItem) => windowItem.appId),
      },
    });
    globalThis.dispatchEvent(event);
  }, [windows]);

  useEffect(() => {
    const handler = (event: Event): void => {
      const customEvent = event as CustomEvent<{ appId?: string }>;
      const appId = customEvent.detail?.appId;
      if (!appId) {
        return;
      }
      if (!(appId in APP_META)) {
        return;
      }
      openApp(appId as AppId);
    };

    globalThis.addEventListener("kryos:desktop-open-app", handler);
    return () => {
      globalThis.removeEventListener("kryos:desktop-open-app", handler);
    };
  }, [openApp]);

  return (
    <div className="relative w-full h-full">
      <Wallpaper imageUrl={wallpaperUrl} dark={darkWallpaper} />
      <MenuBar nemoEnabled={nemoEnabled} />

      <WindowManager
        windows={windows}
        activeWindowId={activeWindowId}
        onFocus={focusWindow}
        onClose={closeWindow}
        onMinimize={minimizeWindow}
        onMaximize={maximizeWindow}
        onMoveResize={updateWindow}
        renderWindow={(window) => renderApp(window.appId, swarms, nemoEnabled, (url, dark) => {
          setWallpaperUrl(url);
          setDarkWallpaper(dark);
        })}
      />

      <Dock runningApps={runningApps} onOpenApp={openApp} />

      <Spotlight
        open={spotlightOpen}
        onClose={() => setSpotlightOpen(false)}
        onSwarmStarted={() => void 0}
        swarms={swarms}
      />

      {missionControlOpen ? (
        <MissionControl
          windows={windows}
          onBringToFront={(id) => { focusWindow(id); }}
          onClose={() => setMissionControlOpen(false)}
        />
      ) : null}

      <NotificationCentre open={notifOpen} onClose={() => setNotifOpen(false)} />

      <aside className="absolute right-4 top-10 w-72 glass rounded-2xl p-3 text-xs z-40">
        <div className="font-semibold mb-2">Live Agent Activity</div>
        <div className="max-h-48 overflow-auto space-y-2">
          {swarms.length === 0 ? (
            <div className="opacity-70">No active swarms.</div>
          ) : (
            swarms.map((swarm) => (
              <div key={swarm.swarm_id} className="rounded-lg bg-white/50 dark:bg-black/20 p-2">
                <div className="font-medium">{swarm.goal}</div>
                <div>{swarm.status}</div>
                <div className="opacity-70">Agents: {swarm.agent_count}</div>
              </div>
            ))
          )}
        </div>
      </aside>
    </div>
  );
}

function renderApp(appId: AppId, swarms: SwarmState[], nemoEnabled: boolean, onWallpaperChange?: (url: string | undefined, dark: boolean) => void) {
  switch (appId) {
    case "assistant":
      return <AIAssistant swarms={swarms} />;
    case "activity":
      return <ActivityMonitor swarms={swarms} nemoEnabled={nemoEnabled} />;
    case "models":
      return <ModelManager />;
    case "terminal":
      return <TerminalApp />;
    case "screen":
      return <ScreenViewer />;
    case "browser":
      return <BrowserApp />;
    case "files":
      return <FilesApp />;
    case "settings":
      return <SettingsApp onWallpaperChange={onWallpaperChange} />;
    case "lumyn":
      return <LumynConsole />;
    case "desktop-agent":
      return <DesktopAgent />;
    case "process-viewer":
      return <ProcessViewer />;
    case "memory-browser":
      return <MemoryBrowser />;
    default:
      return <div className="p-4">Unknown app</div>;
  }
}
