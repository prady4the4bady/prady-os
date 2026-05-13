import { useCallback, useEffect, useState } from "react";
import type { Proposal } from "./ProposalCard";
import ProposalCardView from "./ProposalCard";
import BuildProgress from "./BuildProgress";
import ProjectHistory from "./ProjectHistory";

interface InventorDashboardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  layerZIndex: number;
}

type Tab = "active" | "proposals" | "history";

interface InventorStatus {
  loop_active: boolean;
  current_phase: string;
  active_project: unknown;
  completed_projects: number;
  pending_proposal: unknown;
  last_scan_ts: string;
}

interface Project {
  project_id: string;
  name: string;
  status: string;
  verified: number;
  test_pass_rate: number;
  repo_url: string;
  build_started: string;
  build_completed: string | null;
}

const FONT = "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif";

export default function InventorDashboard({ open, onOpenChange, layerZIndex }: Readonly<InventorDashboardProps>): JSX.Element | null {
  const [tab, setTab] = useState<Tab>("active");
  const [status, setStatus] = useState<InventorStatus | null>(null);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);

  const fetchStatus = useCallback(async () => {
    try {
      const r = await fetch("/api/inventor/status");
      if (r.ok) setStatus((await r.json()) as InventorStatus);
    } catch { /* ignore */ }
  }, []);

  const fetchProposals = useCallback(async () => {
    try {
      const r = await fetch("/api/inventor/proposals");
      if (r.ok) setProposals(await r.json());
    } catch { /* ignore */ }
  }, []);

  const fetchProjects = useCallback(async () => {
    try {
      const r = await fetch("/api/inventor/projects");
      if (r.ok) setProjects((await r.json()) as Project[]);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (!open) return;
    void fetchStatus();
    void fetchProposals();
    void fetchProjects();
    const timer = setInterval(() => {
      void fetchStatus();
      void fetchProposals();
      void fetchProjects();
    }, 5000);
    return () => clearInterval(timer);
  }, [open, fetchStatus, fetchProposals, fetchProjects]);

  const handleStart = useCallback(async () => {
    await fetch("/api/inventor/start", { method: "POST" });
    void fetchStatus();
  }, [fetchStatus]);

  const handleStop = useCallback(async () => {
    await fetch("/api/inventor/stop", { method: "POST" });
    void fetchStatus();
  }, [fetchStatus]);

  if (!open) return null;

  const tabs: { id: Tab; label: string }[] = [
    { id: "active", label: "Active" },
    { id: "proposals", label: "Proposals" },
    { id: "history", label: "History" },
  ];

  return (
    <dialog
      open
      aria-label="Prax Inventor Dashboard"
      style={{
        position: "fixed",
        top: "8vh",
        left: "50%",
        transform: "translateX(-50%)",
        margin: 0,
        padding: 0,
        width: "min(900px, calc(100vw - 32px))",
        maxHeight: "84vh",
        overflow: "hidden",
        background: "linear-gradient(180deg, #f7f8fa 0%, #eef0f4 100%)",
        border: "1px solid #d5d9e2",
        borderRadius: 20,
        boxShadow: "0 24px 80px rgba(15,23,42,0.25)",
        zIndex: layerZIndex,
        fontFamily: FONT,
        color: "#1f2937",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "16px 20px",
          borderBottom: "1px solid #dde2ea",
          background: "rgba(255,255,255,0.8)",
        }}
      >
        <div>
          <div style={{ fontSize: 20, fontWeight: 700, letterSpacing: -0.3 }}>Prax Inventor Engine</div>
          <div style={{ marginTop: 4, fontSize: 13, color: "#52607a" }}>
            Autonomous project discovery and building
            {status?.loop_active ? " — Loop active" : " — Loop stopped"}
          </div>
        </div>
        <button
          type="button"
          onClick={() => onOpenChange(false)}
          style={{
            border: "1px solid #d7dce5",
            background: "#fff",
            borderRadius: 10,
            padding: "6px 10px",
            cursor: "pointer",
            color: "#374151",
          }}
        >
          Close
        </button>
      </div>

      <div style={{ padding: "10px 20px 0", display: "flex", gap: 8 }}>
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            style={{
              padding: "8px 16px",
              border: "none",
              borderRadius: "10px 10px 0 0",
              background: tab === t.id ? "#fff" : "transparent",
              fontWeight: tab === t.id ? 700 : 500,
              color: tab === t.id ? "#0a84ff" : "#6b7280",
              cursor: "pointer",
              borderBottom: tab === t.id ? "2px solid #0a84ff" : "2px solid transparent",
            }}
          >
            {t.label}
          </button>
        ))}

        <div style={{ flex: 1 }} />

        {status && (
          <div style={{ fontSize: 12, color: "#6b7280", paddingTop: 10 }}>
            {status.completed_projects} projects delivered
          </div>
        )}
      </div>

      <div style={{ padding: 16, overflowY: "auto", maxHeight: "calc(84vh - 120px)" }}>
        {status?.loop_active === false && tab === "active" && (
          <div style={{ textAlign: "center", padding: 40 }}>
            <div style={{ fontSize: 14, color: "#6b7280", marginBottom: 16 }}>
              The inventor loop is currently stopped. Start it to begin autonomous research and building.
            </div>
            <button
              type="button"
              onClick={() => void handleStart()}
              style={{
                background: "#0a84ff",
                color: "white",
                border: "none",
                borderRadius: 10,
                padding: "10px 24px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Start Inventor Loop
            </button>
          </div>
        )}

        {tab === "active" && status?.loop_active && <BuildProgress status={status} onStop={handleStop} />}
        {tab === "proposals" && <ProposalCardView proposals={proposals} onRefresh={fetchProposals} />}
        {tab === "history" && <ProjectHistory projects={projects} />}
      </div>
    </dialog>
  );
}
