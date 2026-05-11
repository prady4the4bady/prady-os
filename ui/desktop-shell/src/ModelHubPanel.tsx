import React, { useEffect, useMemo, useState } from 'react';

type SourceType = 'huggingface' | 'github' | 'ollama';
type PullStatus = 'idle' | 'queued' | 'downloading' | 'converting' | 'registering' | 'done' | 'error';

interface PullResponse {
  job_id: string;
  status: 'queued';
}

interface ProgressEvent {
  job_id: string;
  percent: number;
  speed_mb_s: number;
  eta_s: number;
  status: 'downloading' | 'converting' | 'registering' | 'done' | 'error' | 'queued';
  message: string;
}

interface ModelItem {
  name: string;
  size?: number;
  modified_at?: string;
}

const API = 'http://localhost:8100/api/models';

function placeholderFor(source: SourceType): string {
  if (source === 'huggingface') return 'NousResearch/Lumyn-3-Llama-3.1-8B-GGUF';
  if (source === 'github') return 'https://raw.githubusercontent.com/.../model.gguf';
  return 'llama3:8b';
}

function badgeColor(status: PullStatus): string {
  if (status === 'done') return '#30d158';
  if (status === 'error') return '#ff453a';
  if (status === 'registering') return '#ffd60a';
  return '#0a84ff';
}

export default function ModelHubPanel() {
  const [source, setSource] = useState<SourceType>('huggingface');
  const [identifier, setIdentifier] = useState('');
  const [filename, setFilename] = useState('');
  const [alias, setAlias] = useState('');
  const [pullStatus, setPullStatus] = useState<PullStatus>('idle');
  const [progress, setProgress] = useState<ProgressEvent | null>(null);
  const [models, setModels] = useState<ModelItem[]>([]);
  const [defaultModel, setDefaultModel] = useState('');

  const style = useMemo<React.CSSProperties>(() => ({
    position: 'fixed',
    top: 76,
    right: 20,
    width: 520,
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

  const loadModels = async () => {
    try {
      const [modelsRes, configRes] = await Promise.all([
        fetch(`${API}/list`),
        fetch(`${API}/config`),
      ]);
      if (modelsRes.ok) {
        const modelsJson = await modelsRes.json();
        setModels(modelsJson.models || []);
      }
      if (configRes.ok) {
        const cfg = await configRes.json();
        setDefaultModel(cfg.default_model || '');
      }
    } catch {
      // no-op
    }
  };

  useEffect(() => {
    void loadModels();
  }, []);

  const startSse = (jobId: string) => {
    const es = new EventSource(`${API}/pull/${jobId}/progress`);
    es.onmessage = (ev) => {
      try {
        const data: ProgressEvent = JSON.parse(ev.data);
        setProgress(data);
        setPullStatus((data.status as PullStatus) || 'downloading');
        if (data.status === 'done' || data.status === 'error') {
          es.close();
          void loadModels();
        }
      } catch {
        // ignore malformed event
      }
    };
    es.onerror = () => {
      es.close();
      setPullStatus('error');
    };
  };

  const pullModel = async () => {
    if (!identifier.trim()) return;
    setPullStatus('queued');
    setProgress(null);

    const res = await fetch(`${API}/pull`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source,
        identifier,
        filename: filename.trim() || null,
        alias: alias.trim() || null,
      }),
    });

    if (!res.ok) {
      setPullStatus('error');
      return;
    }

    const body = (await res.json()) as PullResponse;
    startSse(body.job_id);
  };

  const setDefault = async (modelAlias: string) => {
    const res = await fetch(`${API}/set-default`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ alias: modelAlias }),
    });
    if (res.ok) {
      setDefaultModel(modelAlias);
    }
  };

  const deleteModel = async (modelAlias: string) => {
    if (!globalThis.confirm(`Delete model ${modelAlias}?`)) return;
    const res = await fetch(`${API}/${encodeURIComponent(modelAlias)}`, { method: 'DELETE' });
    if (res.ok) {
      void loadModels();
    }
  };

  return (
    <section style={style}>
      <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#30d158' }} />
        <strong style={{ fontSize: 13 }}>Active model: {defaultModel || 'not set'}</strong>
      </div>

      <div style={{ borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: 12 }}>
        <h3 style={{ margin: 0, marginBottom: 8, fontSize: 12 }}>Pull a Model</h3>
        <div style={{ display: 'grid', gap: 8 }}>
          <select value={source} onChange={(e) => setSource(e.target.value as SourceType)} style={{ borderRadius: 8, padding: 8, background: 'rgba(255,255,255,0.08)', color: '#fff', border: '1px solid rgba(255,255,255,0.12)' }}>
            <option value="huggingface">HuggingFace</option>
            <option value="github">GitHub</option>
            <option value="ollama">Ollama Registry</option>
          </select>
          <input value={identifier} onChange={(e) => setIdentifier(e.target.value)} placeholder={placeholderFor(source)} style={{ borderRadius: 8, padding: 8, background: 'rgba(255,255,255,0.08)', color: '#fff', border: '1px solid rgba(255,255,255,0.12)' }} />
          <input value={filename} onChange={(e) => setFilename(e.target.value)} placeholder="Optional filename" style={{ borderRadius: 8, padding: 8, background: 'rgba(255,255,255,0.08)', color: '#fff', border: '1px solid rgba(255,255,255,0.12)' }} />
          <input value={alias} onChange={(e) => setAlias(e.target.value)} placeholder="Optional alias" style={{ borderRadius: 8, padding: 8, background: 'rgba(255,255,255,0.08)', color: '#fff', border: '1px solid rgba(255,255,255,0.12)' }} />
          <button onClick={() => void pullModel()} style={{ borderRadius: 8, border: 'none', padding: '8px 10px', background: '#0a84ff', color: '#fff', cursor: 'pointer' }}>Pull Model</button>
        </div>

        {progress && (
          <div style={{ marginTop: 10, display: 'grid', gap: 5 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
              <span style={{ color: badgeColor(pullStatus) }}>{progress.status.toUpperCase()}</span>
              <span>{progress.percent.toFixed(1)}%</span>
            </div>
            <div style={{ height: 6, borderRadius: 6, background: 'rgba(255,255,255,0.1)', overflow: 'hidden' }}>
              <div style={{ width: `${Math.max(0, Math.min(100, progress.percent))}%`, height: '100%', background: '#0a84ff' }} />
            </div>
            <div style={{ fontSize: 11, color: 'rgba(235,235,245,0.8)' }}>
              {progress.message} • {progress.speed_mb_s} MB/s • ETA {progress.eta_s}s
            </div>
          </div>
        )}
      </div>

      <div style={{ marginTop: 14, borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: 12 }}>
        <h3 style={{ margin: 0, marginBottom: 8, fontSize: 12 }}>Installed Models</h3>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
          <thead>
            <tr style={{ color: 'rgba(235,235,245,0.65)' }}>
              <th style={{ textAlign: 'left', padding: '4px 6px' }}>Name</th>
              <th style={{ textAlign: 'left', padding: '4px 6px' }}>Size</th>
              <th style={{ textAlign: 'left', padding: '4px 6px' }}>Modified</th>
              <th style={{ textAlign: 'left', padding: '4px 6px' }}>Default</th>
              <th style={{ textAlign: 'left', padding: '4px 6px' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {models.map((m) => {
              const isDefault = m.name === defaultModel;
              return (
                <tr key={m.name} style={{ borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                  <td style={{ padding: '6px' }}>{m.name}</td>
                  <td style={{ padding: '6px' }}>{m.size ? `${(m.size / (1024 * 1024 * 1024)).toFixed(2)} GB` : '-'}</td>
                  <td style={{ padding: '6px' }}>{m.modified_at || '-'}</td>
                  <td style={{ padding: '6px' }}>{isDefault ? '★' : ''}</td>
                  <td style={{ padding: '6px', display: 'flex', gap: 6 }}>
                    <button onClick={() => void setDefault(m.name)} style={{ borderRadius: 6, border: '1px solid rgba(255,255,255,0.2)', background: 'rgba(255,255,255,0.08)', color: '#fff', padding: '2px 6px' }}>Set Default</button>
                    <button onClick={() => void deleteModel(m.name)} style={{ borderRadius: 6, border: '1px solid rgba(255,69,58,0.4)', background: 'rgba(255,69,58,0.16)', color: '#ff8b82', padding: '2px 6px' }}>Delete</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
