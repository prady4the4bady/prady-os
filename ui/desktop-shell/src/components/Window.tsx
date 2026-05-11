import { motion } from "framer-motion";
import type { ReactNode } from "react";

export interface WindowProps {
  id?: string;
  title: string;
  children: ReactNode;
  onClose: () => void;
  onMinimize: () => void;
  onMaximize: () => void;
  focused?: boolean;
}

export function Window({ id, title, children, onClose, onMinimize, onMaximize, focused = true }: Readonly<WindowProps>) {
  return (
    <motion.div
      data-window-id={id}
      className="flex flex-col rounded-xl overflow-hidden"
      style={{
        boxShadow: focused
          ? "0 22px 70px rgba(0,0,0,0.56)"
          : "0 8px 32px rgba(0,0,0,0.28)",
        background: "rgba(30,30,30,0.92)",
        backdropFilter: "blur(32px) saturate(160%)",
      }}
      initial={{ scale: 0.95, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      exit={{ scale: 0.95, opacity: 0 }}
      transition={{ type: "spring", stiffness: 320, damping: 28, mass: 0.8 }}
    >
      {/* Title bar */}
      <div
        className="flex items-center gap-2 px-3 py-2 select-none shrink-0"
        style={{
          background: focused
            ? "rgba(50,50,50,0.9)"
            : "rgba(40,40,40,0.8)",
          borderBottom: "1px solid rgba(255,255,255,0.08)",
        }}
      >
        {/* Traffic-light buttons */}
        <div className="flex items-center gap-2">
          <button
            aria-label="Close"
            onClick={onClose}
            className="w-3 h-3 rounded-full flex items-center justify-center group"
            style={{ background: "#FF5F57" }}
          >
            <span className="opacity-0 group-hover:opacity-100 text-[8px] font-bold text-black leading-none">✕</span>
          </button>
          <button
            aria-label="Minimize"
            onClick={onMinimize}
            className="w-3 h-3 rounded-full flex items-center justify-center group"
            style={{ background: "#FEBC2E" }}
          >
            <span className="opacity-0 group-hover:opacity-100 text-[8px] font-bold text-black leading-none">−</span>
          </button>
          <button
            aria-label="Maximize"
            onClick={onMaximize}
            className="w-3 h-3 rounded-full flex items-center justify-center group"
            style={{ background: "#28C840" }}
          >
            <span className="opacity-0 group-hover:opacity-100 text-[8px] font-bold text-black leading-none">+</span>
          </button>
        </div>

        {/* Window title */}
        <span
          className="flex-1 text-center text-xs font-medium truncate"
          style={{ color: focused ? "rgba(255,255,255,0.85)" : "rgba(255,255,255,0.4)" }}
        >
          {title}
        </span>

        {/* Spacer to balance traffic lights */}
        <div className="w-[52px] shrink-0" />
      </div>

      {/* Content area with frosted glass sidebar strip */}
      <div className="flex flex-1 min-h-0">
        {/* Frosted glass sidebar strip */}
        <div
          className="w-12 shrink-0 border-r"
          style={{
            background: "rgba(255,255,255,0.06)",
            backdropFilter: "blur(8px)",
            borderColor: "rgba(255,255,255,0.08)",
          }}
        />

        {/* Main content */}
        <div className="flex-1 min-w-0 overflow-auto">
          {children}
        </div>
      </div>
    </motion.div>
  );
}
