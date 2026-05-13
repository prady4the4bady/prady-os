import { useCallback } from "react";

export interface Proposal {
  proposal_id: string;
  problem_summary: string;
  why_it_matters: string;
  what_to_build: string;
  tools: { name: string; license: string; purpose: string }[];
  time_estimate_hrs: number;
  deliverables: string[];
  confidence_level: string;
  honest_caveats: string[];
  created_ts: string;
}

interface ProposalCardProps {
  proposals: Proposal[];
  onRefresh: () => void;
}

function confidenceColor(level: string): string {
  switch (level) {
    case "high": return "#1f9d55";
    case "medium": return "#f59e0b";
    case "experimental": return "#ea580c";
    default: return "#6b7280";
  }
}

export default function ProposalCardView({ proposals, onRefresh }: Readonly<ProposalCardProps>) {
  const handleApprove = useCallback(async (proposalId: string) => {
    await fetch(`/api/inventor/proposals/${proposalId}/approve`, { method: "POST" });
    onRefresh();
  }, [onRefresh]);

  const handleReject = useCallback(async (proposalId: string) => {
    await fetch(`/api/inventor/proposals/${proposalId}/reject`, { method: "POST" });
    onRefresh();
  }, [onRefresh]);

  if (proposals.length === 0) {
    return (
      <div style={{ textAlign: "center", padding: 40, color: "#6b7280", fontSize: 14 }}>
        No pending proposals. The inventor loop will generate new proposals as it discovers problems.
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      {proposals.map((proposal) => (
        <div
          key={proposal.proposal_id}
          style={{
            border: "1px solid #dbe2ee",
            borderRadius: 16,
            background: "#ffffff",
            padding: 20,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
            <div>
              <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 4 }}>PROBLEM</div>
              <div style={{ fontSize: 15, fontWeight: 600, lineHeight: 1.4 }}>{proposal.problem_summary}</div>
            </div>
            <span
              style={{
                fontSize: 11,
                fontWeight: 700,
                borderRadius: 999,
                padding: "3px 10px",
                background: `${confidenceColor(proposal.confidence_level)}22`,
                color: confidenceColor(proposal.confidence_level),
                whiteSpace: "nowrap",
              }}
            >
              {proposal.confidence_level.toUpperCase()}
            </span>
          </div>

          <div style={{ fontSize: 13, color: "#4b5563", marginBottom: 12, lineHeight: 1.6 }}>
            <strong>Why it matters:</strong> {proposal.why_it_matters}
          </div>

          <div style={{ fontSize: 13, color: "#4b5563", marginBottom: 12, lineHeight: 1.6 }}>
            <strong>What to build:</strong> {proposal.what_to_build}
          </div>

          {proposal.tools.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 6 }}>TOOLS</div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {proposal.tools.map((tool) => (
                  <span
                    key={tool.name}
                    style={{
                      fontSize: 11,
                      borderRadius: 6,
                      padding: "4px 8px",
                      background: "#f3f4f6",
                      color: "#374151",
                      border: "1px solid #e5e7eb",
                    }}
                  >
                    {tool.name} <span style={{ color: "#9ca3af" }}>{tool.license}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 12 }}>
            Estimated time: <strong>{proposal.time_estimate_hrs} hours</strong>
          </div>

          {proposal.deliverables.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>DELIVERABLES</div>
              <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, color: "#4b5563", lineHeight: 1.6 }}>
                {proposal.deliverables.map((d) => <li key={d}>{d}</li>)}
              </ul>
            </div>
          )}

          {proposal.honest_caveats.length > 0 && (
            <details style={{ marginBottom: 12, fontSize: 12 }}>
              <summary style={{ cursor: "pointer", color: "#ea580c", fontWeight: 600 }}>
                What might not work
              </summary>
              <ul style={{ margin: "8px 0 0", paddingLeft: 16, color: "#6b7280", lineHeight: 1.6 }}>
                {proposal.honest_caveats.map((c) => <li key={c}>{c}</li>)}
              </ul>
            </details>
          )}

          <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
            <button
              type="button"
              onClick={() => void handleApprove(proposal.proposal_id)}
              style={{
                background: "#0a84ff",
                color: "white",
                border: "none",
                borderRadius: 10,
                padding: "10px 20px",
                fontWeight: 600,
                cursor: "pointer",
                flex: 1,
              }}
            >
              Build It
            </button>
            <button
              type="button"
              onClick={() => void handleReject(proposal.proposal_id)}
              style={{
                background: "transparent",
                color: "#6b7280",
                border: "1px solid #d7dce5",
                borderRadius: 10,
                padding: "10px 16px",
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              Not Interested
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
