import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  CheckCircle,
  RefreshCw,
  RotateCcw,
  Shield,
  X,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ServiceStatus = "unknown" | "healthy" | "degraded" | "down";

interface ServiceRecord {
  name: string;
  status: ServiceStatus;
  last_check_at: string | null;
  last_ok_at: string | null;
  last_error: string | null;
  consecutive_failures: number;
  latency_ms: number | null;
  check_count: number;
  updated_at: string;
}

interface ServicesResponse {
  services: ServiceRecord[];
  total: number;
}

interface IncidentRecord {
  id: string;
  service_name: string;
  status: string;
  started_at: string;
  resolved_at: string | null;
  message: string | null;
  created_at: string;
}

interface IncidentsResponse {
  incidents: IncidentRecord[];
  total: number;
  limit: number;
  offset: number;
}

interface IncidentsStats {
  total: number;
  open: number;
  resolved: number;
  by_service: Record<string, number>;
  by_status: Record<string, number>;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const FONT = "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif";
const API_BASE = "/api/watchdog";
const REFRESH_MS = 20_000;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function jsonOrThrow<T>(resp: Response): Promise<T> {
  const body = await resp.text();
  if (!resp.ok) throw new Error(body || `HTTP ${resp.status}`);
  return (body ? JSON.parse(body) : {}) as T;
}

function relativeTime(iso: string | null): string {
  if (!iso) return "never";
  const ms = Date.now() - new Date(iso).getTime();
  const sec = Math.floor(ms / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  return `${Math.floor(hr / 24)}d ago`;
}

function statusColor(status: string): string {
  switch (status) {
    case "healthy":  return "#30D158";
    case "degraded": return "#FFD60A";
    case "down":     return "#FF453A";
    default:         return "#8E8E93";
  }
}

function StatusIcon({ status }: Readonly<{ status: string }>): JSX.Element {
  const size = 13;
  const color = statusColor(status);
  switch (status) {
    case "healthy":  return <CheckCircle size={size} color={color} />;
    case "degraded": return <AlertTriangle size={size} color={color} />;
    case "down":     return <AlertCircle size={size} color={color} />;
    default:         return <Activity size={size} color={color} />;
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface WatchdogCenterProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  layerZIndex?: number;
}

export default function WatchdogCenter({
  open,
  onOpenChange,
  layerZIndex,
}: Readonly<WatchdogCenterProps>): JSX.Element {
  const [internalOpen, setInternalOpen] = useState(false);
  const [services, setServices] = useState<ServiceRecord[]>([]);
  const [incidents, setIncidents] = useState<IncidentRecord[]>([]);
  const [stats, setStats] = useState<IncidentsStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [checkingService, setCheckingService] = useState<string | null>(null);
  const [restartingService, setRestartingService] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<number | null>(null);
  const isControlled = open !== undefined;
  const isOpen = isControlled ? open : internalOpen;
  const baseZIndex = layerZIndex ?? 9000;

  const setOpenState = (next: boolean): void => {
    if (!isControlled) {
      setInternalOpen(next);
    }
    onOpenChange?.(next);
  };

  const unhealthyCount = services.filter(
    (s) => s.status !== "healthy" && s.status !== "unknown"
  ).length;

  const overallStatus = (() => {
    if (services.some((s) => s.status === "down")) return "down";
    if (services.some((s) => s.status === "degraded")) return "degraded";
    if (services.length > 0 && services.every((s) => s.status === "healthy")) return "healthy";
    return "unknown";
  })() as ServiceStatus;

  const refresh = useCallback((): void => {
    void (async () => {
      setLoading(true);
      try {
        const [svcResp, incResp, statsResp] = await Promise.all([
          fetch(`${API_BASE}/services`),
          fetch(`${API_BASE}/incidents?limit=20`),
          fetch(`${API_BASE}/incidents/stats`),
        ]);
        const [svcData, incData, statsData] = await Promise.all([
          jsonOrThrow<ServicesResponse>(svcResp),
          jsonOrThrow<IncidentsResponse>(incResp),
          jsonOrThrow<IncidentsStats>(statsResp),
        ]);
        setServices(svcData.services ?? []);
        setIncidents(incData.incidents ?? []);
        setStats(statsData);
        setError(null);
      } catch (e) {
        setError(`Failed to load watchdog data: ${String(e)}`);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    refresh();
    intervalRef.current = globalThis.setInterval(refresh, REFRESH_MS);
    return () => {
      if (intervalRef.current !== null) {
        globalThis.clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [isOpen, refresh]);

  const forceCheck = (name: string): void => {
    void (async () => {
      setCheckingService(name);
      try {
        await fetch(`${API_BASE}/services/${encodeURIComponent(name)}/check`, {
          method: "POST",
        });
        refresh();
      } catch {
        setError(`Check failed for ${name}`);
      } finally {
        setCheckingService(null);
      }
    })();
  };

  const restartService = (name: string): void => {
    void (async () => {
      setRestartingService(name);
      try {
        const resp = await fetch(
          `${API_BASE}/services/${encodeURIComponent(name)}/restart`,
          { method: "POST" }
        );
        const data = (await resp.json()) as { ok: boolean; error?: string };
        if (data.ok) {
          globalThis.setTimeout(refresh, 2000);
        } else {
          setError(data.error ?? `Restart failed for ${name}`);
        }
      } catch (e) {
        setError(`Restart failed for ${name}: ${String(e)}`);
      } finally {
        setRestartingService(null);
      }
    })();
  };

  const scanAll = (): void => {
    void (async () => {
      setLoading(true);
      try {
        await fetch(`${API_BASE}/scan`, { method: "POST" });
        refresh();
      } catch {
        setLoading(false);
      }
    })();
  };

  return (
    <>
      {/* ── Tray button ─────────────────────────────────────────────────── */}
      <button
        type="button"
        onClick={() => setOpenState(!isOpen)}
        title="Watchdog — service health monitor"
        style={{
          position: "fixed",
          bottom: 56,
          right: 454,
          zIndex: baseZIndex + 2,
          borderRadius: 10,
          border: `1px solid ${
            unhealthyCount > 0 ? "rgba(255,69,58,0.7)" : "rgba(58,58,60,0.7)"
          }`,
          background: "rgba(28,28,30,0.85)",
          color: unhealthyCount > 0 ? "#FF453A" : "#F2F2F7",
          backdropFilter: "blur(12px)",
          WebkitBackdropFilter: "blur(12px)",
          padding: "6px 10px",
          fontSize: 11,
          fontFamily: FONT,
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        <Shield size={14} />
        Watchdog
        {unhealthyCount > 0 && (
          <span
            style={{
              background: "#FF453A",
              color: "#fff",
              borderRadius: 8,
              padding: "1px 5px",
              fontSize: 10,
              fontWeight: 600,
              lineHeight: 1.4,
            }}
          >
            {unhealthyCount}
          </span>
        )}
      </button>

      {/* ── Slide-in panel ──────────────────────────────────────────────── */}
      {isOpen && (
        <div
          style={{
            position: "fixed",
            top: 0,
            right: 0,
            bottom: 0,
            width: 420,
            zIndex: baseZIndex + 1,
            background: "rgba(20,20,22,0.96)",
            backdropFilter: "blur(16px)",
            WebkitBackdropFilter: "blur(16px)",
            borderLeft: "1px solid rgba(58,58,60,0.7)",
            display: "flex",
            flexDirection: "column",
            fontFamily: FONT,
            color: "#F2F2F7",
            overflowY: "auto",
          }}
        >
          {/* Header */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "16px 20px 12px",
              borderBottom: "1px solid rgba(58,58,60,0.5)",
              flexShrink: 0,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Shield size={18} color="#0A84FF" />
              <span style={{ fontSize: 16, fontWeight: 600 }}>Watchdog</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <button
                type="button"
                onClick={scanAll}
                disabled={loading}
                title="Scan all services now"
                style={{
                  background: "rgba(58,58,60,0.5)",
                  border: "1px solid rgba(58,58,60,0.7)",
                  borderRadius: 6,
                  color: "#F2F2F7",
                  padding: "4px 8px",
                  cursor: loading ? "not-allowed" : "pointer",
                  fontSize: 11,
                  display: "flex",
                  alignItems: "center",
                  gap: 4,
                  opacity: loading ? 0.5 : 1,
                }}
              >
                <RefreshCw size={11} />
                Scan
              </button>
              <button
                type="button"
                onClick={() => setOpenState(false)}
                style={{
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "#8E8E93",
                  padding: 4,
                  display: "flex",
                  alignItems: "center",
                }}
              >
                <X size={18} />
              </button>
            </div>
          </div>

          <div style={{ padding: "12px 20px", flexShrink: 0 }}>
            {error && (
              <div
                style={{
                  background: "rgba(255,69,58,0.15)",
                  border: "1px solid rgba(255,69,58,0.3)",
                  borderRadius: 8,
                  padding: "8px 12px",
                  fontSize: 12,
                  color: "#FF453A",
                  marginBottom: 12,
                }}
              >
                {error}
              </div>
            )}

            {/* Overview card */}
            <div
              style={{
                background: "rgba(44,44,46,0.5)",
                borderRadius: 10,
                padding: "12px 16px",
                marginBottom: 16,
                border: `1px solid ${statusColor(overallStatus)}33`,
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: 8,
                }}
              >
                <span style={{ fontSize: 13, fontWeight: 600 }}>System Health</span>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <StatusIcon status={overallStatus} />
                  <span
                    style={{
                      fontSize: 12,
                      color: statusColor(overallStatus),
                      fontWeight: 600,
                      textTransform: "capitalize",
                    }}
                  >
                    {overallStatus}
                  </span>
                </div>
              </div>
              <div style={{ display: "flex", gap: 16, fontSize: 12, color: "#8E8E93" }}>
                <span>
                  <span style={{ color: "#F2F2F7", fontWeight: 600 }}>
                    {services.filter((s) => s.status === "healthy").length}
                  </span>{" "}
                  healthy
                </span>
                <span>
                  <span style={{ color: "#FFD60A", fontWeight: 600 }}>
                    {services.filter((s) => s.status === "degraded").length}
                  </span>{" "}
                  degraded
                </span>
                <span>
                  <span style={{ color: "#FF453A", fontWeight: 600 }}>
                    {services.filter((s) => s.status === "down").length}
                  </span>{" "}
                  down
                </span>
                {stats && stats.open > 0 && (
                  <span>
                    <span style={{ color: "#FF453A", fontWeight: 600 }}>{stats.open}</span>{" "}
                    open incidents
                  </span>
                )}
              </div>
            </div>

            {/* Services section label */}
            <div
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: "#8E8E93",
                textTransform: "uppercase",
                letterSpacing: 0.5,
                marginBottom: 8,
              }}
            >
              Services
            </div>
          </div>

          {/* Services list */}
          <div style={{ paddingLeft: 20, paddingRight: 20, flexShrink: 0 }}>
            {services.length === 0 && !loading && (
              <div
                style={{ fontSize: 12, color: "#8E8E93", textAlign: "center", padding: "12px 0" }}
              >
                No services available.
              </div>
            )}
            {services.map((svc) => (
              <div
                key={svc.name}
                style={{
                  background: "rgba(44,44,46,0.4)",
                  borderRadius: 8,
                  padding: "10px 12px",
                  marginBottom: 8,
                  border: `1px solid ${
                    svc.status !== "healthy" && svc.status !== "unknown"
                      ? statusColor(svc.status) + "44"
                      : "rgba(58,58,60,0.5)"
                  }`,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    marginBottom: 4,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <StatusIcon status={svc.status} />
                    <span style={{ fontSize: 13, fontWeight: 500 }}>{svc.name}</span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <button
                      type="button"
                      onClick={() => forceCheck(svc.name)}
                      disabled={checkingService === svc.name}
                      title="Force health check"
                      style={{
                        background: "rgba(58,58,60,0.5)",
                        border: "1px solid rgba(58,58,60,0.7)",
                        borderRadius: 5,
                        color: "#F2F2F7",
                        padding: "3px 7px",
                        cursor: checkingService === svc.name ? "not-allowed" : "pointer",
                        fontSize: 10,
                        display: "flex",
                        alignItems: "center",
                        gap: 3,
                        opacity: checkingService === svc.name ? 0.5 : 1,
                      }}
                    >
                      <Activity size={10} />
                      {checkingService === svc.name ? "…" : "Check"}
                    </button>
                    <button
                      type="button"
                      onClick={() => restartService(svc.name)}
                      disabled={restartingService === svc.name}
                      title="Restart service via systemctl"
                      style={{
                        background: "rgba(255,69,58,0.15)",
                        border: "1px solid rgba(255,69,58,0.3)",
                        borderRadius: 5,
                        color: "#FF453A",
                        padding: "3px 7px",
                        cursor: restartingService === svc.name ? "not-allowed" : "pointer",
                        fontSize: 10,
                        display: "flex",
                        alignItems: "center",
                        gap: 3,
                        opacity: restartingService === svc.name ? 0.5 : 1,
                      }}
                    >
                      <RotateCcw size={10} />
                      {restartingService === svc.name ? "…" : "Restart"}
                    </button>
                  </div>
                </div>
                <div
                  style={{
                    fontSize: 11,
                    color: "#8E8E93",
                    display: "flex",
                    gap: 12,
                    flexWrap: "wrap",
                  }}
                >
                  <span>Checked {relativeTime(svc.last_check_at)}</span>
                  {svc.latency_ms !== null && (
                    <span>{svc.latency_ms.toFixed(0)} ms</span>
                  )}
                  {svc.consecutive_failures > 0 && (
                    <span style={{ color: "#FFD60A" }}>
                      {svc.consecutive_failures} failure
                      {svc.consecutive_failures === 1 ? "" : "s"}
                    </span>
                  )}
                </div>
                {svc.last_error && (
                  <div
                    style={{
                      fontSize: 11,
                      color: "#FF453A",
                      marginTop: 4,
                      wordBreak: "break-word",
                    }}
                  >
                    {svc.last_error}
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Incidents section */}
          <div style={{ padding: "12px 20px 8px", flexShrink: 0 }}>
            <div
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: "#8E8E93",
                textTransform: "uppercase",
                letterSpacing: 0.5,
                marginBottom: 8,
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              Recent Incidents
              {stats && stats.open > 0 && (
                <span
                  style={{
                    background: "#FF453A",
                    color: "#fff",
                    borderRadius: 8,
                    padding: "1px 6px",
                    fontSize: 10,
                    fontWeight: 600,
                    lineHeight: 1.4,
                  }}
                >
                  {stats.open} open
                </span>
              )}
            </div>
          </div>

          <div style={{ paddingLeft: 20, paddingRight: 20, paddingBottom: 20, flexShrink: 0 }}>
            {incidents.length === 0 && (
              <div
                style={{ fontSize: 12, color: "#8E8E93", textAlign: "center", padding: "12px 0" }}
              >
                No incidents recorded.
              </div>
            )}
            {incidents.map((inc) => (
              <div
                key={inc.id}
                style={{
                  background: inc.resolved_at
                    ? "rgba(44,44,46,0.25)"
                    : "rgba(255,69,58,0.08)",
                  borderRadius: 8,
                  padding: "8px 12px",
                  marginBottom: 6,
                  border: inc.resolved_at
                    ? "1px solid rgba(58,58,60,0.4)"
                    : "1px solid rgba(255,69,58,0.3)",
                  opacity: inc.resolved_at ? 0.75 : 1,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    marginBottom: 2,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                    <StatusIcon status={inc.status} />
                    <span style={{ fontSize: 12, fontWeight: 500 }}>{inc.service_name}</span>
                    <span
                      style={{
                        fontSize: 10,
                        padding: "1px 5px",
                        borderRadius: 4,
                        background: statusColor(inc.status) + "33",
                        color: statusColor(inc.status),
                        textTransform: "capitalize",
                      }}
                    >
                      {inc.status}
                    </span>
                  </div>
                  {inc.resolved_at ? (
                    <span style={{ fontSize: 10, color: "#30D158" }}>resolved</span>
                  ) : (
                    <span style={{ fontSize: 10, color: "#FF453A" }}>open</span>
                  )}
                </div>
                {inc.message && (
                  <div
                    style={{
                      fontSize: 11,
                      color: "#8E8E93",
                      marginBottom: 2,
                      wordBreak: "break-word",
                    }}
                  >
                    {inc.message}
                  </div>
                )}
                <div style={{ fontSize: 10, color: "#636366" }}>
                  {relativeTime(inc.started_at)}
                  {inc.resolved_at &&
                    ` → resolved ${relativeTime(inc.resolved_at)}`}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
