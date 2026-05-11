import React, { useCallback, useEffect, useRef, useState } from 'react';

interface MetricsSummary {
  total_requests: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  tokens_per_second_avg: number;
  active_models: string[];
  vram_used_mb: number;
  vram_total_mb: number;
  queue_depth: number;
}

const PROXY_METRICS_URL = 'http://localhost:8105/proxy/metrics/summary';

function latencyColor(ms: number): string {
  if (ms < 200) return '#30d158';
  if (ms < 500) return '#ffd60a';
  return '#ff453a';
}

function tpsColor(tps: number): string {
  if (tps > 50) return '#30d158';
  if (tps > 20) return '#ffd60a';
  return '#ff453a';
}

export function PerformanceDashboard() {
  const [data, setData] = useState<MetricsSummary | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchMetrics = useCallback(async () => {
    try {
      const res = await fetch(PROXY_METRICS_URL);
      if (!res.ok) return;
      const json: MetricsSummary = await res.json();
      setData(json);
    } catch {
      // silently ignore – proxy may not be up yet
    }
  }, []);

  useEffect(() => {
    fetchMetrics();
    intervalRef.current = setInterval(fetchMetrics, 2000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchMetrics]);

  const panelStyle: React.CSSProperties = {
    position: 'fixed',
    bottom: 8,
    right: 8,
    zIndex: 50,
    width: 280,
    background: 'rgba(28, 28, 30, 0.75)',
    backdropFilter: 'blur(20px) saturate(180%)',
    WebkitBackdropFilter: 'blur(20px) saturate(180%)',
    border: '1px solid rgba(255,255,255,0.12)',
    borderRadius: 12,
    padding: '10px 12px',
    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif',
    fontSize: 12,
    color: '#ebebf5',
    boxShadow: '0 8px 32px rgba(0,0,0,0.45)',
    userSelect: 'none',
  };

  const headerStyle: React.CSSProperties = {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: collapsed ? 0 : 8,
    cursor: 'pointer',
  };

  const labelStyle: React.CSSProperties = {
    fontSize: 10,
    color: 'rgba(235,235,245,0.5)',
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    marginBottom: 2,
  };

  const rowStyle: React.CSSProperties = {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  };

  return (
    <div style={panelStyle}>
      <button
        type="button"
        style={{ ...headerStyle, background: 'transparent', border: 'none', width: '100%', padding: 0, textAlign: 'left' }}
        onClick={() => setCollapsed(c => !c)}
      >
        <span style={{ fontWeight: 600, fontSize: 11, letterSpacing: '0.3px' }}>
          ⚡ Vyrex Proxy
        </span>
        <span style={{ fontSize: 10, color: 'rgba(235,235,245,0.4)' }}>
          {collapsed ? '▲' : '▼'}
        </span>
      </button>

      {!collapsed && data && (
        <div>
          {/* Tokens/s */}
          <div style={rowStyle}>
            <span style={labelStyle}>Tokens/s</span>
            <span style={{ color: tpsColor(data.tokens_per_second_avg), fontWeight: 600 }}>
              {data.tokens_per_second_avg.toFixed(1)}
            </span>
          </div>

          {/* VRAM bar */}
          {data.vram_total_mb > 0 && (
            <div style={{ marginBottom: 6 }}>
              <div style={{ ...rowStyle, marginBottom: 3 }}>
                <span style={labelStyle}>VRAM</span>
                <span style={{ color: 'rgba(235,235,245,0.7)', fontSize: 10 }}>
                  {data.vram_used_mb} / {data.vram_total_mb} MB
                </span>
              </div>
              <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 3, height: 4, overflow: 'hidden' }}>
                <div
                  style={{
                    height: '100%',
                    width: `${Math.min(100, (data.vram_used_mb / data.vram_total_mb) * 100)}%`,
                    background: '#0a84ff',
                    borderRadius: 3,
                    transition: 'width 0.4s ease',
                  }}
                />
              </div>
            </div>
          )}
          {data.vram_total_mb === 0 && (
            <div style={{ ...rowStyle }}>
              <span style={labelStyle}>VRAM</span>
              <span style={{ color: 'rgba(235,235,245,0.3)', fontSize: 10 }}>N/A</span>
            </div>
          )}

          {/* Latency chips */}
          <div style={rowStyle}>
            <span style={labelStyle}>Avg Latency</span>
            <span
              style={{
                background: 'rgba(255,255,255,0.08)',
                borderRadius: 4,
                padding: '1px 6px',
                color: latencyColor(data.avg_latency_ms),
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              {data.avg_latency_ms.toFixed(0)} ms
            </span>
          </div>
          <div style={rowStyle}>
            <span style={labelStyle}>P95</span>
            <span
              style={{
                background: 'rgba(255,255,255,0.08)',
                borderRadius: 4,
                padding: '1px 6px',
                color: latencyColor(data.p95_latency_ms),
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              {data.p95_latency_ms.toFixed(0)} ms
            </span>
          </div>

          {/* Queue depth */}
          <div style={rowStyle}>
            <span style={labelStyle}>Queue</span>
            <span
              style={{
                background: data.queue_depth > 0 ? 'rgba(255,69,58,0.2)' : 'rgba(255,255,255,0.08)',
                color: data.queue_depth > 0 ? '#ff453a' : 'rgba(235,235,245,0.7)',
                borderRadius: 10,
                padding: '1px 7px',
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              {data.queue_depth}
            </span>
          </div>

          {/* Active models */}
          {data.active_models.length > 0 && (
            <div>
              <div style={labelStyle}>Active Models</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, marginTop: 2 }}>
                {data.active_models.slice(0, 3).map(m => (
                  <span
                    key={m}
                    style={{
                      background: 'rgba(10,132,255,0.18)',
                      color: '#0a84ff',
                      borderRadius: 4,
                      padding: '1px 6px',
                      fontSize: 10,
                      maxWidth: 80,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {m}
                  </span>
                ))}
                {data.active_models.length > 3 && (
                  <span style={{ color: 'rgba(235,235,245,0.4)', fontSize: 10 }}>
                    +{data.active_models.length - 3} more
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Total requests */}
          <div style={{ ...rowStyle, marginTop: 6, borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: 6 }}>
            <span style={labelStyle}>Total Requests</span>
            <span style={{ color: 'rgba(235,235,245,0.5)', fontVariantNumeric: 'tabular-nums' }}>
              {data.total_requests}
            </span>
          </div>
        </div>
      )}

      {!collapsed && !data && (
        <div style={{ color: 'rgba(235,235,245,0.3)', fontSize: 11, textAlign: 'center', padding: '8px 0' }}>
          Connecting to proxy…
        </div>
      )}
    </div>
  );
}
