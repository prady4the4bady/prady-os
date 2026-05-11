import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { useClickOutside } from "../hooks/useClickOutside";

const SWARM_BASE =
  (import.meta.env as Record<string, string>)
    .VITE_SWARM_URL ?? "http://localhost:8000";

interface Notification {
  id: string;
  icon: string;
  title: string;
  body: string;
  ts: number;
}

interface Props {
  open: boolean;
  onClose: () => void;
}

export function NotificationCentre({ open, onClose }: Readonly<Props>) {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const panelRef = useRef<HTMLDivElement>(null);
  useClickOutside(panelRef, onClose, open);

  // WebSocket subscription
  useEffect(() => {
    if (!open) return;
    let ws: WebSocket | null = null;
    try {
      ws = new WebSocket("ws://localhost:8765");
      ws.onmessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data as string) as {
            topic?: string;
            title?: string;
            body?: string;
            icon?: string;
          };
          if (data.topic === "notifications") {
            const n: Notification = {
              id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
              icon: data.icon ?? "🔔",
              title: data.title ?? "Notification",
              body: data.body ?? "",
              ts: Date.now(),
            };
            setNotifications((prev) => [n, ...prev].slice(0, 50));
            // Persist to memory store
            void fetch(`${SWARM_BASE}/api/memory/store`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ content: `${n.title}: ${n.body}`, tags: ["notification"], agent_id: "ui" }),
            });
          }
        } catch {
          // ignore malformed messages
        }
      };
    } catch {
      // WebSocket may not be available in test/dev
    }
    return () => {
      ws?.close();
    };
  }, [open]);

  function dismiss(id: string) {
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  }

  function clearAll() {
    setNotifications([]);
  }

  return (
    <AnimatePresence>
      {open ? (
        <motion.aside
          ref={panelRef}
          className="absolute right-0 top-7 h-[calc(100%-7rem)] w-80 glass rounded-l-2xl z-[60] flex flex-col shadow-2xl"
          initial={{ x: 320, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 320, opacity: 0 }}
          transition={{ type: "spring", stiffness: 350, damping: 30 }}
        >
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/20">
            <span className="font-semibold text-sm">Notifications</span>
            <button className="text-xs opacity-60 hover:opacity-100" onClick={clearAll}>
              Clear All
            </button>
          </div>

          <div className="flex-1 overflow-auto p-2 space-y-2">
            {notifications.length === 0 ? (
              <div className="text-xs opacity-50 text-center pt-8">No notifications</div>
            ) : (
              notifications.map((n) => (
                <div key={n.id} className="rounded-xl bg-white/60 dark:bg-black/25 p-3 text-xs relative group">
                  <div className="flex items-start gap-2">
                    <span className="text-base">{n.icon}</span>
                    <div className="flex-1 min-w-0">
                      <div className="font-semibold truncate">{n.title}</div>
                      <div className="opacity-70 mt-0.5 line-clamp-2">{n.body}</div>
                      <div className="opacity-40 mt-1">
                        {new Date(n.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </div>
                    </div>
                    <button
                      aria-label="dismiss"
                      className="opacity-0 group-hover:opacity-60 hover:!opacity-100 text-lg leading-none"
                      onClick={() => dismiss(n.id)}
                    >
                      ×
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </motion.aside>
      ) : null}
    </AnimatePresence>
  );
}
