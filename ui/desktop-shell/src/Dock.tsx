import { useEffect, useMemo, useState } from "react";
import { ArrowUpCircle, Bot, Cpu, Globe, Mic, Package2, Settings, Shield, ShieldCheck, TerminalSquare, Users } from "lucide-react";
import { useShellWindowState } from "./ShellWindowState";

interface DockItem {
  id: string;
  label: string;
  kind: "panel" | "desktop-app" | "action";
  target: string;
  icon: JSX.Element;
}

const FONT = "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif";

const DOCK_ITEMS: DockItem[] = [
  {
    id: "dock-terminal",
    label: "Terminal",
    kind: "desktop-app",
    target: "terminal",
    icon: <TerminalSquare size={18} />,
  },
  {
    id: "dock-browser",
    label: "Browser",
    kind: "desktop-app",
    target: "browser",
    icon: <Globe size={18} />,
  },
  {
    id: "dock-task-runner",
    label: "Task Runner",
    kind: "panel",
    target: "task-history",
    icon: <Bot size={18} />,
  },
  {
    id: "dock-models",
    label: "Models",
    kind: "panel",
    target: "model-hub",
    icon: <Cpu size={18} />,
  },
  {
    id: "dock-personas",
    label: "Personas",
    kind: "panel",
    target: "persona-manager",
    icon: <Users size={18} />,
  },
  {
    id: "dock-watchdog",
    label: "Watchdog",
    kind: "panel",
    target: "watchdog-center",
    icon: <Shield size={18} />,
  },
  {
    id: "dock-settings",
    label: "Settings",
    kind: "desktop-app",
    target: "settings",
    icon: <Settings size={18} />,
  },
  {
    id: "dock-app-store",
    label: "App Store",
    kind: "panel",
    target: "app-store",
    icon: <Package2 size={18} />,
  },
  {
    id: "dock-security",
    label: "Security",
    kind: "panel",
    target: "security-center",
    icon: <ShieldCheck size={18} />,
  },
  {
    id: "dock-software-update",
    label: "Update",
    kind: "panel",
    target: "software-update",
    icon: <ArrowUpCircle size={18} />,
  },
  {
    id: "dock-voice",
    label: "Voice",
    kind: "action",
    target: "voice-bar",
    icon: <Mic size={18} />,
  },
];

interface DesktopRunningAppsEventDetail {
  appIds: string[];
}

function isDesktopRunningAppsEvent(
  event: Event
): event is CustomEvent<DesktopRunningAppsEventDetail> {
  return event instanceof CustomEvent;
}

function isOtaUpdateEvent(event: Event): event is CustomEvent<{ available?: boolean }> {
  return event instanceof CustomEvent;
}

function invokeDesktopOpen(appId: string): void {
  globalThis.dispatchEvent(new CustomEvent("kryos:desktop-open-app", { detail: { appId } }));
}

export default function Dock(): JSX.Element {
  const {
    windows,
    openWindow,
    focusWindow,
  } = useShellWindowState();

  const [hoveredTarget, setHoveredTarget] = useState<string | null>(null);
  const [desktopOpenApps, setDesktopOpenApps] = useState<string[]>([]);
  const [otaUpdateAvailable, setOtaUpdateAvailable] = useState(false);

  useEffect(() => {
    const listener = (event: Event): void => {
      if (!isDesktopRunningAppsEvent(event)) {
        return;
      }
      setDesktopOpenApps(Array.isArray(event.detail?.appIds) ? event.detail.appIds : []);
    };

    globalThis.addEventListener("kryos:desktop-running-apps", listener);
    return () => {
      globalThis.removeEventListener("kryos:desktop-running-apps", listener);
    };
  }, []);

  useEffect(() => {
    const listener = (event: Event): void => {
      if (!isOtaUpdateEvent(event)) {
        return;
      }
      setOtaUpdateAvailable(Boolean(event.detail?.available));
    };
    globalThis.addEventListener("kryos:ota-update-available", listener);
    return () => {
      globalThis.removeEventListener("kryos:ota-update-available", listener);
    };
  }, []);

  const openPanelsById = useMemo(() => {
    return new Set(windows.filter((windowRecord) => windowRecord.open).map((windowRecord) => windowRecord.id));
  }, [windows]);

  const onActivateItem = (item: DockItem): void => {
    if (item.kind === "action") {
      if (item.target === "voice-bar") {
        globalThis.dispatchEvent(new CustomEvent("kryos:toggle-voice-bar"));
      }
      return;
    }

    if (item.kind === "desktop-app") {
      invokeDesktopOpen(item.target);
      return;
    }

    const existing = windows.find((windowRecord) => windowRecord.id === item.target);
    if (existing?.open) {
      focusWindow(item.target);
      return;
    }
    openWindow(item.target);
  };

  const isItemActive = (item: DockItem): boolean => {
    if (item.kind === "action") {
      return false;
    }
    if (item.kind === "desktop-app") {
      return desktopOpenApps.includes(item.target);
    }
    return openPanelsById.has(item.target);
  };

  return (
    <div
      aria-label="Application Dock"
      style={{
        position: "fixed",
        left: "50%",
        bottom: 10,
        transform: "translateX(-50%)",
        zIndex: 11000,
        width: "min(92vw, 760px)",
        overflowX: "auto",
        paddingBottom: 2,
      }}
    >
      <div
        style={{
          margin: "0 auto",
          display: "inline-flex",
          alignItems: "flex-end",
          gap: 8,
          background: "rgba(22,22,24,0.76)",
          border: "1px solid rgba(58,58,60,0.72)",
          borderRadius: 18,
          backdropFilter: "blur(18px)",
          WebkitBackdropFilter: "blur(18px)",
          padding: "8px 10px",
          minWidth: "max-content",
        }}
      >
        {DOCK_ITEMS.map((item) => {
          const active = isItemActive(item);
          const hovered = hoveredTarget === item.target;
          const scale = hovered ? 1.22 : 1;
          const iconContainerSize = hovered ? 54 : 46;

          return (
            <button
              key={item.id}
              type="button"
              aria-label={item.label}
              title={item.label}
              onMouseEnter={() => setHoveredTarget(item.target)}
              onMouseLeave={() => setHoveredTarget(null)}
              onFocus={() => setHoveredTarget(item.target)}
              onBlur={() => setHoveredTarget((current) => (current === item.target ? null : current))}
              onClick={() => onActivateItem(item)}
              style={{
                border: "none",
                background: "none",
                color: "#F2F2F7",
                cursor: "pointer",
                padding: "0 2px",
                fontFamily: FONT,
                minWidth: 60,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 4,
              }}
            >
              <span
                style={{
                  position: "relative",
                  width: iconContainerSize,
                  height: iconContainerSize,
                  borderRadius: 14,
                  border: active ? "1px solid rgba(10,132,255,0.8)" : "1px solid rgba(72,72,74,0.72)",
                  background: active ? "rgba(10,132,255,0.22)" : "rgba(44,44,46,0.84)",
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  transform: `scale(${scale})`,
                  transition: "transform 140ms ease, width 140ms ease, height 140ms ease, background 140ms ease, border-color 140ms ease",
                  willChange: "transform",
                }}
              >
                {item.icon}
                {item.target === "software-update" && otaUpdateAvailable && (
                  <span
                    style={{
                      position: "absolute",
                      top: 4,
                      right: 4,
                      width: 10,
                      height: 10,
                      borderRadius: "50%",
                      background: "#F97316",
                      border: "1px solid rgba(255,255,255,0.8)",
                    }}
                  />
                )}
              </span>
              <span
                style={{
                  fontSize: 10,
                  color: "#D1D1D6",
                  lineHeight: 1,
                  whiteSpace: "nowrap",
                }}
              >
                {item.label}
              </span>
              <span
                aria-hidden="true"
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: "50%",
                  background: active ? "#F2F2F7" : "transparent",
                  transition: "background 120ms ease",
                }}
              />
            </button>
          );
        })}
      </div>
    </div>
  );
}
