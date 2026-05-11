import React, { useState, useEffect, useCallback } from "react";
import { ShieldCheck } from "lucide-react";

type SubjectType = "package" | "persona" | "service";

interface PolicyGrant {
  id: string;
  subject_type: SubjectType;
  subject_id: string;
  permission: string;
  scope: string;
  expires_at: string | null;
  granted_by: string;
  created_at: string;
  active?: boolean;
}

interface PolicyAuditEntry {
  id: string;
  subject_type: string;
  subject_id: string;
  permission: string;
  action: string;
  allowed: boolean;
  reason: string;
  created_at: string;
}

interface EbpfProgram {
  name: string;
  attached_pids?: number[];
  syscall_count?: number;
  denial_count?: number;
  loaded_at: string;
}

interface EbpfProgramsResponse {
  programs?: EbpfProgram[];
}

const SENSITIVE_PERMISSIONS = [
  "network",
  "filesystem-write",
  "filesystem-read-sensitive",
  "model-activation",
  "persona-activation",
  "service-restart",
  "package-install",
  "package-remove",
  "computer-control",
  "shell-exec",
  "clipboard",
  "task-replay",
] as const;

const SUBJECT_TYPES = ["package", "persona", "service"] as const;
const SCOPES = ["global", "session", "task"] as const;

const PANEL_W = 820;
const PANEL_H = 600;

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  layerZIndex: number;
}

export default function SecurityCenter({ open, onOpenChange, layerZIndex }: Readonly<Props>): JSX.Element | null {
  const [tab, setTab] = useState<"grants" | "audit" | "inspect" | "kernel-sandbox">("grants");
  const [grants, setGrants] = useState<PolicyGrant[]>([]);
  const [audit, setAudit] = useState<PolicyAuditEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Grant form state
  const [grantSubjectType, setGrantSubjectType] = useState<SubjectType>("package");
  const [grantSubjectId, setGrantSubjectId] = useState("");
  const [grantPermission, setGrantPermission] = useState<string>(SENSITIVE_PERMISSIONS[0]);
  const [grantScope, setGrantScope] = useState<string>("global");
  const [grantLoading, setGrantLoading] = useState(false);
  const [grantMsg, setGrantMsg] = useState<string | null>(null);

  // Inspect form state
  const [inspectSubjectType, setInspectSubjectType] = useState<SubjectType>("package");
  const [inspectSubjectId, setInspectSubjectId] = useState("");
  const [inspectResult, setInspectResult] = useState<PolicyGrant[]>([]);
  const [inspectLoading, setInspectLoading] = useState(false);

  // Kernel sandbox state
  interface SandboxService {
    name: string;
    sandbox_status: "active" | "inactive" | "unknown";
    syscall_count: number;
    denial_count: number;
    last_updated: string;
  }
  const [sandboxServices, setSandboxServices] = useState<SandboxService[]>([]);
  const [sandboxLoading, setSandboxLoading] = useState(false);

  const fetchGrants = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/security/policies");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: { grants: PolicyGrant[]; total: number } = await res.json();
      setGrants(data.grants ?? []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load grants");
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchAudit = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/security/audit?limit=50");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: { entries: PolicyAuditEntry[]; total: number } = await res.json();
      setAudit(data.entries ?? []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load audit log");
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchSandboxServices = useCallback(async () => {
    setSandboxLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/ebpf/programs");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: EbpfProgramsResponse = await res.json();
      const services: SandboxService[] = (data.programs ?? []).map((prog) => ({
        name: prog.name,
        sandbox_status: (prog.attached_pids?.length ?? 0) > 0 ? "active" : "inactive",
        syscall_count: prog.syscall_count || 0,
        denial_count: prog.denial_count || 0,
        last_updated: prog.loaded_at,
      }));
      setSandboxServices(services);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load sandbox services");
    } finally {
      setSandboxLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    if (tab === "grants") fetchGrants();
    if (tab === "audit") fetchAudit();
    if (tab === "kernel-sandbox") fetchSandboxServices();
  }, [open, tab, fetchGrants, fetchAudit, fetchSandboxServices]);

  const handleGrant = async () => {
    if (!grantSubjectId.trim()) return;
    setGrantLoading(true);
    setGrantMsg(null);
    try {
      const res = await fetch("/api/security/grant", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          subject_type: grantSubjectType,
          subject_id: grantSubjectId.trim(),
          permission: grantPermission,
          scope: grantScope,
          granted_by: "security-center-ui",
        }),
      });
      if (!res.ok) {
        const err: { detail?: string } = await res.json();
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      setGrantMsg("Grant created");
      setGrantSubjectId("");
      if (tab === "grants") fetchGrants();
    } catch (e: unknown) {
      setGrantMsg(e instanceof Error ? `Error: ${e.message}` : "Grant failed");
    } finally {
      setGrantLoading(false);
    }
  };

  const handleRevoke = async (g: PolicyGrant) => {
    try {
      await fetch("/api/security/revoke", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          subject_type: g.subject_type,
          subject_id: g.subject_id,
          permission: g.permission,
        }),
      });
      fetchGrants();
    } catch {
      // ignore
    }
  };

  const handleInspect = async () => {
    if (!inspectSubjectId.trim()) return;
    setInspectLoading(true);
    try {
      const res = await fetch(`/api/security/policies/${inspectSubjectType}/${inspectSubjectId.trim()}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: { grants: PolicyGrant[] } = await res.json();
      setInspectResult(data.grants ?? []);
    } catch {
      setInspectResult([]);
    } finally {
      setInspectLoading(false);
    }
  };

  const isSensitive = (perm: string) =>
    (SENSITIVE_PERMISSIONS as readonly string[]).includes(perm);

  if (!open) return null;

  const left = Math.max(0, (window.innerWidth - PANEL_W) / 2);
  const top = Math.max(0, (window.innerHeight - PANEL_H) / 2);

  const style: React.CSSProperties = {
    position: "fixed",
    left,
    top,
    width: PANEL_W,
    height: PANEL_H,
    zIndex: layerZIndex,
    background: "#1a1a2e",
    border: "1px solid #3a3a5c",
    borderRadius: 10,
    display: "flex",
    flexDirection: "column",
    fontFamily: "monospace",
    color: "#e0e0e0",
    boxShadow: "0 8px 32px rgba(0,0,0,0.6)",
  };

  const tabStyle = (active: boolean): React.CSSProperties => ({
    padding: "6px 16px",
    cursor: "pointer",
    background: active ? "#2a2a4e" : "transparent",
    border: "none",
    color: active ? "#a0c4ff" : "#888",
    borderBottom: active ? "2px solid #a0c4ff" : "2px solid transparent",
    fontSize: 13,
  });

  const badgeStyle = (sensitive: boolean): React.CSSProperties => ({
    display: "inline-block",
    padding: "1px 6px",
    borderRadius: 3,
    fontSize: 11,
    background: sensitive ? "#4a1a1a" : "#1a3a1a",
    color: sensitive ? "#ff8a8a" : "#8aff8a",
    marginLeft: 4,
  });

  const btnStyle: React.CSSProperties = {
    padding: "4px 12px",
    background: "#2a4a6a",
    color: "#a0c4ff",
    border: "1px solid #3a5a8a",
    borderRadius: 4,
    cursor: "pointer",
    fontSize: 12,
  };

  const revokeBtn: React.CSSProperties = {
    padding: "2px 8px",
    background: "#4a1a1a",
    color: "#ff8a8a",
    border: "1px solid #7a2a2a",
    borderRadius: 3,
    cursor: "pointer",
    fontSize: 11,
  };

  const inputStyle: React.CSSProperties = {
    background: "#12122a",
    border: "1px solid #3a3a5c",
    borderRadius: 4,
    color: "#e0e0e0",
    padding: "4px 8px",
    fontSize: 12,
    outline: "none",
  };

  const selectStyle: React.CSSProperties = { ...inputStyle };

  const kernelSandboxContent = (() => {
    if (sandboxLoading) {
      return <div style={{ color: "#888", fontSize: 12, padding: 8 }}>Loading…</div>;
    }
    if (sandboxServices.length === 0) {
      return <div style={{ color: "#888", fontSize: 12, padding: 8 }}>No sandbox programs loaded</div>;
    }
    return (
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
        <thead>
          <tr style={{ borderBottom: "1px solid #3a3a5c" }}>
            <th style={{ textAlign: "left", padding: "4px", color: "#a0c4ff" }}>Service</th>
            <th style={{ textAlign: "left", padding: "4px", color: "#a0c4ff" }}>Status</th>
            <th style={{ textAlign: "right", padding: "4px", color: "#a0c4ff" }}>Syscalls</th>
            <th style={{ textAlign: "right", padding: "4px", color: "#a0c4ff" }}>Denials</th>
            <th style={{ textAlign: "left", padding: "4px", color: "#a0c4ff" }}>Updated</th>
          </tr>
        </thead>
        <tbody>
          {sandboxServices.map((svc) => (
            <tr key={svc.name} style={{ borderBottom: "1px solid #2a2a4e" }}>
              <td style={{ padding: "4px", color: "#e0e0e0" }}>{svc.name}</td>
              <td style={{ padding: "4px", color: svc.sandbox_status === "active" ? "#4aff8a" : "#ff8a4a" }}>
                {svc.sandbox_status === "active" ? "✓ Active" : "⚠ Inactive"}
              </td>
              <td style={{ padding: "4px", color: "#888", textAlign: "right" }}>{svc.syscall_count}</td>
              <td style={{ padding: "4px", color: svc.denial_count > 0 ? "#ff8a8a" : "#8aff8a", textAlign: "right" }}>{svc.denial_count}</td>
              <td style={{ padding: "4px", color: "#666", fontSize: 10 }}>{svc.last_updated.slice(0, 19)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  })();

  const grantsContent = (() => {
    if (loading) {
      return <div style={{ color: "#888", fontSize: 12, padding: 8 }}>Loading…</div>;
    }
    if (grants.length === 0) {
      return <div style={{ color: "#888", fontSize: 12, padding: 8 }}>No active grants</div>;
    }
    return grants.map((g) => (
      <div
        key={g.id}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "6px 8px",
          borderBottom: "1px solid #2a2a4e",
          fontSize: 12,
        }}
      >
        <div style={{ flex: 1 }}>
          <span style={{ color: "#a0c4ff" }}>{g.subject_type}</span>
          <span style={{ color: "#888" }}>/</span>
          <span style={{ color: "#e0e0e0" }}>{g.subject_id}</span>
          <span style={badgeStyle(isSensitive(g.permission))}>{g.permission}</span>
          <span style={{ color: "#666", marginLeft: 8 }}>[{g.scope}]</span>
          {g.expires_at && (
            <span style={{ color: "#888", marginLeft: 8, fontSize: 10 }}>exp: {g.expires_at}</span>
          )}
        </div>
        <button style={revokeBtn} onClick={() => handleRevoke(g)}>Revoke</button>
      </div>
    ));
  })();

  const auditContent = (() => {
    if (loading) {
      return <div style={{ color: "#888", fontSize: 12, padding: 8 }}>Loading…</div>;
    }
    if (audit.length === 0) {
      return <div style={{ color: "#888", fontSize: 12, padding: 8 }}>No audit entries</div>;
    }
    return audit.map((a) => (
      <div
        key={a.id}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "5px 8px",
          borderBottom: "1px solid #2a2a4e",
          fontSize: 11,
        }}
      >
        <span
          style={{
            display: "inline-block",
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: a.allowed ? "#4aff8a" : "#ff4a4a",
            flexShrink: 0,
          }}
        />
        <span style={{ color: "#666", flexShrink: 0 }}>{a.created_at.slice(0, 19)}</span>
        <span style={{ color: "#a0c4ff" }}>{a.subject_type}/{a.subject_id}</span>
        <span style={badgeStyle(isSensitive(a.permission))}>{a.permission}</span>
        <span style={{ color: "#888" }}>{a.action}</span>
        <span style={{ color: "#666", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.reason}</span>
      </div>
    ));
  })();

  return (
    <div style={style}>
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "10px 16px",
          borderBottom: "1px solid #3a3a5c",
          background: "#16163a",
          borderRadius: "10px 10px 0 0",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <ShieldCheck size={18} color="#a0c4ff" />
          <span style={{ fontWeight: "bold", fontSize: 14, color: "#a0c4ff" }}>Security Center</span>
        </div>
        <button
          style={{ background: "none", border: "none", color: "#888", cursor: "pointer", fontSize: 16 }}
          onClick={() => onOpenChange(false)}
          aria-label="Close Security Center"
        >
          ✕
        </button>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", borderBottom: "1px solid #3a3a5c" }}>
        <button style={tabStyle(tab === "grants")} onClick={() => setTab("grants")}>Grants</button>
        <button style={tabStyle(tab === "audit")} onClick={() => setTab("audit")}>Audit Log</button>
        <button style={tabStyle(tab === "inspect")} onClick={() => setTab("inspect")}>Inspect Subject</button>
        <button style={tabStyle(tab === "kernel-sandbox")} onClick={() => setTab("kernel-sandbox")}>Kernel Sandbox</button>
      </div>

      {/* Body */}
      <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
        {error && (
          <div style={{ padding: "6px 16px", background: "#3a1a1a", color: "#ff8a8a", fontSize: 12 }}>
            {error}
          </div>
        )}

        {tab === "kernel-sandbox" && (
          <div style={{ flex: 1, overflowY: "auto", padding: "8px 16px" }}>
            {kernelSandboxContent}
          </div>
        )}

        {tab === "grants" && (
          <div style={{ display: "flex", flexDirection: "column", flex: 1, overflow: "hidden" }}>
            {/* Grant form */}
            <div style={{ padding: "12px 16px", borderBottom: "1px solid #2a2a4e", display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <select
                value={grantSubjectType}
                onChange={(e) => setGrantSubjectType(e.target.value as SubjectType)}
                style={selectStyle}
              >
                {SUBJECT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              <input
                value={grantSubjectId}
                onChange={(e) => setGrantSubjectId(e.target.value)}
                placeholder="subject-id"
                style={{ ...inputStyle, width: 140 }}
              />
              <select
                value={grantPermission}
                onChange={(e) => setGrantPermission(e.target.value)}
                style={selectStyle}
              >
                {SENSITIVE_PERMISSIONS.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
              <select
                value={grantScope}
                onChange={(e) => setGrantScope(e.target.value)}
                style={selectStyle}
              >
                {SCOPES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
              <button style={btnStyle} onClick={handleGrant} disabled={grantLoading}>
                {grantLoading ? "…" : "Grant"}
              </button>
              {grantMsg && <span style={{ fontSize: 11, color: grantMsg.startsWith("Error") ? "#ff8a8a" : "#8aff8a" }}>{grantMsg}</span>}
            </div>

            {/* Grants list */}
            <div style={{ flex: 1, overflowY: "auto", padding: "8px 16px" }}>{grantsContent}</div>
          </div>
        )}

        {tab === "audit" && (
          <div style={{ flex: 1, overflowY: "auto", padding: "8px 16px" }}>{auditContent}</div>
        )}

        {tab === "inspect" && (
          <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <div style={{ padding: "12px 16px", borderBottom: "1px solid #2a2a4e", display: "flex", gap: 8, alignItems: "center" }}>
              <select
                value={inspectSubjectType}
                onChange={(e) => setInspectSubjectType(e.target.value as "package" | "persona" | "service")}
                style={selectStyle}
              >
                {SUBJECT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              <input
                value={inspectSubjectId}
                onChange={(e) => setInspectSubjectId(e.target.value)}
                placeholder="subject-id"
                style={{ ...inputStyle, width: 200 }}
              />
              <button style={btnStyle} onClick={handleInspect} disabled={inspectLoading}>
                {inspectLoading ? "…" : "Inspect"}
              </button>
            </div>
            <div style={{ flex: 1, overflowY: "auto", padding: "8px 16px" }}>
              {inspectResult.length === 0 ? (
                <div style={{ color: "#888", fontSize: 12, padding: 8 }}>Enter a subject and click Inspect</div>
              ) : (
                inspectResult.map((g) => (
                  <div key={g.id} style={{ padding: "6px 8px", borderBottom: "1px solid #2a2a4e", fontSize: 12 }}>
                    <span style={badgeStyle(isSensitive(g.permission))}>{g.permission}</span>
                    <span style={{ color: "#666", marginLeft: 8 }}>[{g.scope}]</span>
                    <span style={{ color: "#888", marginLeft: 8, fontSize: 10 }}>by {g.granted_by}</span>
                    {g.expires_at && (
                      <span style={{ color: "#888", marginLeft: 8, fontSize: 10 }}>exp: {g.expires_at}</span>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
