import { useState } from "react";
import DockItem from "./DockItem";
import type { DockAppConfig } from "../../types";

/** Default dock application list – exported for unit testing. */
export const DOCK_APPS: DockAppConfig[] = [
  { id: "terminal",    label: "Terminal",    icon: "🖥️" },
  { id: "files",       label: "Files",       icon: "📁" },
  { id: "browser",     label: "Browser",     icon: "🌐" },
  { id: "kryos_tasks", label: "Kryos Tasks", icon: "🤖" },
  { id: "settings",    label: "Settings",    icon: "⚙️" },
];

export default function Dock() {
  const [bouncing, setBouncing] = useState<string | null>(null);

  const handleLaunch = (app: DockAppConfig) => {
    // Trigger bounce animation
    setBouncing(app.id);
    setTimeout(() => setBouncing(null), 1_600);
  };

  return (
    <div className="dock-wrapper glass">
      <div className="dock">
        {DOCK_APPS.map((app) => (
          <DockItem
            key={app.id}
            app={app}
            bouncing={bouncing === app.id}
            onLaunch={handleLaunch}
          />
        ))}
      </div>
    </div>
  );
}
