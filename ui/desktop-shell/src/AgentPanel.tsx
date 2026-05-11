import { useState, useEffect, useRef, useCallback } from "react";

const AGENT_RUNTIME_URL = "http://localhost:8100";

interface AgentHandle {
  agent_id: string;
  model_id: string;
  policy_id: string;
  pid: number | null;
  status: string;
  started_at: number;
  stopped_at: number | null;
  exit_code: number | null;
}

interface StreamToken {
  token?: string;
  done?: boolean;
  agent_id?: string;
}

function parseSseFrames(buffer: string): { frames: string[]; remainder: string } {
  const frames = buffer.split("\n\n");
  const remainder = frames.pop() ?? "";
  return { frames, remainder };
}

function appendFrameContent(frame: string, append: (value: string) => void) {
  const dataLine = frame
    .split("\n")
    .find((line) => line.startsWith("data:"));
  if (!dataLine) {
    return;
  }
  const jsonStr = dataLine.slice(5).trim();
  try {
    const parsed = JSON.parse(jsonStr) as StreamToken;
    if (!parsed.done && parsed.token) {
      append(parsed.token);
    }
  } catch {
    append(jsonStr);
  }
}

const AVAILABLE_MODELS = [
  { id: "phi3", label: "Phi-3 Mini" },
  { id: "mistral-7b", label: "Mistral 7B" },
  { id: "llama3-8b", label: "LLaMA 3 8B" },
  { id: "lumyn-agent", label: "Lumyn Agent" },
];

const AVAILABLE_POLICIES = [
  { id: "task-executor", label: "Task Executor" },
  { id: "agent-runtime", label: "Agent Runtime" },
];

export function AgentPanel() {
  const [open, setOpen] = useState(false);
  const [agents, setAgents] = useState<AgentHandle[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [response, setResponse] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [loading, setLoading] = useState(false);
  const [spawnModel, setSpawnModel] = useState(AVAILABLE_MODELS[0].id);
  const [spawnPolicy, setSpawnPolicy] = useState(AVAILABLE_POLICIES[0].id);
  const [error, setError] = useState<string | null>(null);

  const responseRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fetchAgents = useCallback(async () => {
    try {
      const res = await fetch(`${AGENT_RUNTIME_URL}/agents/`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as AgentHandle[];
      setAgents(data);
    } catch (err) {
      setError(`Failed to load agents: ${String(err)}`);
    }
  }, []);

  useEffect(() => {
    if (open) {
      void fetchAgents();
    }
  }, [open, fetchAgents]);

  // Auto-scroll response
  useEffect(() => {
    if (responseRef.current) {
      responseRef.current.scrollTop = responseRef.current.scrollHeight;
    }
  }, [response]);

  const handleSpawn = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${AGENT_RUNTIME_URL}/agents/spawn`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_id: spawnModel, policy_id: spawnPolicy }),
      });
      if (!res.ok) {
        const err = (await res.json()) as { detail?: string };
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      const agent = (await res.json()) as AgentHandle;
      setAgents((prev) => [...prev, agent]);
      setSelectedAgentId(agent.agent_id);
    } catch (err) {
      setError(`Spawn failed: ${String(err)}`);
    } finally {
      setLoading(false);
    }
  };

  const handleKill = async (agentId: string) => {
    setError(null);
    try {
      const res = await fetch(`${AGENT_RUNTIME_URL}/agents/${agentId}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const updated = (await res.json()) as AgentHandle;
      setAgents((prev) =>
        prev.map((a) => (a.agent_id === agentId ? updated : a))
      );
      if (selectedAgentId === agentId) {
        setSelectedAgentId(null);
        setResponse("");
      }
    } catch (err) {
      setError(`Kill failed: ${String(err)}`);
    }
  };

  const handlePrompt = async () => {
    if (!selectedAgentId || !prompt.trim()) return;

    setResponse("");
    setStreaming(true);
    setError(null);

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      const res = await fetch(
        `${AGENT_RUNTIME_URL}/agents/${selectedAgentId}/prompt`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: prompt }),
          signal: ctrl.signal,
        }
      );
      if (!res.ok) {
        const err = (await res.json()) as { detail?: string };
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";

      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        const parsedFrames = parseSseFrames(buffer + decoder.decode(value, { stream: true }));
        buffer = parsedFrames.remainder;
        for (const frame of parsedFrames.frames) {
          appendFrameContent(frame, (token) => {
            setResponse((prev) => prev + token);
          });
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setError(`Prompt error: ${String(err)}`);
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  };

  const handleStopStream = () => {
    abortRef.current?.abort();
  };

  const selectedAgent = agents.find((a) => a.agent_id === selectedAgentId);

  return (
    <>
      {/* Toggle button – fixed bottom-right */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="fixed bottom-4 right-4 z-50 rounded-full w-12 h-12 flex items-center justify-center bg-indigo-600 hover:bg-indigo-500 text-white shadow-xl transition-all"
        aria-label="Toggle Agent Panel"
        title="Agent Runtime"
      >
        <AgentIcon />
      </button>

      {/* Drawer */}
      {open && (
        <div className="fixed bottom-20 right-4 z-50 w-96 max-h-[80vh] flex flex-col glass rounded-2xl shadow-2xl overflow-hidden text-sm">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
            <span className="font-semibold text-base">Agent Runtime</span>
            <button
              onClick={() => setOpen(false)}
              className="opacity-60 hover:opacity-100 transition-opacity"
              aria-label="Close Agent Panel"
            >
              ✕
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-3">
            {/* Error banner */}
            {error && (
              <div className="rounded-lg bg-red-500/20 border border-red-400/30 px-3 py-2 text-red-300 text-xs">
                {error}
                <button
                  className="ml-2 underline opacity-70 hover:opacity-100"
                  onClick={() => setError(null)}
                >
                  dismiss
                </button>
              </div>
            )}

            {/* Spawn form */}
            <section className="rounded-xl bg-white/5 p-3 space-y-2">
              <div className="font-medium opacity-70 text-xs uppercase tracking-wide">
                Spawn Agent
              </div>
              <div className="flex gap-2">
                <select
                  value={spawnModel}
                  onChange={(e) => setSpawnModel(e.target.value)}
                  className="flex-1 rounded-lg bg-black/30 border border-white/10 px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-400"
                  aria-label="Model"
                >
                  {AVAILABLE_MODELS.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
                <select
                  value={spawnPolicy}
                  onChange={(e) => setSpawnPolicy(e.target.value)}
                  className="flex-1 rounded-lg bg-black/30 border border-white/10 px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-400"
                  aria-label="Policy"
                >
                  {AVAILABLE_POLICIES.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
                <button
                  onClick={() => void handleSpawn()}
                  disabled={loading}
                  className="rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 px-3 py-1 text-xs font-medium transition-colors"
                >
                  {loading ? "…" : "Spawn"}
                </button>
              </div>
            </section>

            {/* Agent list */}
            {agents.length > 0 && (
              <section className="space-y-1">
                <div className="font-medium opacity-70 text-xs uppercase tracking-wide px-1">
                  Agents ({agents.length})
                </div>
                {agents.map((agent) => (
                  <button
                    type="button"
                    key={agent.agent_id}
                    onClick={() => setSelectedAgentId(agent.agent_id)}
                    disabled={agent.status !== "running"}
                    className={[
                      "flex items-center justify-between rounded-xl p-2 cursor-pointer transition-colors",
                      selectedAgentId === agent.agent_id
                        ? "bg-indigo-600/40 ring-1 ring-indigo-400/50"
                        : "bg-white/5 hover:bg-white/10",
                      agent.status === "running" ? "" : "opacity-50 cursor-default",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                  >
                    <div className="flex flex-col min-w-0">
                      <span className="font-mono text-xs truncate">
                        {agent.agent_id.slice(0, 12)}…
                      </span>
                      <span className="opacity-60 text-xs">
                        {agent.model_id} · {agent.policy_id}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <StatusBadge status={agent.status} />
                      {agent.status === "running" && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleKill(agent.agent_id);
                          }}
                          className="rounded-md bg-red-600/60 hover:bg-red-500 px-2 py-0.5 text-xs transition-colors"
                          aria-label={`Kill agent ${agent.agent_id}`}
                        >
                          Kill
                        </button>
                      )}
                    </div>
                  </button>
                ))}
              </section>
            )}

            {/* Prompt area */}
            {selectedAgent?.status === "running" && (
              <section className="rounded-xl bg-white/5 p-3 space-y-2">
                <div className="font-medium opacity-70 text-xs uppercase tracking-wide">
                  Prompt →{" "}
                  <span className="text-indigo-300">
                    {selectedAgent.agent_id.slice(0, 12)}
                  </span>
                </div>
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  rows={3}
                  placeholder="Enter your prompt…"
                  className="w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-xs resize-none focus:outline-none focus:ring-1 focus:ring-indigo-400"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                      void handlePrompt();
                    }
                  }}
                />
                <div className="flex gap-2">
                  <button
                    onClick={() => void handlePrompt()}
                    disabled={streaming || !prompt.trim()}
                    className="flex-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 py-1.5 text-xs font-medium transition-colors"
                  >
                    {streaming ? "Streaming…" : "Send  ⌘↩"}
                  </button>
                  {streaming && (
                    <button
                      onClick={handleStopStream}
                      className="rounded-lg bg-orange-600/70 hover:bg-orange-500 px-3 py-1.5 text-xs transition-colors"
                    >
                      Stop
                    </button>
                  )}
                </div>

                {response && (
                  <div
                    ref={responseRef}
                    className="rounded-lg bg-black/30 border border-white/10 p-2 max-h-40 overflow-y-auto font-mono text-xs whitespace-pre-wrap leading-relaxed"
                  >
                    {response}
                    {streaming && (
                      <span className="inline-block w-1.5 h-3 ml-0.5 bg-indigo-400 animate-pulse" />
                    )}
                  </div>
                )}
              </section>
            )}

            {agents.length === 0 && (
              <p className="text-center opacity-50 py-4 text-xs">
                No agents running. Spawn one above.
              </p>
            )}
          </div>

          {/* Footer */}
          <div className="border-t border-white/10 px-4 py-2 flex items-center justify-between">
            <button
              onClick={() => void fetchAgents()}
              className="text-xs opacity-50 hover:opacity-80 transition-opacity"
            >
              ↺ Refresh
            </button>
            <span className="text-xs opacity-30">:8100</span>
          </div>
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Small sub-components
// ---------------------------------------------------------------------------

function StatusBadge({ status }: Readonly<{ status: string }>) {
  const colours: Record<string, string> = {
    running: "bg-green-500/80 text-green-100",
    stopped: "bg-gray-500/60 text-gray-200",
    killed: "bg-red-500/60 text-red-100",
    error: "bg-orange-500/60 text-orange-100",
  };
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${colours[status] ?? "bg-gray-500/50"}`}
    >
      {status}
    </span>
  );
}

function AgentIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      className="w-6 h-6"
    >
      <circle cx="12" cy="8" r="4" />
      <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" />
      <path d="M17 4l2-2M7 4L5 2" />
    </svg>
  );
}
