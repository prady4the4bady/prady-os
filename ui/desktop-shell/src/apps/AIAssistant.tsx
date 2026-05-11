import { useEffect, useMemo, useState } from "react";
import type { SwarmState } from "../types";

interface Props {
  swarms: SwarmState[];
}

export function AIAssistant({ swarms }: Readonly<Props>) {
  const [stream, setStream] = useState("");

  const latestReasoning = useMemo(() => {
    const latest = [...swarms]
      .sort((a, b) => a.started_at.localeCompare(b.started_at))
      .at(-1);
    const text = latest?.merged_result?.combined_reasoning;
    return typeof text === "string" ? text : "";
  }, [swarms]);

  useEffect(() => {
    if (!latestReasoning) {
      setStream("");
      return;
    }
    setStream("");
    let i = 0;
    const timer = globalThis.setInterval(() => {
      i += 5;
      setStream(latestReasoning.slice(0, i));
      if (i >= latestReasoning.length) {
        globalThis.clearInterval(timer);
      }
    }, 20);
    return () => globalThis.clearInterval(timer);
  }, [latestReasoning]);

  const activeAgents = swarms.flatMap((s) => s.agents.filter((a) => a.status !== "done"));

  return (
    <div className="h-full p-4 flex flex-col gap-4 text-sm">
      <h2 className="text-base font-semibold">Kryos AI Assistant</h2>
      <div className="grid grid-cols-1 gap-2 max-h-48 overflow-auto">
        {activeAgents.length === 0 ? (
          <div className="rounded-xl bg-white/40 dark:bg-black/20 p-3">No active agents.</div>
        ) : (
          activeAgents.map((agent) => (
            <div key={agent.agent_id} className="rounded-xl bg-white/50 dark:bg-black/20 p-3">
              <div className="font-medium">{agent.agent_id}</div>
              <div className="text-xs opacity-70">Model: {agent.model_id}</div>
              <div className="text-xs opacity-80">State: {agent.status}</div>
            </div>
          ))
        )}
      </div>

      <div className="rounded-xl bg-black/80 text-green-300 p-3 flex-1 overflow-auto font-mono text-xs">
        <div className="opacity-70 mb-2">Live token stream</div>
        <pre className="whitespace-pre-wrap">{stream || "Waiting for swarm output..."}</pre>
      </div>
    </div>
  );
}
