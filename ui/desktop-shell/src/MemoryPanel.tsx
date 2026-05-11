import React, { useEffect, useMemo, useState } from 'react';

type MemoryType = 'task' | 'preference' | 'conversation' | 'shortcut' | 'fact';

interface MemoryRecord {
  id: string;
  type: MemoryType;
  content: string;
  tags: string[];
  importance: number;
  access_count: number;
  created_at: string;
  score: number;
}

interface SessionRecord {
  id: string;
  started_at: string;
  ended_at?: string;
  summary?: string;
  task_count: number;
}

const API = 'http://localhost:8100/api';

function typeColor(type: MemoryType): string {
  if (type === 'task') return '#0a84ff';
  if (type === 'preference') return '#30d158';
  if (type === 'conversation') return '#ffd60a';
  if (type === 'shortcut') return '#bf5af2';
  return '#8e8e93';
}

function stars(importance: number): string {
  const n = Math.max(1, Math.min(5, Math.round(importance * 5)));
  return '★★★★★'.slice(0, n) + '☆☆☆☆☆'.slice(0, 5 - n);
}

function relativeTime(iso: string): string {
  const t = new Date(iso).getTime();
  const diff = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export default function MemoryPanel() {
  const [q, setQ] = useState('');
  const [results, setResults] = useState<MemoryRecord[]>([]);
  const [sessions, setSessions] = useState<SessionRecord[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [type, setType] = useState<MemoryType>('fact');
  const [content, setContent] = useState('');
  const [tags, setTags] = useState('');
  const [importance, setImportance] = useState(0.5);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  const totalCount = results.length;

  const loadSessions = async () => {
    try {
      const res = await fetch(`${API}/session/list?user_id=default&limit=20`);
      if (!res.ok) return;
      const data = await res.json();
      setSessions(data.sessions || []);
    } catch {
      // no-op
    }
  };

  const runSearch = async (query: string) => {
    try {
      const params = new URLSearchParams({ q: query, user_id: 'default', top_k: '20' });
      const res = await fetch(`${API}/memory/search?${params.toString()}`);
      if (!res.ok) return;
      const data = await res.json();
      setResults(data.results || []);
    } catch {
      // no-op
    }
  };

  useEffect(() => {
    void runSearch('');
    void loadSessions();
  }, []);

  useEffect(() => {
    const handle = setTimeout(() => {
      void runSearch(q);
    }, 300);
    return () => clearTimeout(handle);
  }, [q]);

  const addMemory = async () => {
    if (!content.trim()) return;
    const tagArr = tags
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    const res = await fetch(`${API}/memory`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, content, tags: tagArr, importance }),
    });
    if (res.ok) {
      setContent('');
      setTags('');
      setImportance(0.5);
      setShowAdd(false);
      void runSearch(q);
    }
  };

  const startSession = async () => {
    const res = await fetch(`${API}/session/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: 'default' }),
    });
    if (res.ok) {
      const data = await res.json();
      setActiveSessionId(data.session_id);
      void loadSessions();
    }
  };

  const endSession = async () => {
    if (!activeSessionId) return;
    const res = await fetch(`${API}/session/end`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: activeSessionId, summary: 'Session ended from UI' }),
    });
    if (res.ok) {
      setActiveSessionId(null);
      void loadSessions();
    }
  };

  const style = useMemo<React.CSSProperties>(() => ({
    position: 'fixed',
    left: 20,
    top: 76,
    width: 560,
    maxHeight: '76vh',
    overflow: 'auto',
    zIndex: 49,
    borderRadius: 14,
    border: '1px solid rgba(255,255,255,0.12)',
    background: 'rgba(28, 28, 30, 0.72)',
    backdropFilter: 'blur(20px) saturate(180%)',
    WebkitBackdropFilter: 'blur(20px) saturate(180%)',
    boxShadow: '0 10px 30px rgba(0,0,0,0.35)',
    color: '#ebebf5',
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif",
    padding: 14,
  }), []);

  return (
    <section style={style}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10, fontSize: 12 }}>
        <strong>Memory</strong>
        <span>Total memories: {totalCount} • Session: {activeSessionId ? 'ACTIVE' : 'IDLE'}</span>
      </div>

      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search memory..."
        style={{ width: '100%', borderRadius: 8, border: '1px solid rgba(255,255,255,0.14)', background: 'rgba(255,255,255,0.06)', color: '#fff', padding: '8px 10px', marginBottom: 10 }}
      />

      <button onClick={() => setShowAdd((v) => !v)} style={{ borderRadius: 8, border: '1px solid rgba(255,255,255,0.2)', background: 'rgba(255,255,255,0.08)', color: '#fff', padding: '6px 10px', marginBottom: 10 }}>
        {showAdd ? 'Hide Add Memory' : 'Add Memory'}
      </button>

      {showAdd && (
        <div style={{ border: '1px solid rgba(255,255,255,0.08)', borderRadius: 10, padding: 10, marginBottom: 12, display: 'grid', gap: 8 }}>
          <select value={type} onChange={(e) => setType(e.target.value as MemoryType)} style={{ borderRadius: 8, padding: 8, background: 'rgba(255,255,255,0.08)', color: '#fff', border: '1px solid rgba(255,255,255,0.12)' }}>
            <option value="task">task</option>
            <option value="preference">preference</option>
            <option value="conversation">conversation</option>
            <option value="shortcut">shortcut</option>
            <option value="fact">fact</option>
          </select>
          <textarea value={content} onChange={(e) => setContent(e.target.value)} placeholder="Memory content" rows={3} style={{ borderRadius: 8, padding: 8, background: 'rgba(255,255,255,0.08)', color: '#fff', border: '1px solid rgba(255,255,255,0.12)' }} />
          <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="tags,comma,separated" style={{ borderRadius: 8, padding: 8, background: 'rgba(255,255,255,0.08)', color: '#fff', border: '1px solid rgba(255,255,255,0.12)' }} />
          <label style={{ fontSize: 11 }}>Importance: {importance.toFixed(2)}</label>
          <input type="range" min={0} max={1} step={0.01} value={importance} onChange={(e) => setImportance(Number(e.target.value))} />
          <button onClick={() => void addMemory()} style={{ borderRadius: 8, border: 'none', background: '#0a84ff', color: '#fff', padding: '8px 10px' }}>Save Memory</button>
        </div>
      )}

      <div style={{ display: 'grid', gap: 8, marginBottom: 14 }}>
        {results.map((m) => (
          <article key={m.id} style={{ border: '1px solid rgba(255,255,255,0.08)', borderRadius: 10, padding: 10, background: 'rgba(0,0,0,0.2)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <span style={{ color: typeColor(m.type), fontSize: 11 }}>{m.type.toUpperCase()}</span>
              <span style={{ fontSize: 10, color: 'rgba(235,235,245,0.6)' }}>{relativeTime(m.created_at)}</span>
            </div>
            <div style={{ fontSize: 12, marginBottom: 6 }}>{m.content}</div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 4 }}>
              {m.tags?.map((t) => (
                <span key={t} style={{ fontSize: 10, borderRadius: 999, padding: '2px 6px', background: 'rgba(255,255,255,0.1)' }}>{t}</span>
              ))}
            </div>
            <div style={{ fontSize: 10, color: 'rgba(235,235,245,0.65)' }}>
              {stars(m.importance)} • Access {m.access_count}
            </div>
          </article>
        ))}
      </div>

      <aside style={{ borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: 10 }}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
          <button onClick={() => void startSession()} style={{ borderRadius: 8, border: 'none', background: '#30d158', color: '#fff', padding: '6px 10px' }}>Start Session</button>
          <button onClick={() => void endSession()} style={{ borderRadius: 8, border: 'none', background: '#ff453a', color: '#fff', padding: '6px 10px' }}>End Session</button>
        </div>
        <div style={{ display: 'grid', gap: 6 }}>
          {sessions.map((s) => (
            <div key={s.id} style={{ fontSize: 11, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, padding: 8 }}>
              <div>{relativeTime(s.started_at)} • tasks {s.task_count}</div>
              <div style={{ color: 'rgba(235,235,245,0.6)' }}>{s.summary || 'No summary'}</div>
            </div>
          ))}
        </div>
      </aside>
    </section>
  );
}
