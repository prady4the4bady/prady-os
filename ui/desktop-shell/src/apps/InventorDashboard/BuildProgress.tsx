

interface InventorStatus {
  loop_active: boolean;
  current_phase: string;
  active_project: unknown;
  completed_projects: number;
  pending_proposal: unknown;
  last_scan_ts: string;
}

interface BuildProgressProps {
  status: InventorStatus;
  onStop: () => void;
}

const AGENTS = ["architect", "developer", "qa", "documenter", "verifier"];

const PHASE_LABELS: Record<string, string> = {
  idle: "Idle",
  researching: "Researching problems...",
  proposing: "Generating proposal...",
  awaiting_approval: "Awaiting your decision",
  building: "Building project...",
  verifying: "Verifying cold start...",
  releasing: "Releasing to GitHub...",
};

function phaseIndex(phase: string): number {
  const map: Record<string, number> = {
    researching: -1,
    proposing: -1,
    awaiting_approval: -1,
    building: 0,
    verifying: 3,
    releasing: 4,
  };
  return map[phase] ?? -1;
}

export default function BuildProgress({ status, onStop }: Readonly<BuildProgressProps>) {
  const currentAgentIdx = phaseIndex(status.current_phase);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
        <div
          style={{
            width: 10,
            height: 10,
            borderRadius: "50%",
            background: status.loop_active ? "#1f9d55" : "#ef4444",
          }}
        />
        <span style={{ fontSize: 13, fontWeight: 600 }}>
          {PHASE_LABELS[status.current_phase] ?? status.current_phase}
        </span>
        <div style={{ flex: 1 }} />
        <button
          type="button"
          onClick={onStop}
          style={{
            background: "#fee2e2",
            color: "#b91c1c",
            border: "1px solid #fecaca",
            borderRadius: 8,
            padding: "4px 12px",
            fontSize: 12,
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Stop Loop
        </button>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap" }}>
        {AGENTS.map((agent, idx) => {
          let bg = "#f3f4f6";
          let border = "#e5e7eb";
          let label = "Pending";

          if (idx < currentAgentIdx) {
            bg = "#dcfce7";
            border = "#86efac";
            label = "Complete";
          } else if (idx === currentAgentIdx) {
            bg = "#dbeafe";
            border = "#60a5fa";
            label = "Running";
          }

          return (
            <div
              key={agent}
              style={{
                flex: 1,
                minWidth: 80,
                padding: "10px 8px",
                borderRadius: 10,
                background: bg,
                border: `1px solid ${border}`,
                textAlign: "center",
              }}
            >
              <div style={{ fontSize: 11, fontWeight: 700, color: "#374151", marginBottom: 2, textTransform: "capitalize" }}>
                {agent}
              </div>
              <div style={{ fontSize: 10, color: "#6b7280" }}>{label}</div>
            </div>
          );
        })}
      </div>

      <div
        style={{
          border: "1px solid #dbe2ee",
          borderRadius: 12,
          background: "#ffffff",
          padding: 16,
          fontSize: 13,
          color: "#4b5563",
          lineHeight: 1.6,
        }}
      >
        <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 14 }}>Phase Timeline</div>
        <div style={{ fontSize: 12, color: "#6b7280" }}>
          <div>Loop active: {status.loop_active ? "Yes" : "No"}</div>
          <div>Current phase: {status.current_phase}</div>
          <div>Projects completed: {status.completed_projects}</div>
          {status.last_scan_ts && <div>Last scan: {new Date(status.last_scan_ts).toLocaleString()}</div>}
        </div>
      </div>
    </div>
  );
}
