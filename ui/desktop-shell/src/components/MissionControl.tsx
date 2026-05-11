import { AnimatePresence, motion } from "framer-motion";
import type { WindowItem } from "../types";

interface Props {
  windows: WindowItem[];
  onBringToFront: (id: string) => void;
  onClose: () => void;
}

export function MissionControl({ windows, onBringToFront, onClose }: Readonly<Props>) {
  const visible = windows.filter((w) => !w.minimized);

  return (
    <AnimatePresence>
      <motion.div
        key="mission-control"
        className="absolute inset-0 z-[80] flex flex-col"
        style={{ backgroundColor: "rgba(0,0,0,0.4)", backdropFilter: "blur(4px)" }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.22 }}
        onClick={(event) => {
          if (event.target === event.currentTarget) {
            onClose();
          }
        }}
      >
        <div className="flex-1 p-12 pt-16 overflow-auto">
          <div
            className="grid gap-4"
            style={{ gridTemplateColumns: "repeat(auto-fill, minmax(300px,1fr))" }}
          >
            {visible.map((win) => (
              <motion.button
                key={win.id}
                layoutId={`window-${win.id}`}
                className="rounded-2xl overflow-hidden shadow-xl cursor-pointer text-left focus:outline-none focus:ring-2 focus:ring-blue-400"
                style={{ aspectRatio: "16/10", background: "rgba(255,255,255,0.15)" }}
                initial={{ scale: 0.9, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0.9, opacity: 0 }}
                transition={{ type: "spring", stiffness: 300, damping: 25 }}
                onClick={(event) => {
                  event.stopPropagation();
                  onBringToFront(win.id);
                  onClose();
                }}
              >
                {/* Mini window chrome */}
                <div className="h-6 px-2 flex items-center gap-1.5 bg-white/20">
                  <span className="w-2.5 h-2.5 rounded-full bg-red-400/80" />
                  <span className="w-2.5 h-2.5 rounded-full bg-yellow-400/80" />
                  <span className="w-2.5 h-2.5 rounded-full bg-green-400/80" />
                  <span className="ml-2 text-[10px] truncate opacity-70">{win.title}</span>
                </div>
                <div className="flex items-center justify-center h-[calc(100%-24px)] opacity-30 text-4xl">
                  {win.icon}
                </div>
              </motion.button>
            ))}
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
