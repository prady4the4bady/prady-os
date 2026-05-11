import { useEffect, useState } from "react";
import {
  activateModel,
  deleteModel,
  listModels,
  streamPullModel,
} from "../api/models";
import type { ModelListItem } from "../types";

function coerceMessage(value: unknown, fallback: string): string {
  return typeof value === "string" && value.trim().length > 0 ? value : fallback;
}

export function ModelManager() {
  const [source, setSource] = useState("");
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState("idle");
  const [models, setModels] = useState<ModelListItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ModelListItem | null>(null);

  async function refreshModels() {
    try {
      const res = await listModels();
      setModels(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load models");
    }
  }

  useEffect(() => {
    void refreshModels();
  }, []);

  async function onPull() {
    if (!source.trim()) {
      return;
    }
    setStatus("pulling");
    setProgress(1);
    setError(null);

    try {
      await streamPullModel({ source: source.trim() }, ({ event, data }) => {
        if (event === "status") {
          const value = Number(data.progress ?? 0);
          setProgress(Number.isFinite(value) ? value : 0);
          const stage = coerceMessage(data.stage, "pulling");
          setStatus(stage);
        }
        if (event === "error") {
          setStatus("error");
          setError(coerceMessage(data.message, "pull failed"));
        }
        if (event === "complete") {
          setProgress(100);
          setStatus(coerceMessage(data.status, "ready"));
        }
      });
      await refreshModels();
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : "Pull failed");
    }
  }

  async function onActivate(modelId: string) {
    setError(null);
    try {
      await activateModel(modelId);
      setStatus(`activated:${modelId}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Activation failed");
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) {
      return;
    }
    setError(null);
    try {
      await deleteModel(deleteTarget.model_id);
      setDeleteTarget(null);
      await refreshModels();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  return (
    <div className="h-full p-4 text-sm space-y-3" data-testid="model-manager">
      <h2 className="text-base font-semibold">Model Manager</h2>

      <div className="flex gap-2">
        <input
          className="flex-1 rounded-xl px-3 py-2 bg-white/70 dark:bg-black/30 outline-none"
          placeholder="HuggingFace ID or GitHub URL"
          value={source}
          onChange={(e) => setSource(e.target.value)}
        />
        <button
          className="rounded-xl px-3 py-2 bg-black text-white dark:bg-white dark:text-black"
          onClick={() => void onPull()}
        >
          Pull
        </button>
      </div>

      <div className="rounded-xl bg-white/50 dark:bg-black/20 p-3">
        <div className="mb-1">Pull status: {status}</div>
        <div className="h-2 rounded bg-black/10 dark:bg-white/10 overflow-hidden">
          <div className="h-full bg-blue-500 transition-all" style={{ width: `${progress}%` }} />
        </div>
      </div>

      {error ? <div className="text-red-500">{error}</div> : null}

      <div className="rounded-xl bg-white/50 dark:bg-black/20 p-3 h-[calc(100%-205px)] overflow-auto">
        <div className="font-medium mb-2">Models</div>
        {models.length === 0 ? (
          <div className="opacity-70">No models loaded.</div>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left opacity-70">
                <th className="py-1">Name</th>
                <th className="py-1">Size (GB)</th>
                <th className="py-1">Score</th>
                <th className="py-1">Tok/s</th>
                <th className="py-1">Status</th>
                <th className="py-1">Actions</th>
              </tr>
            </thead>
            <tbody>
              {models.map((model) => (
                <tr key={model.model_id} className="border-t border-black/10 dark:border-white/10">
                  <td className="py-1">{model.name}</td>
                  <td className="py-1">{model.size_gb.toFixed(2)}</td>
                  <td className="py-1">{model.benchmark_score ?? "-"}</td>
                  <td className="py-1">{model.tokens_per_sec ?? "-"}</td>
                  <td className="py-1">
                    <span className="px-2 py-0.5 rounded bg-black/10 dark:bg-white/10">{model.status}</span>
                  </td>
                  <td className="py-1 flex gap-2">
                    <button
                      className="px-2 py-1 rounded bg-emerald-600 text-white"
                      onClick={() => void onActivate(model.model_id)}
                    >
                      Set as Default
                    </button>
                    <button
                      className="px-2 py-1 rounded bg-rose-600 text-white"
                      onClick={() => setDeleteTarget(model)}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {deleteTarget ? (
        <div className="absolute inset-0 bg-black/30 backdrop-blur-sm flex items-center justify-center">
          <div className="glass rounded-xl p-4 w-[360px]">
            <div className="font-medium">Delete model?</div>
            <div className="mt-1 text-xs opacity-75">{deleteTarget.name}</div>
            <div className="mt-3 flex justify-end gap-2">
              <button className="px-3 py-1 rounded bg-white/70 dark:bg-black/40" onClick={() => setDeleteTarget(null)}>
                Cancel
              </button>
              <button className="px-3 py-1 rounded bg-rose-600 text-white" onClick={() => void confirmDelete()}>
                Confirm Delete
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
