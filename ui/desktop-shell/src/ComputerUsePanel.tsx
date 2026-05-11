import React, { useCallback, useEffect, useMemo, useState } from 'react';

type TaskStatus = 'IDLE' | 'RUNNING' | 'DONE' | 'FAILED';

interface TaskLogEntry {
  step: number;
  action: string;
  reasoning?: string;
  screenshotBefore?: string;
  screenshotAfter?: string;
}

interface RunResult {
  status?: string;
  steps?: number;
  message?: string;
  actions?: Array<{ action?: string; reasoning?: string }>;
}

const AGENT_URL = 'http://localhost:8100';

function statusColor(status: TaskStatus): string {
  if (status === 'RUNNING') return '#0a84ff';
  if (status === 'DONE') return '#30d158';
  if (status === 'FAILED') return '#ff453a';
  return 'rgba(235,235,245,0.6)';
}

export function ComputerUsePanel() {
  const [task, setTask] = useState('');
  const [status, setStatus] = useState<TaskStatus>('IDLE');
  const [preview, setPreview] = useState<string>('');
  const [logs, setLogs] = useState<TaskLogEntry[]>([]);
  const [running, setRunning] = useState(false);

  const refreshScreenshot = useCallback(async () => {
    try {
      const res = await fetch(`${AGENT_URL}/computer/screenshot`);
      if (!res.ok) return;
      const data = await res.json();
      if (data?.image_b64) {
        setPreview(`data:image/png;base64,${data.image_b64}`);
      }
    } catch {
      // best-effort preview
    }
  }, []);

  useEffect(() => {
    void refreshScreenshot();
    const timer = setInterval(() => {
      void refreshScreenshot();
    }, 2000);
    return () => clearInterval(timer);
  }, [refreshScreenshot]);

  const runTask = useCallback(async () => {
    if (!task.trim() || running) return;

    setRunning(true);
    setStatus('RUNNING');
    setLogs([]);

    try {
      const res = await fetch(`${AGENT_URL}/computer/task/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_description: task, max_steps: 20 }),
      });

      const data = (await res.json()) as RunResult;
      const nextLogs = (data.actions || []).map((entry, idx) => ({
        step: idx + 1,
        action: entry.action || 'unknown',
        reasoning: entry.reasoning,
      }));
      setLogs(nextLogs);

      if (!res.ok || data.status === 'failed') {
        setStatus('FAILED');
      } else {
        setStatus('DONE');
      }
    } catch {
      setStatus('FAILED');
    } finally {
      setRunning(false);
      void refreshScreenshot();
    }
  }, [refreshScreenshot, running, task]);

  const stopTask = useCallback(async () => {
    try {
      await fetch(`${AGENT_URL}/computer/task/stop`, { method: 'POST' });
      setStatus('FAILED');
    } finally {
      setRunning(false);
    }
  }, []);

  const panelStyle = useMemo<React.CSSProperties>(
    () => ({
      position: 'fixed',
      top: 76,
      left: 20,
      width: 340,
      maxHeight: '72vh',
      overflow: 'hidden',
      zIndex: 48,
      borderRadius: 14,
      border: '1px solid rgba(255,255,255,0.12)',
      background: 'rgba(28, 28, 30, 0.72)',
      backdropFilter: 'blur(20px) saturate(180%)',
      WebkitBackdropFilter: 'blur(20px) saturate(180%)',
      boxShadow: '0 10px 30px rgba(0,0,0,0.35)',
      color: '#ebebf5',
      fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif",
    }),
    [],
  );

  return (
    <section style={panelStyle}>
      <header style={{ padding: '12px 14px 8px 14px', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <strong style={{ fontSize: 13, letterSpacing: '0.2px' }}>Computer Use</strong>
          <span
            style={{
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: '0.7px',
              color: statusColor(status),
              background: 'rgba(255,255,255,0.08)',
              borderRadius: 99,
              padding: '3px 8px',
            }}
          >
            {status}
          </span>
        </div>
      </header>

      <div style={{ padding: 12, display: 'grid', gap: 10 }}>
        <div
          style={{
            borderRadius: 10,
            overflow: 'hidden',
            border: '1px solid rgba(255,255,255,0.08)',
            background: 'rgba(0,0,0,0.25)',
            minHeight: 130,
          }}
        >
          {preview ? (
            <img src={preview} alt="Live screen" style={{ width: '100%', display: 'block', objectFit: 'cover' }} />
          ) : (
            <div style={{ padding: 14, fontSize: 12, color: 'rgba(235,235,245,0.5)' }}>Waiting for screenshot…</div>
          )}
        </div>

        <div style={{ display: 'grid', gap: 8 }}>
          <input
            value={task}
            onChange={(e) => setTask(e.target.value)}
            placeholder="Describe the task to automate"
            style={{
              width: '100%',
              borderRadius: 8,
              border: '1px solid rgba(255,255,255,0.14)',
              background: 'rgba(255,255,255,0.06)',
              color: '#f2f2f7',
              fontSize: 12,
              padding: '8px 10px',
              outline: 'none',
            }}
          />
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={() => void runTask()}
              disabled={running || !task.trim()}
              style={{
                flex: 1,
                borderRadius: 8,
                border: 'none',
                background: running ? 'rgba(10,132,255,0.45)' : '#0a84ff',
                color: '#fff',
                fontSize: 12,
                padding: '8px 10px',
                cursor: running ? 'not-allowed' : 'pointer',
              }}
            >
              Run Task
            </button>
            <button
              onClick={() => void stopTask()}
              disabled={!running}
              style={{
                borderRadius: 8,
                border: '1px solid rgba(255,69,58,0.35)',
                background: running ? 'rgba(255,69,58,0.22)' : 'rgba(255,69,58,0.1)',
                color: '#ff7b72',
                fontSize: 12,
                padding: '8px 10px',
                cursor: running ? 'pointer' : 'not-allowed',
              }}
            >
              Stop
            </button>
          </div>
        </div>

        <div
          style={{
            maxHeight: 180,
            overflowY: 'auto',
            borderRadius: 10,
            border: '1px solid rgba(255,255,255,0.08)',
            background: 'rgba(0,0,0,0.2)',
            padding: 8,
            display: 'grid',
            gap: 6,
          }}
        >
          {logs.length === 0 && (
            <div style={{ fontSize: 11, color: 'rgba(235,235,245,0.45)', padding: '8px 6px' }}>No steps yet.</div>
          )}
          {logs.map((entry) => (
            <div key={`${entry.step}-${entry.action}`} style={{ borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: 6 }}>
              <div style={{ fontSize: 11, color: '#f2f2f7' }}>Step {entry.step}: {entry.action}</div>
              {entry.reasoning && (
                <div style={{ fontSize: 10, color: 'rgba(235,235,245,0.55)', marginTop: 2 }}>{entry.reasoning}</div>
              )}
              {entry.screenshotAfter && (
                <img
                  src={`data:image/png;base64,${entry.screenshotAfter}`}
                  alt={`Step ${entry.step}`}
                  style={{ marginTop: 5, width: 82, borderRadius: 6, border: '1px solid rgba(255,255,255,0.1)' }}
                />
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
