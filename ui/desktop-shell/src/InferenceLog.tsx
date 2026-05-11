import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

interface InferenceRecord {
  id: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  latency_ms: number;
  timestamp: number;
  status: string;
}

interface InferenceLogProps {
  onClose: () => void;
}

const PROXY_URL = 'http://localhost:8105/proxy/metrics';
const ROW_HEIGHT = 36;
const VISIBLE_ROWS = 15;

function formatTs(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour12: false });
}

function statusColor(status: string): string {
  return status === 'success' ? '#30d158' : '#ff453a';
}

export function InferenceLog({ onClose }: Readonly<InferenceLogProps>) {
  const [records, setRecords] = useState<InferenceRecord[]>([]);
  const [modelFilter, setModelFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'success' | 'error'>('all');
  const [scrollTop, setScrollTop] = useState(0);
  const viewportRef = useRef<HTMLDivElement>(null);

  const fetchLogs = useCallback(async () => {
    try {
      const res = await fetch(PROXY_URL);
      if (!res.ok) return;
      const json = await res.json();
      const recs: InferenceRecord[] = json.requests ?? [];
      setRecords(recs.slice().reverse());
    } catch {
      // proxy may not be running
    }
  }, []);

  useEffect(() => {
    fetchLogs();
    const id = setInterval(fetchLogs, 2000);
    return () => clearInterval(id);
  }, [fetchLogs]);

  // ⌘I / Escape to close
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' || (e.metaKey && e.key === 'i')) {
        e.preventDefault();
        onClose();
      }
    };
    globalThis.addEventListener('keydown', handleKey);
    return () => globalThis.removeEventListener('keydown', handleKey);
  }, [onClose]);

  const filtered = useMemo(() => {
    return records.filter(r => {
      const matchModel = modelFilter === '' || r.model.toLowerCase().includes(modelFilter.toLowerCase());
      const matchStatus = statusFilter === 'all' || r.status === statusFilter;
      return matchModel && matchStatus;
    });
  }, [records, modelFilter, statusFilter]);

  const totalHeight = filtered.length * ROW_HEIGHT;
  const startIdx = Math.floor(scrollTop / ROW_HEIGHT);
  const endIdx = Math.min(filtered.length, startIdx + VISIBLE_ROWS + 2);
  const visibleRows = filtered.slice(startIdx, endIdx);

  const handleExportCSV = () => {
    const header = 'id,model,prompt_tokens,completion_tokens,latency_ms,timestamp,status\n';
    const rows = filtered
      .map(r =>
        [r.id, r.model, r.prompt_tokens, r.completion_tokens, r.latency_ms, r.timestamp, r.status].join(',')
      )
      .join('\n');
    const blob = new Blob([header + rows], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `inference-log-${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const overlayStyle: React.CSSProperties = {
    position: 'fixed',
    inset: 0,
    zIndex: 60,
    display: 'flex',
    justifyContent: 'flex-end',
    background: 'rgba(0,0,0,0.3)',
  };

  const drawerStyle: React.CSSProperties = {
    width: 560,
    height: '100vh',
    background: 'rgba(28, 28, 30, 0.85)',
    backdropFilter: 'blur(28px) saturate(180%)',
    WebkitBackdropFilter: 'blur(28px) saturate(180%)',
    borderLeft: '1px solid rgba(255,255,255,0.1)',
    display: 'flex',
    flexDirection: 'column',
    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif',
    color: '#ebebf5',
    boxShadow: '-8px 0 40px rgba(0,0,0,0.5)',
  };

  const headerStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '16px 16px 12px',
    borderBottom: '1px solid rgba(255,255,255,0.08)',
  };

  const controlsStyle: React.CSSProperties = {
    display: 'flex',
    gap: 8,
    padding: '10px 16px',
    borderBottom: '1px solid rgba(255,255,255,0.06)',
    alignItems: 'center',
  };

  const inputStyle: React.CSSProperties = {
    background: 'rgba(255,255,255,0.07)',
    border: '1px solid rgba(255,255,255,0.1)',
    borderRadius: 6,
    color: '#ebebf5',
    padding: '4px 8px',
    fontSize: 12,
    outline: 'none',
    flex: 1,
  };

  const selectStyle: React.CSSProperties = {
    background: 'rgba(255,255,255,0.07)',
    border: '1px solid rgba(255,255,255,0.1)',
    borderRadius: 6,
    color: '#ebebf5',
    padding: '4px 8px',
    fontSize: 12,
    outline: 'none',
  };

  const colHeaderStyle: React.CSSProperties = {
    display: 'grid',
    gridTemplateColumns: '1fr 80px 60px 60px 80px 60px',
    gap: 6,
    padding: '6px 16px',
    fontSize: 10,
    color: 'rgba(235,235,245,0.4)',
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    borderBottom: '1px solid rgba(255,255,255,0.06)',
    flexShrink: 0,
  };

  return (
    <div style={overlayStyle}>
      <div style={drawerStyle}>
        {/* Header */}
        <div style={headerStyle}>
          <span style={{ fontWeight: 700, fontSize: 14 }}>Inference Log</span>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <button
              onClick={handleExportCSV}
              style={{
                background: 'rgba(10,132,255,0.2)',
                border: '1px solid rgba(10,132,255,0.4)',
                borderRadius: 6,
                color: '#0a84ff',
                padding: '4px 10px',
                fontSize: 11,
                cursor: 'pointer',
              }}
            >
              Export CSV
            </button>
            <button
              onClick={onClose}
              style={{
                background: 'rgba(255,255,255,0.08)',
                border: '1px solid rgba(255,255,255,0.12)',
                borderRadius: 6,
                color: '#ebebf5',
                padding: '4px 10px',
                fontSize: 11,
                cursor: 'pointer',
              }}
            >
              ✕
            </button>
          </div>
        </div>

        {/* Filters */}
        <div style={controlsStyle}>
          <input
            style={inputStyle}
            placeholder="Filter by model…"
            value={modelFilter}
            onChange={e => setModelFilter(e.target.value)}
          />
          <select
            style={selectStyle}
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value as 'all' | 'success' | 'error')}
          >
            <option value="all">All</option>
            <option value="success">Success</option>
            <option value="error">Error</option>
          </select>
          <span style={{ fontSize: 10, color: 'rgba(235,235,245,0.35)', whiteSpace: 'nowrap' }}>
            {filtered.length} records
          </span>
        </div>

        {/* Column headers */}
        <div style={colHeaderStyle}>
          <span>Model</span>
          <span>In Tokens</span>
          <span>Out</span>
          <span>Latency</span>
          <span>Time</span>
          <span>Status</span>
        </div>

        {/* CSS-only virtualized list */}
        <div
          ref={viewportRef}
          style={{ flex: 1, overflowY: 'auto', position: 'relative' }}
          onScroll={e => setScrollTop((e.currentTarget as HTMLDivElement).scrollTop)}
        >
          {/* full height spacer */}
          <div style={{ height: totalHeight, position: 'relative' }}>
            {visibleRows.map((r, i) => {
              const top = (startIdx + i) * ROW_HEIGHT;
              return (
                <div
                  key={r.id}
                  style={{
                    position: 'absolute',
                    top,
                    left: 0,
                    right: 0,
                    height: ROW_HEIGHT,
                    display: 'grid',
                    gridTemplateColumns: '1fr 80px 60px 60px 80px 60px',
                    gap: 6,
                    alignItems: 'center',
                    padding: '0 16px',
                    fontSize: 11,
                    borderBottom: '1px solid rgba(255,255,255,0.04)',
                    background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)',
                  }}
                >
                  <span
                    style={{
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      color: '#0a84ff',
                      fontVariantNumeric: 'tabular-nums',
                    }}
                  >
                    {r.model}
                  </span>
                  <span style={{ fontVariantNumeric: 'tabular-nums', color: 'rgba(235,235,245,0.7)' }}>
                    {r.prompt_tokens}
                  </span>
                  <span style={{ fontVariantNumeric: 'tabular-nums', color: 'rgba(235,235,245,0.7)' }}>
                    {r.completion_tokens}
                  </span>
                  <span style={{ fontVariantNumeric: 'tabular-nums', color: 'rgba(235,235,245,0.6)' }}>
                    {r.latency_ms.toFixed(0)} ms
                  </span>
                  <span style={{ fontVariantNumeric: 'tabular-nums', color: 'rgba(235,235,245,0.4)', fontSize: 10 }}>
                    {formatTs(r.timestamp)}
                  </span>
                  <span
                    style={{
                      color: statusColor(r.status),
                      fontSize: 10,
                      fontWeight: 600,
                      textTransform: 'uppercase',
                    }}
                  >
                    {r.status}
                  </span>
                </div>
              );
            })}
          </div>

          {filtered.length === 0 && (
            <div
              style={{
                textAlign: 'center',
                color: 'rgba(235,235,245,0.3)',
                padding: '32px 0',
                fontSize: 12,
              }}
            >
              No records yet
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
