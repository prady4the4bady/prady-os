import { useEffect, useMemo, useState } from "react";
import { Layers, X } from "lucide-react";
import { useShellWindowState } from "./ShellWindowState";

const FONT = "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif";

function isTypingTarget(eventTarget: EventTarget | null): boolean {
  const element = eventTarget as HTMLElement | null;
  if (!element) {
    return false;
  }
  const tag = element.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
    return true;
  }
  return element.isContentEditable;
}

export default function WindowOverview(): JSX.Element {
  const {
    windows,
    focusWindow,
    closeWindow,
  } = useShellWindowState();

  const [overviewOpen, setOverviewOpen] = useState(false);
  const [cycleIndex, setCycleIndex] = useState(0);

  const openWindows = useMemo(
    () => windows.filter((windowRecord) => windowRecord.open).sort((a, b) => b.zIndex - a.zIndex),
    [windows]
  );

  useEffect(() => {
    if (openWindows.length === 0) {
      setCycleIndex(0);
      return;
    }
    setCycleIndex((prev) => Math.min(prev, openWindows.length - 1));
  }, [openWindows.length]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (!overviewOpen && isTypingTarget(event.target) && !(event.metaKey && event.key === "Tab")) {
        return;
      }

      const ctrlArrowUp = event.ctrlKey && event.key === "ArrowUp";
      if (ctrlArrowUp) {
        event.preventDefault();
        setOverviewOpen((prev) => !prev);
        return;
      }

      if (event.key === "Escape" && overviewOpen) {
        event.preventDefault();
        setOverviewOpen(false);
        return;
      }

      if (event.metaKey && event.key === "Tab") {
        event.preventDefault();
        if (openWindows.length === 0) {
          return;
        }

        const direction = event.shiftKey ? -1 : 1;
        const next = (cycleIndex + direction + openWindows.length) % openWindows.length;
        setCycleIndex(next);
        const nextWindow = openWindows[next];
        focusWindow(nextWindow.id);
      }
    };

    globalThis.addEventListener("keydown", onKeyDown);
    return () => {
      globalThis.removeEventListener("keydown", onKeyDown);
    };
  }, [cycleIndex, focusWindow, openWindows, overviewOpen]);

  if (!overviewOpen) {
    return <></>;
  }

  return (
    <dialog
      open
      aria-label="Window Overview"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 11500,
        margin: 0,
        border: "none",
        padding: 0,
        width: "100vw",
        height: "100vh",
        background: "rgba(0,0,0,0.38)",
        backdropFilter: "blur(8px)",
        WebkitBackdropFilter: "blur(8px)",
        fontFamily: FONT,
        color: "#F2F2F7",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "16px 20px",
        }}
      >
        <div style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          <Layers size={16} />
          <span style={{ fontWeight: 600, fontSize: 15 }}>Window Overview</span>
        </div>
        <button
          type="button"
          aria-label="Close overview"
          onClick={() => setOverviewOpen(false)}
          style={{
            border: "1px solid rgba(72,72,74,0.8)",
            borderRadius: 8,
            background: "rgba(44,44,46,0.8)",
            color: "#F2F2F7",
            padding: 6,
            cursor: "pointer",
            display: "inline-flex",
          }}
        >
          <X size={14} />
        </button>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
          gap: 14,
          padding: "0 20px 20px",
          maxHeight: "calc(100vh - 74px)",
          overflowY: "auto",
        }}
      >
        {openWindows.length === 0 && (
          <div style={{ color: "#A1A1A6", fontSize: 12 }}>No open windows to show.</div>
        )}

        {openWindows.map((windowRecord) => (
          <button
            key={windowRecord.id}
            type="button"
            aria-label={`Focus ${windowRecord.title}`}
            onClick={() => {
              focusWindow(windowRecord.id);
              setOverviewOpen(false);
            }}
            style={{
              border: windowRecord.focused
                ? "1px solid rgba(10,132,255,0.9)"
                : "1px solid rgba(72,72,74,0.75)",
              borderRadius: 14,
              background: "rgba(24,24,27,0.9)",
              textAlign: "left",
              color: "#F2F2F7",
              padding: 12,
              cursor: "pointer",
              minHeight: 150,
              display: "flex",
              flexDirection: "column",
              gap: 10,
              boxShadow: windowRecord.focused ? "0 0 0 2px rgba(10,132,255,0.3)" : "none",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 13, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {windowRecord.title}
              </span>
              {windowRecord.minimizable && (
                <button
                  type="button"
                  aria-label={`Close ${windowRecord.title}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    closeWindow(windowRecord.id);
                  }}
                  style={{
                    border: "1px solid rgba(255,69,58,0.65)",
                    borderRadius: 6,
                    background: "rgba(255,69,58,0.18)",
                    color: "#F2F2F7",
                    cursor: "pointer",
                    padding: "2px 6px",
                    fontSize: 10,
                  }}
                >
                  Close
                </button>
              )}
            </div>
            <div
              style={{
                flex: 1,
                borderRadius: 10,
                border: "1px solid rgba(58,58,60,0.6)",
                background: "linear-gradient(135deg, rgba(10,132,255,0.12), rgba(175,82,222,0.12))",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#D1D1D6",
                fontSize: 12,
              }}
            >
              {windowRecord.open ? "Open" : "Closed"}
            </div>
          </button>
        ))}
      </div>
    </dialog>
  );
}
