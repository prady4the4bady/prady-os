import { useEffect, useRef, useState } from "react";
import { Clock, RotateCcw, X, ChevronDown, ChevronUp } from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TaskRun {
  id: string;
  task_id: string | null;
  agent_id: string | null;
  persona_id: string | null;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  steps_json: string | null;
  result_json: string | null;
  error: string | null;
  replay_count: number;
  source: string | null;
  task_description: string | null;
  created_at: string | null;
}

interface RunsResponse {
  total: number;
  runs: TaskRun[];
  limit: number;
  offset: number;
}

interface StatsResponse {
  total: number;
  by_status: {
    done: number;
    failed: number;
    stopped: number;
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function statusColor(status: string): string {
  if (status === "done") return "#34C759";
  if (status === "failed") return "#FF3B30";
  if (status === "stopped") return "#FF9F0A";
  return "#8E8E93";
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function truncate(text: string | null, len: number): string {
  if (!text) return "—";
  return text.length > len ? `${text.slice(0, len)}…` : text;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface TaskHistoryProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  layerZIndex?: number;
}

export default function TaskHistory({ open, onOpenChange, layerZIndex }: Readonly<TaskHistoryProps>): JSX.Element {
  const [internalOpen, setInternalOpen] = useState(false);
  const [runs, setRuns] = useState<TaskRun[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [replayingIds, setReplayingIds] = useState<Set<string>>(new Set());
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

  const fetchData = (): void => {
    void (async () => {
      try {
        const [runsRes, statsRes] = await Promise.all([
          fetch("/api/audit/runs?limit=100"),
          fetch("/api/audit/runs/stats"),
        ]);
        if (runsRes.ok) {
          const data = (await runsRes.json()) as RunsResponse;
          setRuns(data.runs);
          setTotal(data.total);
        }
        if (statsRes.ok) {
          const data = (await statsRes.json()) as StatsResponse;
          setStats(data);
        }
      } catch {
        // ignore fetch errors
      }
    })();
  };

  useEffect(() => {
    if (isOpen) {
      fetchData();
      intervalRef.current = globalThis.setInterval(fetchData, 30_000);
    } else if (intervalRef.current !== null) {
      globalThis.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    return () => {
      if (intervalRef.current !== null) {
        globalThis.clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [isOpen]);

  const handleReplay = (run: TaskRun): void => {
    if (replayingIds.has(run.id)) return;

    const incrementReplayCount = (items: TaskRun[]): TaskRun[] =>
      items.map((item) =>
        item.id === run.id ? { ...item, replay_count: item.replay_count + 1 } : item
      );

    setReplayingIds((prev) => new Set([...prev, run.id]));
    void (async () => {
      try {
        await fetch(`/api/audit/runs/${run.id}/replay`, { method: "POST" });
        // Optimistically update replay_count
        setRuns(incrementReplayCount);
      } catch {
        // ignore
      } finally {
        setReplayingIds((prev) => {
          const next = new Set(prev);
          next.delete(run.id);
          return next;
        });
      }
    })();
  };

  const toggleExpand = (id: string): void => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  const successRate =
    stats && stats.total > 0
      ? Math.round((stats.by_status.done / stats.total) * 100)
      : null;

  return (
    <>
      {/* Trigger button */}
      <button
        type="button"
        aria-label="Task History"
        onClick={() => setOpenState(!isOpen)}
        style={{
          position: "fixed",
          top: 12,
          right: 72,
          zIndex: baseZIndex + 2,
          background: "rgba(28,28,30,0.85)",
          backdropFilter: "blur(12px)",
          WebkitBackdropFilter: "blur(12px)",
          border: "1px solid rgba(58,58,60,0.8)",
          borderRadius: 10,
          color: isOpen ? "#0A84FF" : "#F2F2F7",
          padding: "6px 10px",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: 5,
          fontSize: 12,
          fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif",
        }}
      >
        <Clock size={14} />
        <span>History</span>
        {total > 0 && (
          <span
            style={{
              background: "#0A84FF",
              color: "#fff",
              borderRadius: 10,
              padding: "1px 6px",
              fontSize: 10,
              minWidth: 16,
              textAlign: "center",
            }}
          >
            {total > 99 ? "99+" : total}
          </span>
        )}
      </button>

      {/* Slide-in panel */}
      {isOpen && (
        <>
          {/* Backdrop */}
          <button
            type="button"
            aria-label="Close task history"
            onClick={() => setOpenState(false)}
            style={{
              position: "fixed",
              inset: 0,
              background: "transparent",
              zIndex: baseZIndex,
              border: "none",
              cursor: "default",
            }}
          />

          {/* Panel */}
          <div
            style={{
              position: "fixed",
              top: 0,
              right: 0,
              width: 480,
              height: "100vh",
              background: "rgba(18,18,20,0.97)",
              backdropFilter: "blur(20px)",
              WebkitBackdropFilter: "blur(20px)",
              borderLeft: "1px solid rgba(58,58,60,0.8)",
              zIndex: baseZIndex + 1,
              display: "flex",
              flexDirection: "column",
              fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif",
              color: "#F2F2F7",
            }}
          >
            {/* Header */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "14px 16px",
                borderBottom: "1px solid rgba(58,58,60,0.6)",
                flexShrink: 0,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Clock size={16} color="#0A84FF" />
                <span style={{ fontWeight: 600, fontSize: 15 }}>Task History</span>
              </div>
              <button
                type="button"
                aria-label="Close"
                onClick={() => setOpenState(false)}
                style={{
                  background: "none",
                  border: "none",
                  color: "#8E8E93",
                  cursor: "pointer",
                  padding: 4,
                  borderRadius: 6,
                  display: "flex",
                  alignItems: "center",
                }}
              >
                <X size={16} />
              </button>
            </div>

            {/* Stats bar */}
            {stats && (
              <div
                style={{
                  display: "flex",
                  gap: 12,
                  padding: "10px 16px",
                  borderBottom: "1px solid rgba(58,58,60,0.4)",
                  flexShrink: 0,
                  flexWrap: "wrap",
                }}
              >
                <StatPill label="Total" value={String(stats.total)} color="#8E8E93" />
                <StatPill
                  label="Done"
                  value={String(stats.by_status.done)}
                  color="#34C759"
                />
                <StatPill
                  label="Failed"
                  value={String(stats.by_status.failed)}
                  color="#FF3B30"
                />
                {successRate !== null && (
                  <StatPill
                    label="Success rate"
                    value={`${successRate}%`}
                    color={successRate >= 80 ? "#34C759" : "#FF9F0A"}
                  />
                )}
              </div>
            )}

            {/* Run list */}
            <div style={{ flex: 1, overflowY: "auto", padding: "8px 0" }}>
              {runs.length === 0 ? (
                <div
                  style={{
                    padding: "40px 16px",
                    textAlign: "center",
                    color: "#636366",
                    fontSize: 13,
                  }}
                >
                  No task runs recorded yet.
                </div>
              ) : (
                runs.map((run) => (
                  <RunRow
                    key={run.id}
                    run={run}
                    expanded={expandedId === run.id}
                    replaying={replayingIds.has(run.id)}
                    onToggle={() => toggleExpand(run.id)}
                    onReplay={() => handleReplay(run)}
                  />
                ))
              )}
            </div>
          </div>
        </>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

type StatPillProps = Readonly<{
  label: string;
  value: string;
  color: string;
}>;

function StatPill({
  label,
  value,
  color,
}: StatPillProps): JSX.Element {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 2,
      }}
    >
      <span style={{ fontSize: 16, fontWeight: 700, color }}>{value}</span>
      <span style={{ fontSize: 10, color: "#636366", textTransform: "uppercase" }}>
        {label}
      </span>
    </div>
  );
}

type RunRowProps = Readonly<{
  run: TaskRun;
  expanded: boolean;
  replaying: boolean;
  onToggle: () => void;
  onReplay: () => void;
}>;

function RunRow({
  run,
  expanded,
  replaying,
  onToggle,
  onReplay,
}: RunRowProps): JSX.Element {
  let steps: unknown[] = [];
  try {
    steps = run.steps_json ? (JSON.parse(run.steps_json) as unknown[]) : [];
  } catch {
    steps = [];
  }

  return (
    <div
      style={{
        borderBottom: "1px solid rgba(58,58,60,0.3)",
        padding: "10px 16px",
      }}
    >
      {/* Row header */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: 10,
        }}
      >
        {/* Status dot */}
        <div
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: statusColor(run.status),
            marginTop: 4,
            flexShrink: 0,
          }}
        />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: 13,
              fontWeight: 500,
              color: "#F2F2F7",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {truncate(run.task_description, 70)}
          </div>
          <div
            style={{
              fontSize: 11,
              color: "#636366",
              marginTop: 2,
              display: "flex",
              gap: 8,
              flexWrap: "wrap",
            }}
          >
            <span style={{ color: statusColor(run.status) }}>{run.status}</span>
            <span>{run.agent_id ?? "—"}</span>
            <span>{formatDate(run.started_at)}</span>
            {run.replay_count > 0 && (
              <span style={{ color: "#FF9F0A" }}>
                replayed ×{run.replay_count}
              </span>
            )}
          </div>
        </div>

        {/* Replay button */}
        <button
          type="button"
          aria-label="Replay task"
          onClick={(e) => {
            e.stopPropagation();
            onReplay();
          }}
          disabled={replaying}
          style={{
            background: "none",
            border: "1px solid rgba(58,58,60,0.6)",
            borderRadius: 6,
            color: replaying ? "#636366" : "#0A84FF",
            cursor: replaying ? "default" : "pointer",
            padding: "4px 6px",
            display: "flex",
            alignItems: "center",
            flexShrink: 0,
          }}
        >
          <RotateCcw size={12} style={replaying ? { animation: "spin 1s linear infinite" } : undefined} />
        </button>

        {/* Expand toggle */}
        <button
          type="button"
          aria-label={expanded ? "Collapse" : "Expand"}
          onClick={(e) => {
            e.stopPropagation();
            onToggle();
          }}
          style={{
            background: "none",
            border: "none",
            color: "#636366",
            cursor: "pointer",
            padding: "4px",
            display: "flex",
            alignItems: "center",
            flexShrink: 0,
          }}
        >
          {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>
      </div>

      {/* Expanded steps */}
      {expanded && (
        <div
          style={{
            marginTop: 10,
            marginLeft: 18,
            borderLeft: "2px solid rgba(58,58,60,0.4)",
            paddingLeft: 12,
          }}
        >
          {steps.length === 0 ? (
            <div style={{ fontSize: 12, color: "#636366" }}>No step data.</div>
          ) : (
            steps.map((step) => {
              const stepKey =
                typeof step === "string" ? step : JSON.stringify(step);
              return (
              <div
                key={stepKey}
                style={{
                  marginBottom: 6,
                  fontSize: 12,
                  color: "#C7C7CC",
                  fontFamily: "monospace",
                  background: "rgba(38,38,40,0.6)",
                  borderRadius: 6,
                  padding: "4px 8px",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-all",
                }}
              >
                {typeof step === "string"
                  ? step
                  : JSON.stringify(step, null, 2)}
              </div>
              );
            })
          )}
          {run.error && (
            <div
              style={{
                marginTop: 6,
                fontSize: 12,
                color: "#FF3B30",
                background: "rgba(255,59,48,0.08)",
                borderRadius: 6,
                padding: "4px 8px",
              }}
            >
              Error: {run.error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
