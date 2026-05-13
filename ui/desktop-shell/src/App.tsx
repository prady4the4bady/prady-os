import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Calendar, UserCircle } from "lucide-react";
import { Desktop } from "./components/Desktop";
import LoginScreen, { type UserProfile } from "./components/LoginScreen";
import UserSwitcher from "./components/UserSwitcher";
import { VoiceBar } from "./components/VoiceBar";
import { AutomationStatus } from "./AutomationStatus";
import { LumynTaskPanel } from "./LumynTaskPanel";
import { ModelHub } from "./ModelHub";
import { SwarmPanel } from "./SwarmPanel";
import { PerformanceDashboard } from "./PerformanceDashboard";
import { InferenceLog } from "./InferenceLog";
import { ComputerUsePanel } from "./ComputerUsePanel";
import ModelHubPanel from "./ModelHubPanel";
import MemoryPanel from "./MemoryPanel";
import PersonaPanel from "./PersonaPanel";
import SchedulerPanel from "./SchedulerPanel";
import NotificationCenter from "./NotificationCenter";
import TaskHistory from "./TaskHistory";
import WatchdogCenter from "./WatchdogCenter";
import AppStore from "./AppStore";
import SecurityCenter from "./SecurityCenter";
import PersonaManager from "./PersonaManager";
import SpotlightLauncher from "./SpotlightLauncher";
import Dock from "./Dock";
import WindowOverview from "./WindowOverview";
import { ShellWindowStateProvider, useShellWindowState } from "./ShellWindowState";
import SoftwareUpdate from "./apps/SoftwareUpdate/SoftwareUpdate";
import InventorDashboard from "./apps/InventorDashboard/InventorDashboard";
import About from "./apps/About";
import FirstBootWizard from "./components/FirstBootWizard";

function isTypingTarget(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null;
  if (!element) {
    return false;
  }
  const tag = element.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
    return true;
  }
  return element.isContentEditable;
}

function AppShell(): JSX.Element | null {
  const { registerWindow, setWindowOpen, windows } = useShellWindowState();
  const [checked, setChecked] = useState(false);
  const [swarmOpen, setSwarmOpen] = useState(false);
  const [inferenceOpen, setInferenceOpen] = useState(false);
  const [computerOpen, setComputerOpen] = useState(true);
  const [modelHubOpen, setModelHubOpen] = useState(false);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [personaOpen, setPersonaOpen] = useState(false);
  const [schedulerOpen, setSchedulerOpen] = useState(false);
  const [appStoreOpen, setAppStoreOpen] = useState(false);
  const [securityCenterOpen, setSecurityCenterOpen] = useState(false);
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState<string | null>(null);
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null);
  const [switchingUser, setSwitchingUser] = useState(false);
  const [voiceBarOpen, setVoiceBarOpen] = useState(false);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [inventorOpen] = useState(false);
  const [oobeWizardOpen, setOobeWizardOpen] = useState(false);
  const [systemAbout, setSystemAbout] = useState<{ name: string; version: string; channel: string; build?: string }>({
    name: "Prady OS",
    version: "1.0.0",
    channel: "stable",
    build: "phase-38",
  });
  const previousSessionRef = useRef<{ authToken: string; refreshToken: string; user: UserProfile } | null>(null);

  const windowById = useMemo(
    () => new Map(windows.map((windowRecord) => [windowRecord.id, windowRecord])),
    [windows]
  );

  const getWindowOpen = useCallback((id: string): boolean => windowById.get(id)?.open ?? false, [windowById]);
  const getWindowLayer = useCallback((id: string): number => windowById.get(id)?.zIndex ?? 9000, [windowById]);

  useEffect(() => {
    registerWindow({ id: "notifications", title: "Notifications", minimizable: true });
    registerWindow({ id: "task-history", title: "Task History", minimizable: true });
    registerWindow({ id: "model-hub", title: "Model Hub", minimizable: true });
    registerWindow({ id: "persona-manager", title: "Persona Manager", minimizable: true });
    registerWindow({ id: "watchdog-center", title: "Watchdog Center", minimizable: true });

    registerWindow({ id: "swarm-panel", title: "Swarm Panel", minimizable: true });
    registerWindow({ id: "inference-log", title: "Inference Log", minimizable: true });
    registerWindow({ id: "computer-use", title: "Computer Use", minimizable: true });
    registerWindow({ id: "model-hub-panel", title: "Model Hub Panel", minimizable: true });
    registerWindow({ id: "memory-panel", title: "Memory Panel", minimizable: true });
    registerWindow({ id: "persona-panel", title: "Persona Panel", minimizable: true });
    registerWindow({ id: "scheduler-panel", title: "Scheduler Panel", minimizable: true });
    registerWindow({ id: "app-store", title: "App Store", minimizable: true });
    registerWindow({ id: "security-center", title: "Security Center", minimizable: true });
    registerWindow({ id: "software-update", title: "Software Update", minimizable: true });
    registerWindow({ id: "inventor-engine", title: "Inventor Engine", minimizable: true });
  }, [registerWindow]);

  useEffect(() => {
    setWindowOpen("swarm-panel", swarmOpen);
  }, [setWindowOpen, swarmOpen]);

  useEffect(() => {
    setWindowOpen("inference-log", inferenceOpen);
  }, [inferenceOpen, setWindowOpen]);

  useEffect(() => {
    setWindowOpen("computer-use", computerOpen);
  }, [computerOpen, setWindowOpen]);

  useEffect(() => {
    setWindowOpen("model-hub-panel", modelHubOpen);
  }, [modelHubOpen, setWindowOpen]);

  useEffect(() => {
    setWindowOpen("memory-panel", memoryOpen);
  }, [memoryOpen, setWindowOpen]);

  useEffect(() => {
    setWindowOpen("persona-panel", personaOpen);
  }, [personaOpen, setWindowOpen]);

  useEffect(() => {
    setWindowOpen("scheduler-panel", schedulerOpen);
  }, [schedulerOpen, setWindowOpen]);

  useEffect(() => {
    setWindowOpen("app-store", appStoreOpen);
  }, [appStoreOpen, setWindowOpen]);

  useEffect(() => {
    setWindowOpen("security-center", securityCenterOpen);
  }, [securityCenterOpen, setWindowOpen]);

  useEffect(() => {
    setWindowOpen("inventor-engine", inventorOpen);
  }, [inventorOpen, setWindowOpen]);

  useEffect(() => {
    const toggleVoice = (): void => setVoiceBarOpen((prev) => !prev);
    const openVoice = (): void => setVoiceBarOpen(true);
    globalThis.addEventListener("kryos:toggle-voice-bar", toggleVoice);
    globalThis.addEventListener("kryos:open-voice-settings", openVoice);
    return () => {
      globalThis.removeEventListener("kryos:toggle-voice-bar", toggleVoice);
      globalThis.removeEventListener("kryos:open-voice-settings", openVoice);
    };
  }, []);

  useEffect(() => {
    if (!authToken || !refreshToken) {
      return;
    }

    const originalFetch = globalThis.fetch.bind(globalThis);

    const refreshAccessToken = async (): Promise<string | null> => {
      try {
        const resp = await originalFetch("/auth/refresh", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!resp.ok) {
          return null;
        }
        const payload = (await resp.json()) as { access_token: string; refresh_token: string };
        if (!payload.access_token || !payload.refresh_token) {
          return null;
        }
        setAuthToken(payload.access_token);
        setRefreshToken(payload.refresh_token);
        return payload.access_token;
      } catch {
        return null;
      }
    };

    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      let requestUrl: string;
      if (typeof input === "string") {
        requestUrl = input;
      } else if (input instanceof URL) {
        requestUrl = input.toString();
      } else {
        requestUrl = input.url;
      }
      const headers = new Headers(init?.headers ?? {});
      const isAuthRoutable =
        requestUrl.startsWith("/api") ||
        requestUrl.startsWith("/auth") ||
        requestUrl.startsWith("/users");

      if (isAuthRoutable && authToken) {
        headers.set("Authorization", `Bearer ${authToken}`);
      }

      const response = await originalFetch(input, { ...init, headers });

      if (
        response.status === 401 &&
        isAuthRoutable &&
        !requestUrl.startsWith("/auth/login") &&
        !requestUrl.startsWith("/auth/refresh") &&
        refreshToken
      ) {
        const refreshedToken = await refreshAccessToken();
        if (!refreshedToken) {
          setAuthToken(null);
          setRefreshToken(null);
          setCurrentUser(null);
          return response;
        }

        const retryHeaders = new Headers(init?.headers ?? {});
        retryHeaders.set("Authorization", `Bearer ${refreshedToken}`);
        return originalFetch(input, { ...init, headers: retryHeaders });
      }

      return response;
    }) as typeof globalThis.fetch;

    return () => {
      globalThis.fetch = originalFetch;
    };
  }, [authToken, refreshToken]);

  useEffect(() => {
    let mounted = true;

    void (async () => {
      try {
        const res = await fetch("/api/system/first-boot-status");
        if (!res.ok) throw new Error("oobe status unavailable");
        const data = (await res.json()) as { complete?: boolean };
        if (data.complete === false) {
          setOobeWizardOpen(true);
        }
      } catch {
        // Safe fallback: render desktop if OOBE service is unavailable.
      } finally {
        if (mounted) setChecked(true);
      }
    })();

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    const openAbout = (): void => setAboutOpen(true);
    const openOobe = (): void => setOobeWizardOpen(true);
    globalThis.addEventListener("kryos:open-about", openAbout);
    globalThis.addEventListener("kryos:open-oobe", openOobe);
    return () => {
      globalThis.removeEventListener("kryos:open-about", openAbout);
      globalThis.removeEventListener("kryos:open-oobe", openOobe);
    };
  }, []);

  useEffect(() => {
    let mounted = true;
    void (async () => {
      try {
        const response = await fetch("/api/system/version");
        if (!response.ok) {
          return;
        }
        const payload = (await response.json()) as { name?: string; version?: string; channel?: string; build?: string };
        if (mounted) {
          setSystemAbout({
            name: payload.name ?? "Prady OS",
            version: payload.version ?? "1.0.0",
            channel: payload.channel ?? "stable",
            build: payload.build ?? "phase-38",
          });
        }
      } catch {
        // Keep fallback values when system-health is not available.
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  // Global keyboard shortcuts
  useEffect(() => {
    const plainShortcuts: Record<string, () => void> = {
      w: () => setSwarmOpen((prev) => !prev),
      i: () => setInferenceOpen((prev) => !prev),
      u: () => setComputerOpen((prev) => !prev),
      k: () => setModelHubOpen((prev) => !prev),
      m: () => setMemoryOpen((prev) => !prev),
      p: () => setPersonaOpen((prev) => !prev),
    };
    const shiftedShortcuts: Record<string, () => void> = {
      s: () => setSchedulerOpen((prev) => !prev),
      a: () => setAppStoreOpen((prev) => !prev),
      q: () => setSecurityCenterOpen((prev) => !prev),
      u: () => setWindowOpen("software-update", !getWindowOpen("software-update")),
    };

    const handler = (e: KeyboardEvent) => {
      if (isTypingTarget(e.target)) {
        return;
      }
      if (!(e.metaKey || e.ctrlKey)) {
        return;
      }

      const key = e.key.toLowerCase();
      const callback = e.shiftKey ? shiftedShortcuts[key] : plainShortcuts[key];
      if (!callback) {
        return;
      }

      e.preventDefault();
      callback();
    };
    globalThis.addEventListener('keydown', handler);
    return () => globalThis.removeEventListener('keydown', handler);
  }, [getWindowOpen, setWindowOpen]);

  if (!checked) {
    return null;
  }

  if (!authToken || !currentUser || !refreshToken) {
    return (
      <LoginScreen
        switching={switchingUser}
        onCancel={
          switchingUser
            ? () => {
                const previous = previousSessionRef.current;
                if (previous) {
                  setAuthToken(previous.authToken);
                  setRefreshToken(previous.refreshToken);
                  setCurrentUser(previous.user);
                }
                setSwitchingUser(false);
              }
            : undefined
        }
        onLoginSuccess={(payload) => {
          setAuthToken(payload.access_token);
          setRefreshToken(payload.refresh_token);
          setCurrentUser(payload.user);
          setSwitchingUser(false);
          previousSessionRef.current = null;
        }}
      />
    );
  }

  return (
    <>
      <Desktop />
      <LumynTaskPanel />
      <AutomationStatus />
      {swarmOpen && <SwarmPanel onClose={() => setSwarmOpen(false)} />}
      {inferenceOpen && <InferenceLog onClose={() => setInferenceOpen(false)} />}
      {computerOpen && <ComputerUsePanel />}
      {modelHubOpen && <ModelHubPanel />}
      {memoryOpen && <MemoryPanel />}
      {personaOpen && <PersonaPanel />}
      {schedulerOpen && <SchedulerPanel />}
      <PerformanceDashboard />
      <ModelHub
        open={getWindowOpen("model-hub")}
        onOpenChange={(open) => setWindowOpen("model-hub", open)}
        layerZIndex={getWindowLayer("model-hub")}
      />
      <PersonaManager
        open={getWindowOpen("persona-manager")}
        onOpenChange={(open) => setWindowOpen("persona-manager", open)}
        layerZIndex={getWindowLayer("persona-manager")}
      />
      <NotificationCenter
        open={getWindowOpen("notifications")}
        onOpenChange={(open) => setWindowOpen("notifications", open)}
        layerZIndex={getWindowLayer("notifications")}
      />
      <TaskHistory
        open={getWindowOpen("task-history")}
        onOpenChange={(open) => setWindowOpen("task-history", open)}
        layerZIndex={getWindowLayer("task-history")}
      />
      <WatchdogCenter
        open={getWindowOpen("watchdog-center")}
        onOpenChange={(open) => setWindowOpen("watchdog-center", open)}
        layerZIndex={getWindowLayer("watchdog-center")}
      />
      <AppStore
        open={getWindowOpen("app-store")}
        onOpenChange={(open) => setWindowOpen("app-store", open)}
        layerZIndex={getWindowLayer("app-store")}
      />
      <SecurityCenter
        open={getWindowOpen("security-center")}
        onOpenChange={(open) => setWindowOpen("security-center", open)}
        layerZIndex={getWindowLayer("security-center")}
      />
      <SoftwareUpdate
        open={getWindowOpen("software-update")}
        onOpenChange={(open) => setWindowOpen("software-update", open)}
        layerZIndex={getWindowLayer("software-update")}
      />
      <InventorDashboard
        open={getWindowOpen("inventor-engine")}
        onOpenChange={(open) => setWindowOpen("inventor-engine", open)}
        layerZIndex={getWindowLayer("inventor-engine")}
      />

      <SpotlightLauncher />
      <WindowOverview />
      <Dock />
      <UserSwitcher
        authToken={authToken}
        currentUser={currentUser}
        onSwitchUser={() => {
          previousSessionRef.current = {
            authToken,
            refreshToken,
            user: currentUser,
          };
          setSwitchingUser(true);
          setAuthToken(null);
          setRefreshToken(null);
          setCurrentUser(null);
        }}
        onLogout={() => {
          setAuthToken(null);
          setRefreshToken(null);
          setCurrentUser(null);
          setSwitchingUser(false);
          previousSessionRef.current = null;
        }}
      />
      {voiceBarOpen ? <VoiceBar /> : null}

      <button
        type="button"
        onClick={() => setModelHubOpen(prev => !prev)}
        style={{
          position: 'fixed',
          bottom: 56,
          right: 14,
          zIndex: 50,
          borderRadius: 10,
          border: '1px solid rgba(58,58,60,0.7)',
          background: 'rgba(28,28,30,0.85)',
          color: '#F2F2F7',
          backdropFilter: 'blur(12px)',
          WebkitBackdropFilter: 'blur(12px)',
          padding: '6px 10px',
          fontSize: 11,
          fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif",
          cursor: 'pointer',
        }}
      >
        📦⬇ Model Hub
      </button>

      <button
        type="button"
        onClick={() => setMemoryOpen(prev => !prev)}
        style={{
          position: 'fixed',
          bottom: 56,
          right: 124,
          zIndex: 50,
          borderRadius: 10,
          border: '1px solid rgba(58,58,60,0.7)',
          background: 'rgba(28,28,30,0.85)',
          color: '#F2F2F7',
          backdropFilter: 'blur(12px)',
          WebkitBackdropFilter: 'blur(12px)',
          padding: '6px 10px',
          fontSize: 11,
          fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif",
          cursor: 'pointer',
        }}
      >
        🧠 Memory
      </button>

      <button
        type="button"
        onClick={() => setPersonaOpen(prev => !prev)}
        style={{
          position: 'fixed',
          bottom: 56,
          right: 234,
          zIndex: 50,
          borderRadius: 10,
          border: '1px solid rgba(58,58,60,0.7)',
          background: 'rgba(28,28,30,0.85)',
          color: '#F2F2F7',
          backdropFilter: 'blur(12px)',
          WebkitBackdropFilter: 'blur(12px)',
          padding: '6px 10px',
          fontSize: 11,
          fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif",
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        <UserCircle size={14} /> Persona
      </button>

      <button
        type="button"
        onClick={() => setSchedulerOpen(prev => !prev)}
        style={{
          position: 'fixed',
          bottom: 56,
          right: 344,
          zIndex: 50,
          borderRadius: 10,
          border: '1px solid rgba(58,58,60,0.7)',
          background: 'rgba(28,28,30,0.85)',
          color: '#F2F2F7',
          backdropFilter: 'blur(12px)',
          WebkitBackdropFilter: 'blur(12px)',
          padding: '6px 10px',
          fontSize: 11,
          fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif",
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        <Calendar size={14} /> Scheduler
      </button>

      {/* Keyboard shortcut legend */}
      <footer
        style={{
          position: 'fixed',
          bottom: 8,
          left: '50%',
          transform: 'translateX(-50%)',
          background: 'rgba(28,28,30,0.85)',
          backdropFilter: 'blur(12px)',
          WebkitBackdropFilter: 'blur(12px)',
          border: '1px solid rgba(58,58,60,0.7)',
          borderRadius: 10,
          padding: '5px 16px',
          display: 'flex',
          gap: 20,
          fontSize: 12,
          color: '#8E8E93',
          pointerEvents: 'none',
          userSelect: 'none',
          zIndex: 50,
          fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif",
        }}
      >
        <span><kbd style={{ color: '#F2F2F7' }}>⌘K</kbd> Model Hub</span>
        <span><kbd style={{ color: '#F2F2F7' }}>⌘W</kbd> Swarm Panel</span>
        <span><kbd style={{ color: '#F2F2F7' }}>⌘A</kbd> Agent Panel</span>
        <span><kbd style={{ color: '#F2F2F7' }}>⌘I</kbd> Inference Log</span>
        <span><kbd style={{ color: '#F2F2F7' }}>⌘U</kbd> Computer Use</span>
        <span><kbd style={{ color: '#F2F2F7' }}>⌘M</kbd> Memory</span>
        <span><kbd style={{ color: '#F2F2F7' }}>⌘P</kbd> Persona</span>
        <span><kbd style={{ color: '#F2F2F7' }}>⌘⇧S</kbd> Scheduler</span>
        <span><kbd style={{ color: '#F2F2F7' }}>⌘⇧A</kbd> App Store</span>
      </footer>

      <About open={aboutOpen} onClose={() => setAboutOpen(false)} about={systemAbout} />

      <FirstBootWizard open={oobeWizardOpen} onClose={() => setOobeWizardOpen(false)} />
    </>
  );
}

export default function App(): JSX.Element {
  return (
    <ShellWindowStateProvider>
      <AppShell />
    </ShellWindowStateProvider>
  );
}
