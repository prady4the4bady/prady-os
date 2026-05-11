import { useState } from "react";
import { useHealthStatus } from "../../hooks/useHealthStatus";
import type { HealthStatus } from "../../types";

const STATUS_LABEL: Record<HealthStatus, string> = {
  healthy:  "Kryos AI",
  degraded: "Kryos AI",
  down:     "Kryos AI",
};

export default function AiStatus() {
  const { status, refresh } = useHealthStatus();
  const [panelOpen, setPanelOpen] = useState(false);

  return (
    <div style={{ position: "relative" }}>
      <button
        className="ai-status"
        onClick={() => { setPanelOpen((v) => !v); refresh(); }}
        style={{ background: "none", border: "none", cursor: "pointer", color: "inherit" }}
      >
        <span className={`ai-status__dot ai-status__dot--${status.status}`} />
        <span>{STATUS_LABEL[status.status]}</span>
      </button>

      {panelOpen && (
        <div className="ai-panel glass">
          <div className="ai-panel__row">
            <span className="ai-panel__label">Status</span>
            <span style={{ textTransform: "capitalize" }}>{status.status}</span>
          </div>
          <div className="ai-panel__row">
            <span className="ai-panel__label">Model</span>
            <span>{status.active_model ?? "—"}</span>
          </div>
          <div className="ai-panel__row">
            <span className="ai-panel__label">Available</span>
            <span>{status.model_count}</span>
          </div>
        </div>
      )}
    </div>
  );
}
