import { useEffect, useRef, useState } from "react";
import { Cpu, X, Play, Gauge, Trash2, Download } from "lucide-react";

type ModelSource = "huggingface" | "github";
type Quantization = "q4" | "q8" | "f16" | "none";

interface ModelRecord {
  id: string;
  model_id: string;
  source: ModelSource;
  url: string;
  quantization: Quantization;
  size_bytes: number;
  path: string;
  is_active: boolean;
  pulled_at: string;
  last_used_at: string | null;
  benchmark_tps: number | null;
  benchmark_latency_ms: number | null;
}

interface ModelsResponse {
  models: ModelRecord[];
  total: number;
}

interface PullResponse {
  job_id: string;
  status: string;
}

interface ProgressEvent {
  job_id: string;
  status: "queued" | "downloading" | "complete" | "failed";
  message: string;
  bytes_downloaded: number;
  total_bytes: number;
  percent: number;
  speed_bps: number;
  error?: string | null;
}

interface BenchmarkResponse {
  model_id: string;
  tokens_per_second: number;
  latency_ms: number;
}

function applyBenchmark(
  models: ModelRecord[],
  modelId: string,
  benchmark: BenchmarkResponse
): ModelRecord[] {
  return models.map((model) => {
    if (model.model_id !== modelId) {
      return model;
    }

    return {
      ...model,
      benchmark_tps: benchmark.tokens_per_second,
      benchmark_latency_ms: benchmark.latency_ms,
      last_used_at: new Date().toISOString(),
    };
  });
}

function formatBytes(bytes: number): string {
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let n = bytes;
  let idx = 0;
  while (n >= 1024 && idx < units.length - 1) {
    n /= 1024;
    idx += 1;
  }
  return `${n.toFixed(idx === 0 ? 0 : 1)} ${units[idx]}`;
}

function formatDate(iso: string | null): string {
  if (!iso) return "Never";
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

function inferModelId(url: string): string {
  const cleaned = url.trim().replace(/\/+$/, "");
  if (!cleaned) return "model";
  try {
    const parsed = new URL(cleaned);
    const pieces = parsed.pathname.split("/").filter(Boolean);
    if (pieces.length >= 2) {
      const previous = pieces.at(-2) ?? "model";
      const last = pieces.at(-1) ?? "model";
      return `${previous}-${last}`
        .replaceAll(/[^a-zA-Z0-9-_]/g, "-")
        .toLowerCase();
    }
  } catch {
    // URL parse fallback below.
  }
  return cleaned
    .split("/")
    .filter(Boolean)
    .slice(-2)
    .join("-")
    .replaceAll(/[^a-zA-Z0-9-_]/g, "-")
    .toLowerCase() || "model";
}

interface ModelHubProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  layerZIndex?: number;
}

export function ModelHub({ open, onOpenChange, layerZIndex }: Readonly<ModelHubProps>): JSX.Element {
  const [internalOpen, setInternalOpen] = useState(false);
  const [models, setModels] = useState<ModelRecord[]>([]);
  const [source, setSource] = useState<ModelSource>("huggingface");
  const [url, setUrl] = useState("");
  const [quantization, setQuantization] = useState<Quantization>("q4");
  const [pullProgress, setPullProgress] = useState<ProgressEvent | null>(null);
  const [pulling, setPulling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [benchmarkingId, setBenchmarkingId] = useState<string | null>(null);
  const refreshRef = useRef<number | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const isControlled = open !== undefined;
  const isOpen = isControlled ? open : internalOpen;
  const baseZIndex = layerZIndex ?? 9000;

  const setOpenState = (next: boolean): void => {
    if (!isControlled) {
      setInternalOpen(next);
    }
    onOpenChange?.(next);
  };

  const active = models.find((m) => m.is_active) ?? null;

  const fetchModels = (): void => {
    void (async () => {
      try {
        const resp = await fetch("/api/models");
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const payload = (await resp.json()) as ModelsResponse;
        setModels(payload.models ?? []);
      } catch (e) {
        setError(`Failed to load models: ${String(e)}`);
      }
    })();
  };

  useEffect(() => {
    if (isOpen) {
      fetchModels();
      refreshRef.current = globalThis.setInterval(fetchModels, 60_000);
    } else if (refreshRef.current !== null) {
      globalThis.clearInterval(refreshRef.current);
      refreshRef.current = null;
    }

    return () => {
      if (refreshRef.current !== null) {
        globalThis.clearInterval(refreshRef.current);
        refreshRef.current = null;
      }
    };
  }, [isOpen]);

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, []);

  const startPull = (): void => {
    if (!url.trim()) {
      setError("Model URL is required.");
      return;
    }

    setError(null);
    setPulling(true);
    setPullProgress({
      job_id: "",
      status: "queued",
      message: "queued",
      bytes_downloaded: 0,
      total_bytes: 0,
      percent: 0,
      speed_bps: 0,
    });

    void (async () => {
      try {
        const req = {
          source,
          url: url.trim(),
          model_id: inferModelId(url),
          quantization,
        };
        const resp = await fetch("/api/models/pull", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(req),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

        const pull = (await resp.json()) as PullResponse;
        const es = new EventSource(`/api/models/pull/${pull.job_id}/progress`);
        eventSourceRef.current = es;

        es.onmessage = (evt: MessageEvent) => {
          try {
            const next = JSON.parse(evt.data) as ProgressEvent;
            setPullProgress(next);
            if (next.status === "complete" || next.status === "failed") {
              es.close();
              eventSourceRef.current = null;
              setPulling(false);
              fetchModels();
            }
          } catch {
            // ignore malformed event payloads
          }
        };

        es.onerror = () => {
          es.close();
          eventSourceRef.current = null;
          setPulling(false);
          setError("Pull stream disconnected.");
        };
      } catch (e) {
        setPulling(false);
        setError(`Pull failed: ${String(e)}`);
      }
    })();
  };

  const activateModel = (model: ModelRecord): void => {
    setError(null);
    setModels((prev) => prev.map((m) => ({ ...m, is_active: m.model_id === model.model_id })));

    void (async () => {
      try {
        const resp = await fetch(`/api/models/${encodeURIComponent(model.model_id)}/activate`, {
          method: "POST",
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        fetchModels();
      } catch (e) {
        setError(`Activate failed: ${String(e)}`);
        fetchModels();
      }
    })();
  };

  const benchmarkModel = (model: ModelRecord): void => {
    setBenchmarkingId(model.model_id);
    setError(null);

    void (async () => {
      try {
        const resp = await fetch(`/api/models/${encodeURIComponent(model.model_id)}/benchmark`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const payload = (await resp.json()) as BenchmarkResponse;
        setModels((prev) => applyBenchmark(prev, model.model_id, payload));
      } catch (e) {
        setError(`Benchmark failed: ${String(e)}`);
      } finally {
        setBenchmarkingId(null);
      }
    })();
  };

  const deleteModel = (model: ModelRecord): void => {
    const ok = globalThis.confirm(`Delete model ${model.model_id}? This removes local files.`);
    if (!ok) return;

    setError(null);
    void (async () => {
      try {
        const resp = await fetch(`/api/models/${encodeURIComponent(model.model_id)}`, {
          method: "DELETE",
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        fetchModels();
      } catch (e) {
        setError(`Delete failed: ${String(e)}`);
      }
    })();
  };

  return (
    <>
      <button
        type="button"
        aria-label="Model Hub"
        onClick={() => setOpenState(!isOpen)}
        style={{
          position: "fixed",
          top: 12,
          right: 128,
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
          gap: 6,
          fontSize: 12,
          fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif",
        }}
      >
        <Cpu size={14} />
        <span>Models</span>
      </button>

      {isOpen && (
        <>
          <button
            type="button"
            aria-label="Close model hub"
            onClick={() => setOpenState(false)}
            style={{
              position: "fixed",
              inset: 0,
              border: "none",
              background: "transparent",
              zIndex: baseZIndex,
            }}
          />

          <div
            style={{
              position: "fixed",
              top: 0,
              right: 0,
              width: 520,
              height: "100vh",
              background: "rgba(18,18,20,0.97)",
              backdropFilter: "blur(20px)",
              WebkitBackdropFilter: "blur(20px)",
              borderLeft: "1px solid rgba(58,58,60,0.8)",
              zIndex: baseZIndex + 1,
              display: "flex",
              flexDirection: "column",
              color: "#F2F2F7",
              fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "14px 16px",
                borderBottom: "1px solid rgba(58,58,60,0.6)",
                flexShrink: 0,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Cpu size={16} color="#0A84FF" />
                <span style={{ fontSize: 15, fontWeight: 600 }}>Model Hub</span>
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
                  display: "flex",
                }}
              >
                <X size={16} />
              </button>
            </div>

            <div style={{ padding: 16, overflowY: "auto", flex: 1 }}>
              <section
                style={{
                  border: "1px solid rgba(58,58,60,0.5)",
                  borderRadius: 10,
                  padding: 12,
                  marginBottom: 12,
                }}
              >
                <div style={{ fontSize: 12, color: "#8E8E93", marginBottom: 8 }}>Active Model</div>
                {active ? (
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 600 }}>{active.model_id}</div>
                    <div style={{ marginTop: 4, display: "flex", gap: 8, alignItems: "center" }}>
                      <span
                        style={{
                          background: "rgba(10,132,255,0.2)",
                          color: "#6FB5FF",
                          padding: "2px 8px",
                          borderRadius: 10,
                          fontSize: 11,
                          textTransform: "uppercase",
                        }}
                      >
                        {active.quantization}
                      </span>
                      <span style={{ fontSize: 12, color: "#A1A1A6" }}>
                        TPS: {active.benchmark_tps?.toFixed(2) ?? "—"}
                      </span>
                      <span style={{ fontSize: 12, color: "#A1A1A6" }}>
                        Latency: {active.benchmark_latency_ms?.toFixed(1) ?? "—"} ms
                      </span>
                    </div>
                  </div>
                ) : (
                  <div style={{ fontSize: 13, color: "#636366" }}>No active model</div>
                )}
              </section>

              <section
                style={{
                  border: "1px solid rgba(58,58,60,0.5)",
                  borderRadius: 10,
                  padding: 12,
                  marginBottom: 12,
                }}
              >
                <div style={{ fontSize: 12, color: "#8E8E93", marginBottom: 8 }}>Pull New Model</div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
                  <select
                    value={source}
                    onChange={(e) => setSource(e.target.value as ModelSource)}
                    style={{
                      background: "rgba(44,44,46,0.8)",
                      color: "#F2F2F7",
                      border: "1px solid rgba(72,72,74,0.8)",
                      borderRadius: 8,
                      padding: "8px 10px",
                    }}
                  >
                    <option value="huggingface">HuggingFace</option>
                    <option value="github">GitHub</option>
                  </select>

                  <select
                    value={quantization}
                    onChange={(e) => setQuantization(e.target.value as Quantization)}
                    style={{
                      background: "rgba(44,44,46,0.8)",
                      color: "#F2F2F7",
                      border: "1px solid rgba(72,72,74,0.8)",
                      borderRadius: 8,
                      padding: "8px 10px",
                    }}
                  >
                    <option value="q4">Q4</option>
                    <option value="q8">Q8</option>
                    <option value="f16">F16</option>
                    <option value="none">None</option>
                  </select>
                </div>

                <input
                  type="text"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://huggingface.co/org/model or https://github.com/org/repo"
                  style={{
                    width: "100%",
                    background: "rgba(44,44,46,0.8)",
                    color: "#F2F2F7",
                    border: "1px solid rgba(72,72,74,0.8)",
                    borderRadius: 8,
                    padding: "8px 10px",
                    marginBottom: 8,
                  }}
                />

                <button
                  type="button"
                  onClick={startPull}
                  disabled={pulling || !url.trim()}
                  style={{
                    background: pulling ? "#636366" : "#0A84FF",
                    color: "#FFFFFF",
                    border: "none",
                    borderRadius: 8,
                    padding: "8px 12px",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                    cursor: pulling ? "default" : "pointer",
                  }}
                >
                  <Download size={14} /> Pull
                </button>

                {pullProgress && (
                  <div style={{ marginTop: 10 }}>
                    <div style={{ fontSize: 12, color: "#8E8E93", marginBottom: 4 }}>
                      {pullProgress.message} ({pullProgress.percent.toFixed(1)}%)
                    </div>
                    <div
                      style={{
                        height: 8,
                        borderRadius: 999,
                        background: "rgba(72,72,74,0.7)",
                        overflow: "hidden",
                      }}
                    >
                      <div
                        style={{
                          height: "100%",
                          width: `${Math.max(0, Math.min(100, pullProgress.percent))}%`,
                          background: pullProgress.status === "failed" ? "#FF3B30" : "#0A84FF",
                          transition: "width 180ms ease",
                        }}
                      />
                    </div>
                    <div style={{ marginTop: 4, fontSize: 11, color: "#A1A1A6" }}>
                      {formatBytes(pullProgress.bytes_downloaded)} / {formatBytes(pullProgress.total_bytes)}
                      {pullProgress.speed_bps > 0
                        ? ` - ${(pullProgress.speed_bps / (1024 * 1024)).toFixed(2)} MB/s`
                        : ""}
                    </div>
                  </div>
                )}
              </section>

              <section>
                <div style={{ fontSize: 12, color: "#8E8E93", marginBottom: 8 }}>Installed Models</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {models.length === 0 && (
                    <div style={{ fontSize: 13, color: "#636366" }}>No installed models.</div>
                  )}

                  {models.map((model) => (
                    <div
                      key={model.model_id}
                      style={{
                        border: "1px solid rgba(58,58,60,0.5)",
                        borderRadius: 10,
                        padding: 10,
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                        <div>
                          <div style={{ fontSize: 13, fontWeight: 600 }}>{model.model_id}</div>
                          <div style={{ fontSize: 11, color: "#8E8E93" }}>
                            {formatBytes(model.size_bytes)} - {model.quantization.toUpperCase()} - Last used {formatDate(model.last_used_at)}
                          </div>
                        </div>
                        {model.is_active && (
                          <span
                            style={{
                              background: "rgba(52,199,89,0.2)",
                              color: "#74E08F",
                              fontSize: 10,
                              borderRadius: 10,
                              padding: "2px 8px",
                              height: 18,
                            }}
                          >
                            ACTIVE
                          </span>
                        )}
                      </div>

                      <div style={{ marginTop: 8, display: "flex", gap: 6 }}>
                        <button
                          type="button"
                          onClick={() => activateModel(model)}
                          style={{
                            background: "rgba(10,132,255,0.18)",
                            color: "#6FB5FF",
                            border: "1px solid rgba(10,132,255,0.5)",
                            borderRadius: 8,
                            padding: "6px 9px",
                            display: "inline-flex",
                            gap: 4,
                            alignItems: "center",
                            cursor: "pointer",
                            fontSize: 12,
                          }}
                        >
                          <Play size={12} /> Activate
                        </button>

                        <button
                          type="button"
                          onClick={() => benchmarkModel(model)}
                          disabled={benchmarkingId === model.model_id}
                          style={{
                            background: "rgba(255,159,10,0.18)",
                            color: "#FFD08A",
                            border: "1px solid rgba(255,159,10,0.5)",
                            borderRadius: 8,
                            padding: "6px 9px",
                            display: "inline-flex",
                            gap: 4,
                            alignItems: "center",
                            cursor: benchmarkingId === model.model_id ? "default" : "pointer",
                            fontSize: 12,
                          }}
                        >
                          <Gauge size={12} />
                          {benchmarkingId === model.model_id ? "Benchmarking..." : "Benchmark"}
                        </button>

                        <button
                          type="button"
                          onClick={() => deleteModel(model)}
                          style={{
                            background: "rgba(255,59,48,0.18)",
                            color: "#FF918B",
                            border: "1px solid rgba(255,59,48,0.5)",
                            borderRadius: 8,
                            padding: "6px 9px",
                            display: "inline-flex",
                            gap: 4,
                            alignItems: "center",
                            cursor: "pointer",
                            fontSize: 12,
                          }}
                        >
                          <Trash2 size={12} /> Delete
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              {error && (
                <div style={{ marginTop: 10, color: "#FF7D75", fontSize: 12 }}>{error}</div>
              )}
            </div>
          </div>
        </>
      )}
    </>
  );
}

export default ModelHub;
