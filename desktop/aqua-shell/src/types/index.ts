// ── Shared TypeScript types for aqua-shell ──────────────────────────────────

export type HealthStatus = "healthy" | "degraded" | "down";

export interface GatewayStatus {
  status: HealthStatus;
  active_model: string | null;
  model_count: number;
}

export interface Notification {
  id: string;
  title: string;
  body: string;
  icon: string | null;
  duration_ms: number;
}

export interface TaskSubmitResult {
  task_id: string;
}

export type DockAppId =
  | "terminal"
  | "files"
  | "browser"
  | "kryos_tasks"
  | "settings";

export interface DockAppConfig {
  id: DockAppId;
  label: string;
  icon: string; // emoji fallback
}

export type NotifAction =
  | { type: "ADD"; notif: Notification }
  | { type: "DISMISS"; id: string }
  | { type: "CLEAR_ALL" };
