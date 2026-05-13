import { AnimatePresence, motion, useMotionValue, useSpring, useTransform } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import type { AppId } from "../types";

interface DockItem {
  appId: AppId;
  label: string;
  icon: string;
}

interface Props {
  runningApps: AppId[];
  onOpenApp: (appId: AppId) => void;
}

export const DOCK_APPS: DockItem[] = [
  { appId: "terminal", label: "Terminal", icon: "💻" },
  { appId: "browser", label: "Browser", icon: "🌐" },
  { appId: "files", label: "Files", icon: "📁" },
  { appId: "assistant", label: "AI Assistant", icon: "🤖" },
  { appId: "settings", label: "Settings", icon: "⚙️" },
  { appId: "activity", label: "Activity Monitor", icon: "📊" },
  { appId: "models", label: "Model Manager", icon: "🧠" },
  { appId: "screen", label: "Screen Viewer", icon: "🖥️" },
  { appId: "lumyn", label: "Lumyn Console", icon: "⚡" },
  { appId: "desktop-agent", label: "Desktop Agent", icon: "🤖" },
  { appId: "process-viewer", label: "Processes", icon: "🖥" },
  { appId: "memory-browser", label: "Memory", icon: "🗄️" },
  { appId: "inventor-engine", label: "Inventor", icon: "🧠" },
];

const PINNED_COUNT = 9;
const ICON_SIZE = 52;
const ICON_GAP = 8;
const DISTANCE_MAX = 120;
const SCALE_MAX = 1.6;

interface DockIconProps {
  item: DockItem;
  running: boolean;
  onOpen: () => void;
  mouseX: ReturnType<typeof useMotionValue<number>>;
  onContextMenu: (appId: AppId, x: number, y: number) => void;
}

function DockIcon({ item, running, onOpen, mouseX, onContextMenu }: Readonly<DockIconProps>) {
  const ref = useRef<HTMLButtonElement>(null);
  const [bouncing, setBouncing] = useState(false);

  const rawScale = useTransform(mouseX, (mx: number) => {
    if (!ref.current) return 1;
    const rect = ref.current.getBoundingClientRect();
    const center = rect.left + rect.width / 2;
    const dist = Math.abs(mx - center);
    if (dist > DISTANCE_MAX) return 1;
    const t = 1 - dist / DISTANCE_MAX;
    return 1 + (SCALE_MAX - 1) * t * t;
  });

  const scale = useSpring(rawScale, { stiffness: 280, damping: 22 });

  function handleClick() {
    setBouncing(true);
    globalThis.setTimeout(() => setBouncing(false), 600);
    onOpen();
  }

  return (
    <motion.button
      ref={ref}
      data-testid={`dock-app-${item.appId}`}
      title={item.label}
      className="relative flex flex-col items-center justify-end focus:outline-none"
      style={{ width: ICON_SIZE, height: ICON_SIZE + 20 }}
      onClick={handleClick}
      onContextMenu={(e) => {
        e.preventDefault();
        onContextMenu(item.appId, e.clientX, e.clientY);
      }}
    >
      <motion.span
        className={`w-full rounded-2xl bg-white/80 dark:bg-black/30 flex items-center justify-center text-2xl shadow-md origin-bottom ${bouncing ? "animate-dock-bounce" : ""}`}
        style={{ scale, height: ICON_SIZE, aspectRatio: "1 / 1" }}
      >
        {item.icon}
      </motion.span>
      <span className="text-[10px] mt-0.5 text-white/90 drop-shadow leading-none truncate max-w-[60px]">
        {item.label}
      </span>
      {running ? (
        <span className="absolute bottom-[14px] left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-white/80 shadow" />
      ) : null}
    </motion.button>
  );
}

interface ContextMenu {
  appId: AppId;
  x: number;
  y: number;
}

export function Dock({ runningApps, onOpenApp }: Readonly<Props>) {
  const mouseX = useMotionValue(Infinity);
  const [contextMenu, setContextMenu] = useState<ContextMenu | null>(null);
  const dockRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const dock = dockRef.current;
    if (!dock) {
      return;
    }

    const handlePointerMove = (event: PointerEvent): void => {
      mouseX.set(event.clientX);
    };

    const handlePointerLeave = (): void => {
      mouseX.set(Infinity);
    };

    dock.addEventListener("pointermove", handlePointerMove);
    dock.addEventListener("pointerleave", handlePointerLeave);
    return () => {
      dock.removeEventListener("pointermove", handlePointerMove);
      dock.removeEventListener("pointerleave", handlePointerLeave);
    };
  }, [mouseX]);

  return (
    <>
      <AnimatePresence>
        {contextMenu ? (
          <motion.div
            key="ctx"
            className="fixed z-[100] rounded-xl shadow-xl border border-black/10 bg-white/95 backdrop-blur-lg py-1 w-48"
            style={{ left: contextMenu.x, top: contextMenu.y - 140 }}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.12 }}
          >
            {["Open", "Keep in Dock", "Remove from Dock"].map((action) => (
              <button
                key={action}
                className="w-full text-left px-4 py-1.5 text-sm hover:bg-blue-500 hover:text-white rounded-md mx-0.5"
                onClick={() => {
                  if (action === "Open") onOpenApp(contextMenu.appId);
                  setContextMenu(null);
                }}
              >
                {action}
              </button>
            ))}
          </motion.div>
        ) : null}
      </AnimatePresence>

      {contextMenu ? (
        <button
          type="button"
          aria-label="Close dock context menu"
          className="fixed inset-0 z-[99]"
          style={{ background: "transparent", border: "none", padding: 0 }}
          onClick={() => setContextMenu(null)}
        />
      ) : null}

      <div
        ref={dockRef}
        className="pointer-events-none absolute bottom-3 left-0 right-0 flex justify-center z-50"
      >
        <div
          className="glass pointer-events-auto rounded-[2rem] px-4 py-2 flex items-end"
          style={{ gap: ICON_GAP }}
        >
          {DOCK_APPS.slice(0, PINNED_COUNT).map((app) => (
            <DockIcon
              key={app.appId}
              item={app}
              running={runningApps.includes(app.appId)}
              onOpen={() => onOpenApp(app.appId)}
              mouseX={mouseX}
              onContextMenu={(id, x, y) => setContextMenu({ appId: id, x, y })}
            />
          ))}

          <svg width="1" height="52" className="opacity-30 mx-1" aria-hidden="true">
            <line x1="0.5" y1="4" x2="0.5" y2="48" stroke="white" strokeWidth="1" />
          </svg>

          {DOCK_APPS.slice(PINNED_COUNT).map((app) => (
            <DockIcon
              key={app.appId}
              item={app}
              running={runningApps.includes(app.appId)}
              onOpen={() => onOpenApp(app.appId)}
              mouseX={mouseX}
              onContextMenu={(id, x, y) => setContextMenu({ appId: id, x, y })}
            />
          ))}
        </div>
      </div>

      <style>{`
        @keyframes dock-bounce {
          0%, 100% { transform: scaleY(1) translateY(0); }
          30%       { transform: scaleY(1.15) translateY(-8px); }
          60%       { transform: scaleY(0.92) translateY(2px); }
          80%       { transform: scaleY(1.06) translateY(-4px); }
        }
        .animate-dock-bounce { animation: dock-bounce 0.55s ease; }
      `}</style>
    </>
  );
}
