import React, { useEffect, useState } from 'react';

interface JobRecord {
  id: string;
  name: string;
  cron_expr: string | null;
  interval_seconds: number | null;
  payload: Record<string, unknown>;
  persona_id: string | null;
  enabled: boolean;
  last_run: string | null;
  next_run: string | null;
  created_at: string;
}

interface JobListResponse {
  jobs: JobRecord[];
  total: number;
}

interface JobRunRecord {
  id: string;
  job_id: string;
  status: string;
  result: string | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

interface JobRunsResponse {
  runs: JobRunRecord[];
  total: number;
}

interface JobFormState {
  name: string;
  scheduleType: 'cron' | 'interval';
  cron_expr: string;
  interval_seconds: string;
  payload: string;
  persona_id: string;
  enabled: boolean;
}

const API = 'http://localhost:8100/api/scheduler';

const emptyForm: JobFormState = {
  name: '',
  scheduleType: 'interval',
  cron_expr: '0 * * * *',
  interval_seconds: '60',
  payload: '{}',
  persona_id: '',
  enabled: true,
};

export default function SchedulerPanel() {
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState<JobFormState>(emptyForm);
  const [formErr, setFormErr] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [runs, setRuns] = useState<JobRunRecord[]>([]);
  const [runsTotal, setRunsTotal] = useState(0);
  const [runsLoading, setRunsLoading] = useState(false);

  const loadJobs = async () => {
    setLoading(true);
    setErr(null);
    try {
      const res = await fetch(`${API}/job`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: JobListResponse = await res.json();
      setJobs(data.jobs);
      setTotal(data.total);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'fetch failed');
    } finally {
      setLoading(false);
    }
  };

  const loadRuns = async (jobId: string) => {
    setRunsLoading(true);
    try {
      const res = await fetch(`${API}/job/${jobId}/runs?limit=20&offset=0`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: JobRunsResponse = await res.json();
      setRuns(data.runs);
      setRunsTotal(data.total);
    } catch {
      setRuns([]);
    } finally {
      setRunsLoading(false);
    }
  };

  useEffect(() => {
    void loadJobs();
  }, []);

  useEffect(() => {
    if (selectedJobId !== null) {
      void loadRuns(selectedJobId);
    }
  }, [selectedJobId]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormErr(null);
    setSubmitting(true);

    let parsedPayload: Record<string, unknown> = {};
    try {
      parsedPayload = JSON.parse(form.payload) as Record<string, unknown>;
    } catch {
      setFormErr('Payload must be valid JSON');
      setSubmitting(false);
      return;
    }

    const body: Record<string, unknown> = {
      name: form.name,
      payload: parsedPayload,
      enabled: form.enabled,
    };
    if (form.persona_id.trim()) body.persona_id = form.persona_id.trim();
    if (form.scheduleType === 'cron') {
      body.cron_expr = form.cron_expr;
    } else {
      const secs = Number.parseInt(form.interval_seconds, 10);
      if (Number.isNaN(secs) || secs < 1) {
        setFormErr('Interval must be a positive integer (seconds)');
        setSubmitting(false);
        return;
      }
      body.interval_seconds = secs;
    }

    try {
      const res = await fetch(`${API}/job`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const detail = (await res.json()) as { detail?: string };
        throw new Error(detail.detail ?? `HTTP ${res.status}`);
      }
      setForm(emptyForm);
      setCreateOpen(false);
      await loadJobs();
    } catch (e: unknown) {
      setFormErr(e instanceof Error ? e.message : 'create failed');
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggleEnabled = async (job: JobRecord) => {
    try {
      await fetch(`${API}/job/${job.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !job.enabled }),
      });
      await loadJobs();
    } catch {
      // ignore
    }
  };

  const handleDelete = async (jobId: string) => {
    if (!confirm('Delete this job?')) return;
    try {
      await fetch(`${API}/job/${jobId}`, { method: 'DELETE' });
      if (selectedJobId === jobId) setSelectedJobId(null);
      await loadJobs();
    } catch {
      // ignore
    }
  };

  const handleRunNow = async (jobId: string) => {
    try {
      await fetch(`${API}/job/${jobId}/run-now`, { method: 'POST' });
      setTimeout(() => void loadRuns(jobId), 1200);
    } catch {
      // ignore
    }
  };

  const panelStyle: React.CSSProperties = {
    position: 'fixed',
    top: 0,
    right: 0,
    bottom: 0,
    width: 520,
    background: 'rgba(18,18,20,0.97)',
    backdropFilter: 'blur(20px)',
    WebkitBackdropFilter: 'blur(20px)',
    borderLeft: '1px solid rgba(58,58,60,0.7)',
    zIndex: 100,
    display: 'flex',
    flexDirection: 'column',
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif",
    color: '#F2F2F7',
    overflowY: 'auto',
    padding: 24,
  };

  const headingStyle: React.CSSProperties = {
    fontSize: 18,
    fontWeight: 600,
    marginBottom: 16,
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  };

  const tableStyle: React.CSSProperties = {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: 12,
  };

  const thStyle: React.CSSProperties = {
    textAlign: 'left',
    color: '#8E8E93',
    fontWeight: 500,
    padding: '4px 8px',
    borderBottom: '1px solid rgba(58,58,60,0.5)',
  };

  const tdStyle: React.CSSProperties = {
    padding: '6px 8px',
    borderBottom: '1px solid rgba(44,44,46,0.7)',
    verticalAlign: 'middle',
  };

  const btnStyle: React.CSSProperties = {
    background: 'rgba(44,44,46,0.8)',
    border: '1px solid rgba(58,58,60,0.6)',
    borderRadius: 6,
    color: '#F2F2F7',
    cursor: 'pointer',
    fontSize: 11,
    padding: '3px 8px',
  };

  const inputStyle: React.CSSProperties = {
    background: 'rgba(44,44,46,0.9)',
    border: '1px solid rgba(58,58,60,0.7)',
    borderRadius: 6,
    color: '#F2F2F7',
    fontSize: 12,
    padding: '6px 10px',
    width: '100%',
    boxSizing: 'border-box',
  };

  const scheduleLabel = (job: JobRecord): string => {
    if (job.cron_expr) return `cron: ${job.cron_expr}`;
    if (job.interval_seconds !== null) return `every ${job.interval_seconds}s`;
    return '—';
  };

  const statusBadge = (status: string): React.CSSProperties => {
    let background = 'rgba(255,214,10,0.2)';
    let color = '#FFD60A';
    if (status === 'done') {
      background = 'rgba(48,209,88,0.2)';
      color = '#30D158';
    } else if (status === 'failed') {
      background = 'rgba(255,69,58,0.2)';
      color = '#FF453A';
    }

    return {
      display: 'inline-block',
      borderRadius: 4,
      padding: '1px 6px',
      fontSize: 10,
      fontWeight: 600,
      background,
      color,
    };
  };

  const jobPluralSuffix = total === 1 ? '' : 's';

  return (
    <div style={panelStyle}>
      <div style={headingStyle}>
        <span>⏰ Task Scheduler</span>
        <div style={{ display: 'flex', gap: 8 }}>
          <button type="button" style={btnStyle} onClick={() => void loadJobs()}>↺ Refresh</button>
          <button type="button" style={btnStyle} onClick={() => setCreateOpen(o => !o)}>
            {createOpen ? '✕ Cancel' : '+ New Job'}
          </button>
        </div>
      </div>

      {/* Create form */}
      {createOpen && (
        <form onSubmit={(e) => void handleCreate(e)} style={{ marginBottom: 20 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, background: 'rgba(28,28,30,0.8)', borderRadius: 10, padding: 16, border: '1px solid rgba(58,58,60,0.5)' }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#F2F2F7', marginBottom: 4 }}>Create New Job</div>

            <div>
              <div style={{ fontSize: 11, color: '#8E8E93', marginBottom: 4 }}>Name *</div>
              <input
                style={inputStyle}
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                placeholder="job-name"
                required
              />
            </div>

            <div>
              <div style={{ fontSize: 11, color: '#8E8E93', marginBottom: 4 }}>Schedule Type</div>
              <select
                style={inputStyle}
                value={form.scheduleType}
                onChange={e => setForm(f => ({ ...f, scheduleType: e.target.value as 'cron' | 'interval' }))}
              >
                <option value="interval">Interval (seconds)</option>
                <option value="cron">Cron Expression</option>
              </select>
            </div>

            {form.scheduleType === 'cron' ? (
              <div>
                <div style={{ fontSize: 11, color: '#8E8E93', marginBottom: 4 }}>Cron Expression *</div>
                <input
                  style={inputStyle}
                  value={form.cron_expr}
                  onChange={e => setForm(f => ({ ...f, cron_expr: e.target.value }))}
                  placeholder="0 * * * *"
                  required
                />
              </div>
            ) : (
              <div>
                <div style={{ fontSize: 11, color: '#8E8E93', marginBottom: 4 }}>Interval (seconds) *</div>
                <input
                  style={inputStyle}
                  type="number"
                  min={1}
                  value={form.interval_seconds}
                  onChange={e => setForm(f => ({ ...f, interval_seconds: e.target.value }))}
                  required
                />
              </div>
            )}

            <div>
              <div style={{ fontSize: 11, color: '#8E8E93', marginBottom: 4 }}>Persona ID (optional)</div>
              <input
                style={inputStyle}
                value={form.persona_id}
                onChange={e => setForm(f => ({ ...f, persona_id: e.target.value }))}
                placeholder="persona-uuid or leave blank"
              />
            </div>

            <div>
              <div style={{ fontSize: 11, color: '#8E8E93', marginBottom: 4 }}>Payload (JSON)</div>
              <textarea
                style={{ ...inputStyle, minHeight: 60, resize: 'vertical', fontFamily: 'monospace' }}
                value={form.payload}
                onChange={e => setForm(f => ({ ...f, payload: e.target.value }))}
              />
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input
                type="checkbox"
                id="sched-enabled"
                checked={form.enabled}
                onChange={e => setForm(f => ({ ...f, enabled: e.target.checked }))}
              />
              <label htmlFor="sched-enabled" style={{ fontSize: 12 }}>Enabled</label>
            </div>

            {formErr && <div style={{ color: '#FF453A', fontSize: 11 }}>{formErr}</div>}

            <button
              type="submit"
              disabled={submitting}
              style={{ ...btnStyle, background: 'rgba(10,132,255,0.3)', border: '1px solid rgba(10,132,255,0.5)', padding: '8px 16px', fontSize: 12 }}
            >
              {submitting ? 'Creating…' : 'Create Job'}
            </button>
          </div>
        </form>
      )}

      {/* Jobs table */}
      {err && <div style={{ color: '#FF453A', fontSize: 12, marginBottom: 10 }}>Error: {err}</div>}
      {loading && <div style={{ color: '#8E8E93', fontSize: 12, marginBottom: 10 }}>Loading…</div>}

      <div style={{ fontSize: 11, color: '#8E8E93', marginBottom: 8 }}>{total} job{jobPluralSuffix}</div>

      {jobs.length === 0 && !loading && (
        <div style={{ color: '#8E8E93', fontSize: 12, textAlign: 'center', padding: '24px 0' }}>
          No scheduled jobs yet. Click &ldquo;+ New Job&rdquo; to create one.
        </div>
      )}

      {jobs.length > 0 && (
        <table style={tableStyle}>
          <thead>
            <tr>
              <th style={thStyle}>Name</th>
              <th style={thStyle}>Schedule</th>
              <th style={thStyle}>Last Run</th>
              <th style={thStyle}>On</th>
              <th style={thStyle}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map(job => (
              <tr key={job.id} style={{ background: selectedJobId === job.id ? 'rgba(10,132,255,0.08)' : 'transparent' }}>
                <td style={{ ...tdStyle, fontWeight: 500 }}>
                  <button
                    type="button"
                    style={{ background: 'none', border: 'none', color: '#F2F2F7', cursor: 'pointer', fontSize: 12, fontWeight: 500, padding: 0, textAlign: 'left' }}
                    onClick={() => setSelectedJobId(selectedJobId === job.id ? null : job.id)}
                  >
                    {job.name}
                  </button>
                </td>
                <td style={{ ...tdStyle, color: '#8E8E93', fontFamily: 'monospace', fontSize: 11 }}>{scheduleLabel(job)}</td>
                <td style={{ ...tdStyle, color: '#8E8E93', fontSize: 10 }}>{job.last_run ? new Date(job.last_run).toLocaleString() : '—'}</td>
                <td style={tdStyle}>
                  <button
                    type="button"
                    style={{
                      background: job.enabled ? 'rgba(48,209,88,0.2)' : 'rgba(142,142,147,0.2)',
                      border: 'none',
                      borderRadius: 4,
                      color: job.enabled ? '#30D158' : '#8E8E93',
                      cursor: 'pointer',
                      fontSize: 10,
                      fontWeight: 600,
                      padding: '2px 8px',
                    }}
                    onClick={() => void handleToggleEnabled(job)}
                  >
                    {job.enabled ? 'ON' : 'OFF'}
                  </button>
                </td>
                <td style={{ ...tdStyle, display: 'flex', gap: 4 }}>
                  <button type="button" style={btnStyle} onClick={() => void handleRunNow(job.id)} title="Run now">▶</button>
                  <button type="button" style={{ ...btnStyle, color: '#FF453A' }} onClick={() => void handleDelete(job.id)} title="Delete">✕</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Run history drawer */}
      {selectedJobId !== null && (
        <div style={{ marginTop: 20, background: 'rgba(28,28,30,0.8)', borderRadius: 10, padding: 16, border: '1px solid rgba(58,58,60,0.5)' }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>Run History ({runsTotal})</span>
            <button type="button" style={btnStyle} onClick={() => void loadRuns(selectedJobId)}>↺</button>
          </div>
          {runsLoading && <div style={{ color: '#8E8E93', fontSize: 12 }}>Loading…</div>}
          {!runsLoading && runs.length === 0 && (
            <div style={{ color: '#8E8E93', fontSize: 12 }}>No runs yet.</div>
          )}
          {runs.map(run => (
            <div key={run.id} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 8, fontSize: 11 }}>
              <span style={statusBadge(run.status)}>{run.status}</span>
              <span style={{ color: '#8E8E93' }}>{new Date(run.started_at).toLocaleString()}</span>
              {run.error && <span style={{ color: '#FF453A', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{run.error}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
