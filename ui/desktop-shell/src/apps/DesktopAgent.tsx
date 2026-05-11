import { useCallback, useRef, useState } from "react";

const SWARM_BASE = (import.meta.env as Record<string, string>)
  .VITE_SWARM_URL ?? "http://localhost:8000";

interface StepEvent {
  type: "step";
  task_id: string;
  step: number;
  action: string;
  params: Record<string, unknown>;
  reasoning: string;
  screenshot_b64?: string;
  screen_description?: string;
  success: boolean;
  error?: string;
  timestamp?: number;
}

interface ResultEvent {
  type: "result";
  task_id: string;
  goal: string;
  user_id?: string;
  steps_taken: number;
  success: boolean;
  final_screenshot_b64?: string;
  summary: string;
  duration_seconds?: number;
  error?: string;
}

type FeedEvent = StepEvent | ResultEvent;

export function DesktopAgent() {
  const [goal, setGoal] = useState("");
  const [running, setRunning] = useState(false);
  const [feed, setFeed] = useState<FeedEvent[]>([]);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [result, setResult] = useState<ResultEvent | null>(null);
  const abortRef = useRef<(() => void) | null>(null);

  const processEvent = useCallback(
    (event: FeedEvent) => {
      if (event.type === "step" && !taskId) setTaskId(event.task_id);
      if (event.type === "result") setResult(event);
      setFeed((prev) => [...prev, event]);
    },
    [taskId]
  );

  const readStream = useCallback(
    async (reader: ReadableStreamDefaultReader<Uint8Array>, abortFn: () => boolean) => {
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done || abortFn()) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data:")) continue;
          try {
            processEvent(JSON.parse(line.slice(5).trim()) as FeedEvent);
          } catch { /* malformed JSON */ }
        }
      }
    },
    [processEvent]
  );

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!goal.trim() || running) return;

      setFeed([]);
      setResult(null);
      setRunning(true);

      try {
        const res = await fetch(`${SWARM_BASE}/task/execute`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ goal, user_id: "ui-user", max_steps: 20 }),
        });

        if (!res.body) throw new Error("No response body");

        const reader = res.body.getReader();
        let aborted = false;
        abortRef.current = () => { aborted = true; reader.cancel(); };
        await readStream(reader, () => aborted);
      } catch (err) {
        console.error("Task stream error:", err);
      } finally {
        setRunning(false);
        abortRef.current = null;
      }
    },
    [goal, running, readStream]
  );

  const handleStop = useCallback(async () => {
    if (abortRef.current) abortRef.current();
    if (taskId) {
      await fetch(`${SWARM_BASE}/task/${taskId}`, { method: "DELETE" }).catch(() => {});
    }
    setRunning(false);
  }, [taskId]);

  const stepEvents = feed.filter((e): e is StepEvent => e.type === "step");
  const stepCount = stepEvents.length;

  return (
    <div className="h-full p-3 flex flex-col gap-3 text-sm">
      <div className="font-semibold text-base">Desktop Agent</div>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          className="flex-1 rounded-lg px-3 py-1.5 bg-white/20 focus:outline-none focus:ring-2 focus:ring-blue-400"
          placeholder="Describe the goal for the agent…"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          disabled={running}
        />
        {running ? (
          <button
            type="button"
            onClick={handleStop}
            className="px-3 py-1.5 rounded-lg bg-red-500 text-white font-medium hover:bg-red-600"
          >
            Stop
          </button>
        ) : (
          <button
            type="submit"
            disabled={!goal.trim()}
            className="px-3 py-1.5 rounded-lg bg-blue-500 text-white font-medium hover:bg-blue-600 disabled:opacity-40"
          >
            Run
          </button>
        )}
      </form>

      {running && (
        <div className="flex items-center gap-2 text-xs text-blue-400">
          <span className="animate-pulse">⚙ Running…</span>
          <span>Step {stepCount}</span>
          <div className="flex-1 bg-white/10 rounded-full h-1.5">
            <div
              className="bg-blue-400 h-1.5 rounded-full transition-all"
              style={{ width: `${Math.min(100, (stepCount / 20) * 100)}%` }}
            />
          </div>
        </div>
      )}

      {result && (
        <div
          className={`rounded-xl p-3 text-sm ${
            result.success
              ? "bg-emerald-500/20 border border-emerald-500/40"
              : "bg-red-500/20 border border-red-500/40"
          }`}
        >
          <div className="flex items-center gap-2 font-semibold mb-1">
            <span>{result.success ? "✅ Success" : "❌ Failed"}</span>
            <span className="opacity-60 font-normal text-xs">
              {result.steps_taken} steps
              {result.duration_seconds !== undefined && ` · ${result.duration_seconds.toFixed(1)}s`}
            </span>
          </div>
          <div className="opacity-80">{result.summary}</div>
        </div>
      )}

      <div className="flex-1 overflow-auto space-y-2">
        {stepEvents.map((event) => (
          <div key={`${event.task_id}-${event.step}`} className="rounded-lg bg-white/10 p-2 flex gap-2">
            {event.screenshot_b64 && (
              <img
                src={`data:image/png;base64,${event.screenshot_b64}`}
                alt={`step ${event.step}`}
                className="w-20 h-14 object-contain rounded bg-black/20 flex-shrink-0"
              />
            )}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono bg-white/10 px-1.5 rounded">{event.action}</span>
                <span className={`text-xs ${event.success ? "text-emerald-400" : "text-red-400"}`}>
                  {event.success ? "✓" : "✗"}
                </span>
              </div>
              <div className="text-xs opacity-70 mt-0.5 truncate">{event.reasoning}</div>
              {event.screen_description && (
                <div className="text-xs opacity-50 truncate">{event.screen_description}</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
