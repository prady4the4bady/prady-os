import { useState } from "react";
import MenuBar from "./components/MenuBar/MenuBar";
import Dock from "./components/Dock/Dock";
import Spotlight from "./components/Spotlight/Spotlight";
import CommandBar from "./components/CommandBar/CommandBar";
import NotificationQueue from "./components/Notifications/NotificationQueue";
import { useWallpaper } from "./hooks/useWallpaper";
import { useKeyboard } from "./hooks/useKeyboard";
import { useNotifications } from "./hooks/useNotifications";

export default function App() {
  const wallpaper = useWallpaper();
  const [spotlightOpen, setSpotlightOpen] = useState(false);
  const [commandBarOpen, setCommandBarOpen] = useState(false);
  const { notifications, dismiss } = useNotifications();

  // Keyboard shortcuts
  useKeyboard([
    // Cmd+Space / Super+Space → Spotlight
    { key: " ", modifiers: ["meta"], handler: () => setSpotlightOpen((v) => !v) },
    // Ctrl+Space fallback (Linux without Super)
    { key: " ", modifiers: ["ctrl"], handler: () => setSpotlightOpen((v) => !v) },
    // Ctrl+R → Kryos Command Bar
    { key: "r", modifiers: ["ctrl"], handler: () => setCommandBarOpen((v) => !v) },
    // Escape closes everything
    {
      key: "Escape",
      modifiers: [],
      handler: () => {
        setSpotlightOpen(false);
        setCommandBarOpen(false);
      },
    },
  ]);

  const desktopStyle: React.CSSProperties = wallpaper
    ? {
        backgroundImage: `url("${wallpaper}")`,
        backgroundSize: "cover",
        backgroundPosition: "center",
      }
    : {};

  return (
    <div className="desktop" style={desktopStyle}>
      {/* ── Fixed top bar ──────────────────────────────────────── */}
      <MenuBar />

      {/* ── Slide-down command bar (below menu bar) ────────────── */}
      {commandBarOpen && (
        <CommandBar onClose={() => setCommandBarOpen(false)} />
      )}

      {/* ── Spotlight modal ────────────────────────────────────── */}
      {spotlightOpen && (
        <Spotlight onClose={() => setSpotlightOpen(false)} />
      )}

      {/* ── Toast notifications (top-right) ───────────────────── */}
      <NotificationQueue notifications={notifications} onDismiss={dismiss} />

      {/* ── Fixed bottom dock ──────────────────────────────────── */}
      <Dock />
    </div>
  );
}
