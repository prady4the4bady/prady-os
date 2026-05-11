import { invoke } from "@tauri-apps/api/core";
import type { DockAppConfig } from "../../types";

interface Props {
  app: DockAppConfig;
  bouncing: boolean;
  onLaunch: (app: DockAppConfig) => void;
}

export default function DockItem({ app, bouncing, onLaunch }: Readonly<Props>) {
  const handleClick = () => {
    onLaunch(app);
    invoke("launch_dock_app", { app: app.id }).catch((err) => {
      console.error(`Failed to launch ${app.label}:`, err);
    });
  };

  return (
    <button
      type="button"
      aria-label={`Launch ${app.label}`}
      className={`dock-item${bouncing ? " dock-item--bouncing" : ""}`}
      onClick={handleClick}
    >
      <div className="dock-item__icon">{app.icon}</div>
      <span className="dock-item__label">{app.label}</span>
    </button>
  );
}
