import React, { useCallback, useEffect, useRef, useState } from 'react';
import TaskGraph from './TaskGraph';

interface TaskSummary {
  id: string;
  description: string;
  status: string;
  created_at: number;
}

interface SwarmPanelProps {
  onClose?: () => void;
}

export const SwarmPanel: React.FC<SwarmPanelProps> = ({ onClose }) => {
  const [description, setDescription] = useState('');
  const [maxAgents, setMaxAgents] = useState(3);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const fetchTasks = useCallback(async () => {
    try {
      const resp = await fetch('http://localhost:8104/swarm/tasks?limit=10&offset=0');
      if (resp.ok) {
        const data = await resp.json();
        setTasks(data.tasks ?? []);
      }
    } catch {
      // network unavailable — silently ignore
    }
  }, []);

  useEffect(() => {
    fetchTasks();
    const id = setInterval(fetchTasks, 5000);
    return () => clearInterval(id);
  }, [fetchTasks]);

  const handleSubmit = async () => {
    if (!description.trim()) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const resp = await fetch('http://localhost:8104/swarm/task', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: description.trim(), max_agents: maxAgents }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }));
        throw new Error(err.detail ?? `HTTP ${resp.status}`);
      }
      const body = await resp.json();
      setActiveTaskId(body.task_id);
      setDescription('');
      await fetchTasks();
    } catch (e) {
      setSubmitError(String(e));
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancel = async (taskId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await fetch(`http://localhost:8104/swarm/task/${taskId}`, { method: 'DELETE' });
      if (activeTaskId === taskId) setActiveTaskId(null);
      await fetchTasks();
    } catch {
      // ignore
    }
  };

  const statusColor = (status: string) => {
    switch (status) {
      case 'done': return '#34C759';
      case 'running': return '#007AFF';
      case 'failed': return '#FF3B30';
      case 'cancelled': return '#FF9500';
      default: return '#8E8E93';
    }
  };

  return (
    <aside
      style={{
        position: 'fixed',
        top: 0,
        right: 0,
        bottom: 0,
        width: 420,
        background: '#1C1C1E',
        borderLeft: '1px solid #3A3A3C',
        display: 'flex',
        flexDirection: 'column',
        zIndex: 200,
        fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif",
      }}
    >
      {/* Header */}
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '16px 20px',
          borderBottom: '1px solid #3A3A3C',
        }}
      >
        <span style={{ fontSize: 17, fontWeight: 600, color: '#F2F2F7' }}>Swarm Panel</span>
        <button
          aria-label="Close Swarm Panel"
          onClick={onClose}
          style={{
            background: 'none',
            border: 'none',
            color: '#8E8E93',
            fontSize: 20,
            cursor: 'pointer',
            lineHeight: 1,
          }}
        >
          ×
        </button>
      </header>

      {/* Create task form */}
      <section style={{ padding: '16px 20px', borderBottom: '1px solid #3A3A3C' }}>
        <label htmlFor="swarm-task-description" style={{ display: 'block', fontSize: 12, color: '#8E8E93', marginBottom: 6 }}>
          Task description
        </label>
        <textarea
          id="swarm-task-description"
          ref={inputRef}
          value={description}
          onChange={e => setDescription(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSubmit();
          }}
          placeholder="Describe the task for swarm agents…"
          rows={3}
          style={{
            width: '100%',
            background: '#2C2C2E',
            border: '1px solid #3A3A3C',
            borderRadius: 8,
            color: '#F2F2F7',
            fontSize: 13,
            padding: '8px 10px',
            resize: 'vertical',
            outline: 'none',
            boxSizing: 'border-box',
          }}
        />

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 10 }}>
          <label style={{ fontSize: 12, color: '#8E8E93', whiteSpace: 'nowrap' }}>
            Agents: <strong style={{ color: '#F2F2F7' }}>{maxAgents}</strong>
          </label>
          <input
            type="range"
            min={1}
            max={10}
            value={maxAgents}
            onChange={e => setMaxAgents(Number(e.target.value))}
            style={{ flex: 1, accentColor: '#007AFF' }}
          />
        </div>

        {submitError && (
          <p style={{ color: '#FF3B30', fontSize: 12, marginTop: 6 }}>{submitError}</p>
        )}

        <button
          onClick={handleSubmit}
          disabled={submitting || !description.trim()}
          style={{
            marginTop: 10,
            width: '100%',
            padding: '9px 0',
            background: submitting || !description.trim() ? '#3A3A3C' : '#007AFF',
            color: '#fff',
            border: 'none',
            borderRadius: 8,
            fontSize: 14,
            fontWeight: 600,
            cursor: submitting || !description.trim() ? 'not-allowed' : 'pointer',
            transition: 'background 0.15s',
          }}
        >
          {submitting ? 'Submitting…' : 'Start Swarm Task'}
        </button>
        <p style={{ fontSize: 11, color: '#636366', marginTop: 4, textAlign: 'right' }}>
          ⌘↵ to submit
        </p>
      </section>

      {/* Task graph for active task */}
      {activeTaskId && (
        <section style={{ padding: '14px 20px', borderBottom: '1px solid #3A3A3C' }}>
          <div style={{ fontSize: 12, color: '#8E8E93', marginBottom: 6 }}>Live Task Graph</div>
          <TaskGraph taskId={activeTaskId} />
        </section>
      )}

      {/* Recent tasks list */}
      <section style={{ flex: 1, overflowY: 'auto', padding: '14px 20px' }}>
        <div style={{ fontSize: 12, color: '#8E8E93', marginBottom: 8 }}>Recent Tasks</div>
        {tasks.length === 0 ? (
          <p style={{ color: '#636366', fontSize: 13 }}>No tasks yet.</p>
        ) : (
          <ul
            style={{ listStyle: 'none', margin: 0, padding: 0 }}
            aria-label="Recent swarm tasks"
          >
            {tasks.map((task, i) => (
              <li
                key={task.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 8,
                  padding: '9px 10px',
                  borderRadius: 8,
                  marginBottom: 4,
                  background: selectedIndex === i ? '#2C2C2E' : 'transparent',
                  border: activeTaskId === task.id ? '1px solid #007AFF55' : '1px solid transparent',
                  transition: 'background 0.1s',
                }}
              >
                <button
                  type="button"
                  onClick={() => { setActiveTaskId(task.id); setSelectedIndex(i); }}
                  style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: 0,
                    cursor: 'pointer',
                    background: 'transparent',
                    border: 'none',
                    textAlign: 'left',
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: 13,
                        color: '#F2F2F7',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {task.description}
                    </div>
                    <div style={{ fontSize: 11, color: '#636366', marginTop: 2 }}>
                      {new Date(task.created_at * 1000).toLocaleTimeString()}
                    </div>
                  </div>
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 600,
                      color: statusColor(task.status),
                      marginLeft: 8,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {task.status}
                  </span>
                </button>
                {(task.status === 'pending' || task.status === 'running') && (
                  <button
                    onClick={e => handleCancel(task.id, e)}
                    style={{
                      padding: '3px 8px',
                      background: 'none',
                      border: '1px solid #FF3B3055',
                      color: '#FF3B30',
                      borderRadius: 6,
                      fontSize: 11,
                      cursor: 'pointer',
                    }}
                  >
                    Cancel
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </aside>
  );
};

export default SwarmPanel;
