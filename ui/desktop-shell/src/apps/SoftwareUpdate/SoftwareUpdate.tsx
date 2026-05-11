import { useCallback, useEffect, useMemo, useState } from "react";

interface SoftwareUpdateProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  layerZIndex: number;
}

type UpdateStage = "up_to_date" | "update_available" | "downloading" | "applying" | "restart_required";

interface CheckResponse {
  update_available: boolean;
  version: string;
  changelog: string[];
}

interface StatusResponse {
  active_slot: "a" | "b";
  version: string;
  last_check_ts: string | null;
  state: string;
}

interface UpdateHistoryItem {
  id: string;
  version: string;
  status: string;
  ts: string;
  slot: string;
}

const FONT = "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif";

function statusBadgeColor(stage: UpdateStage): string {
  switch (stage) {
    case "up_to_date":
      return "#1f9d55";
    case "update_available":
      return "#0a84ff";
    case "downloading":
      return "#2563eb";
    case "applying":
      return "#7c3aed";
    case "restart_required":
      return "#f59e0b";
    default:
      return "#6b7280";
  }
}

export default function SoftwareUpdate({ open, onOpenChange, layerZIndex }: Readonly<SoftwareUpdateProps>): JSX.Element | null {
  const [stage, setStage] = useState<UpdateStage>("up_to_date");
  const [currentVersion, setCurrentVersion] = useState("1.0.0");
  const [newVersion, setNewVersion] = useState<string | null>(null);
  const [changelog, setChangelog] = useState<string[]>([]);
  const [progress, setProgress] = useState(0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [history, setHistory] = useState<UpdateHistoryItem[]>([]);
  const [historyOpen, setHistoryOpen] = useState(true);

  const notifyDockBadge = useCallback((available: boolean) => {
    globalThis.dispatchEvent(new CustomEvent("kryos:ota-update-available", { detail: { available } }));
  }, []);

  const appendHistory = useCallback((item: Omit<UpdateHistoryItem, "id" | "ts">) => {
    const entry: UpdateHistoryItem = {
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      ts: new Date().toISOString(),
      ...item,
    };
    setHistory((prev) => [entry, ...prev].slice(0, 20));
  }, []);

  const pollStatus = useCallback(async () => {
    try {
      const statusResp = await fetch("/api/ota/status");
      if (statusResp.ok) {
        const statusData = (await statusResp.json()) as StatusResponse;
        setCurrentVersion(statusData.version);
      }

      const checkResp = await fetch("/api/ota/check", { method: "POST" });
      if (checkResp.ok) {
        const checkData = (await checkResp.json()) as CheckResponse;
        setNewVersion(checkData.version);
        setChangelog(checkData.changelog || []);
        if (checkData.update_available) {
          setStage((prev) => (prev === "restart_required" ? prev : "update_available"));
          notifyDockBadge(true);
        } else {
          setStage((prev) => (prev === "restart_required" ? prev : "up_to_date"));
          notifyDockBadge(false);
        }
      }
    } catch {
      // Keep current UI state on transient polling failures.
    }
  }, [notifyDockBadge]);

  useEffect(() => {
    void pollStatus();
    const timer = setInterval(() => {
      void pollStatus();
    }, 30_000);
    return () => clearInterval(timer);
  }, [pollStatus]);

  const runUpdate = useCallback(async () => {
    setBusy(true);
    setMessage(null);
    setProgress(0);

    try {
      const checkResp = await fetch("/api/ota/check", { method: "POST" });
      const checkData = (await checkResp.json()) as CheckResponse;
      if (!checkData.update_available) {
        setStage("up_to_date");
        notifyDockBadge(false);
        setMessage("Prady OS is already up to date.");
        return;
      }

      setNewVersion(checkData.version);
      setChangelog(checkData.changelog || []);
      setStage("downloading");

      const downloadResp = await fetch("/api/ota/download", { method: "POST" });
      if (!downloadResp.ok) {
        throw new Error("Download could not be started.");
      }
      await downloadResp.json();

      for (let i = 0; i <= 100; i += 5) {
        setProgress(i);
        await new Promise((resolve) => setTimeout(resolve, 35));
      }

      setStage("applying");
      const applyResp = await fetch("/api/ota/apply", { method: "POST" });
      if (!applyResp.ok) {
        throw new Error("Apply failed.");
      }

      const commitResp = await fetch("/api/ota/commit", { method: "POST" });
      if (!commitResp.ok) {
        throw new Error("Commit failed.");
      }
      const commitData = (await commitResp.json()) as { next_slot: string };

      appendHistory({
        version: checkData.version,
        status: "committed",
        slot: commitData.next_slot,
      });
      setStage("restart_required");
      notifyDockBadge(false);
      setMessage("Update committed. Restart when convenient to boot into the new slot.");
    } catch (error) {
      const detail = error instanceof Error ? error.message : "Unknown update error.";
      setMessage(detail);
      appendHistory({
        version: newVersion ?? "unknown",
        status: "failed",
        slot: "-",
      });
      setStage("update_available");
    } finally {
      setBusy(false);
    }
  }, [appendHistory, newVersion, notifyDockBadge]);

  const rollback = useCallback(async () => {
    setBusy(true);
    try {
      const resp = await fetch("/api/ota/rollback", { method: "POST" });
      if (!resp.ok) {
        throw new Error("Rollback failed.");
      }
      appendHistory({ version: newVersion ?? "unknown", status: "rolled_back", slot: "a" });
      setStage("up_to_date");
      setProgress(0);
      setMessage("Rollback completed. System is back on the previous slot.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Rollback failed.");
    } finally {
      setBusy(false);
    }
  }, [appendHistory, newVersion]);

  const stageLabel = useMemo(() => {
    switch (stage) {
      case "up_to_date":
        return "Up to Date";
      case "update_available":
        return "Update Available";
      case "downloading":
        return "Downloading";
      case "applying":
        return "Applying";
      case "restart_required":
        return "Restart Required";
      default:
        return "Unknown";
    }
  }, [stage]);

  if (!open) {
    return null;
  }

  return (
    <dialog
      open
      aria-label="Software Update"
      style={{
        position: "fixed",
        top: "10vh",
        left: "50%",
        transform: "translateX(-50%)",
        margin: 0,
        padding: 0,
        width: "min(760px, calc(100vw - 32px))",
        maxHeight: "80vh",
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
          <div style={{ fontSize: 20, fontWeight: 700, letterSpacing: -0.3 }}>Software Update</div>
          <div style={{ marginTop: 4, fontSize: 13, color: "#52607a" }}>
            Keep Prady OS secure and up to date
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

      <div style={{ padding: 20, overflowY: "auto", maxHeight: "calc(80vh - 72px)" }}>
        <div
          style={{
            border: "1px solid #dbe2ee",
            borderRadius: 16,
            background: "#ffffff",
            padding: 16,
            marginBottom: 16,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
            <span
              style={{
                width: 12,
                height: 12,
                borderRadius: "50%",
                background: statusBadgeColor(stage),
                display: "inline-block",
              }}
            />
            <span style={{ fontSize: 16, fontWeight: 600 }}>{stageLabel}</span>
          </div>

          <div style={{ fontSize: 13, color: "#4b5563", lineHeight: 1.6 }}>
            <div>Current Version: <strong>{currentVersion}</strong></div>
            <div>Available Version: <strong>{newVersion ?? currentVersion}</strong></div>
          </div>

          {stage === "downloading" && (
            <div style={{ marginTop: 14 }}>
              <div
                style={{
                  width: "100%",
                  height: 10,
                  borderRadius: 999,
                  background: "#e5e7eb",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${progress}%`,
                    height: "100%",
                    background: "linear-gradient(90deg, #3b82f6 0%, #60a5fa 100%)",
                    transition: "width 120ms linear",
                  }}
                />
              </div>
              <div style={{ marginTop: 8, fontSize: 12, color: "#334155" }}>{progress}% downloaded</div>
            </div>
          )}

          {stage === "applying" && (
            <div style={{ marginTop: 14, fontSize: 13, color: "#4c1d95" }}>
              Applying delta patch to inactive slot...
            </div>
          )}

          {message && (
            <div style={{ marginTop: 12, fontSize: 12, color: "#475569" }}>{message}</div>
          )}

          <div style={{ display: "flex", gap: 10, marginTop: 16, flexWrap: "wrap" }}>
            {(stage === "up_to_date" || stage === "update_available") && (
              <button
                type="button"
                onClick={() => void runUpdate()}
                disabled={busy}
                style={{
                  background: "#0a84ff",
                  color: "white",
                  border: "none",
                  borderRadius: 10,
                  padding: "8px 14px",
                  fontWeight: 600,
                  cursor: busy ? "not-allowed" : "pointer",
                  opacity: busy ? 0.6 : 1,
                }}
              >
                Update Now
              </button>
            )}

            {stage === "downloading" && (
              <button
                type="button"
                onClick={() => {
                  setStage("update_available");
                  setProgress(0);
                  setMessage("Download canceled.");
                }}
                disabled={busy}
                style={{
                  background: "#ef4444",
                  color: "white",
                  border: "none",
                  borderRadius: 10,
                  padding: "8px 14px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Cancel
              </button>
            )}

            {stage === "restart_required" && (
              <>
                <button
                  type="button"
                  onClick={() => setMessage("Restart deferred. You can reboot later.")}
                  style={{
                    background: "#e5e7eb",
                    color: "#111827",
                    border: "none",
                    borderRadius: 10,
                    padding: "8px 14px",
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  Restart Later
                </button>
                <button
                  type="button"
                  onClick={() => setMessage("Restart requested. System reboot simulation pending.")}
                  style={{
                    background: "#f59e0b",
                    color: "#111827",
                    border: "none",
                    borderRadius: 10,
                    padding: "8px 14px",
                    fontWeight: 700,
                    cursor: "pointer",
                  }}
                >
                  Restart Now
                </button>
              </>
            )}

            <button
              type="button"
              onClick={() => void rollback()}
              disabled={busy}
              style={{
                background: "#fef2f2",
                color: "#b91c1c",
                border: "1px solid #fecaca",
                borderRadius: 10,
                padding: "8px 14px",
                fontWeight: 600,
                cursor: busy ? "not-allowed" : "pointer",
              }}
            >
              Rollback
            </button>
          </div>
        </div>

        <div
          style={{
            border: "1px solid #dbe2ee",
            borderRadius: 16,
            background: "#ffffff",
            padding: 16,
          }}
        >
          <button
            type="button"
            onClick={() => setHistoryOpen((prev) => !prev)}
            style={{
              width: "100%",
              border: "none",
              background: "transparent",
              padding: 0,
              textAlign: "left",
              cursor: "pointer",
              fontSize: 15,
              fontWeight: 700,
              color: "#111827",
            }}
          >
            Update History {historyOpen ? "▾" : "▸"}
          </button>

          {historyOpen && (
            <div style={{ marginTop: 12, display: "grid", gap: 8 }}>
              {history.length === 0 && (
                <div style={{ fontSize: 12, color: "#6b7280" }}>No updates recorded yet.</div>
              )}
              {history.map((item) => (
                <div
                  key={item.id}
                  style={{
                    border: "1px solid #e5e7eb",
                    borderRadius: 10,
                    padding: "10px 12px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 8,
                  }}
                >
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>{item.version}</div>
                    <div style={{ fontSize: 11, color: "#6b7280" }}>{new Date(item.ts).toLocaleString()}</div>
                  </div>
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 700,
                      borderRadius: 999,
                      padding: "3px 8px",
                      background: item.status === "failed" ? "#fee2e2" : "#dcfce7",
                      color: item.status === "failed" ? "#991b1b" : "#166534",
                    }}
                  >
                    {item.status.toUpperCase()}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div
          style={{
            marginTop: 16,
            border: "1px solid #dbe2ee",
            borderRadius: 16,
            background: "#ffffff",
            padding: 16,
          }}
        >
          <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 8 }}>What’s New</div>
          {changelog.length === 0 ? (
            <div style={{ fontSize: 12, color: "#64748b" }}>No changelog entries available.</div>
          ) : (
            <ul style={{ margin: 0, paddingLeft: 18, color: "#334155", fontSize: 13, lineHeight: 1.7 }}>
              {changelog.map((entry) => (
                <li key={entry}>{entry}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </dialog>
  );
}
