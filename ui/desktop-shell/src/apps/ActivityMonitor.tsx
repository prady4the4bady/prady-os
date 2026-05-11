import type { SwarmState } from "../types";

interface Props {
  swarms: SwarmState[];
  nemoEnabled: boolean;
}

export function ActivityMonitor({ swarms, nemoEnabled }: Readonly<Props>) {
  const activeAgents = swarms.reduce(
    (sum, swarm) => sum + swarm.agents.filter((a) => a.status !== "done" && a.status !== "failed").length,
    0
  );
  const tasksCompleted = swarms.reduce((sum, swarm) => {
    const merged = swarm.merged_result as { successful?: number } | undefined;
    return sum + (merged?.successful ?? 0);
  }, 0);

  return (
    <div className="h-full p-4 space-y-3 text-sm">
      <h2 className="text-base font-semibold">Activity Monitor</h2>
      <div className="grid grid-cols-2 gap-3">
        <Metric label="Active agents" value={String(activeAgents)} />
        <Metric label="Tasks completed" value={String(tasksCompleted)} />
        <Metric label="Model gateway" value="Healthy" />
        <Metric label="Vyrex" value={nemoEnabled ? "Enabled" : "Disabled"} />
      </div>

      <div className="rounded-xl bg-white/50 dark:bg-black/20 p-3 h-[calc(100%-160px)] overflow-auto">
        <div className="font-medium mb-2">Swarm timeline</div>
        {swarms.length === 0 ? (
          <div className="opacity-70">No swarm activity yet.</div>
        ) : (
          <ul className="space-y-2">
            {swarms.map((swarm) => (
              <li key={swarm.swarm_id} className="rounded-lg bg-white/60 dark:bg-black/20 p-2">
                <div className="font-medium">{swarm.goal}</div>
                <div className="text-xs opacity-70">{swarm.swarm_id}</div>
                <div className="text-xs">Status: {swarm.status} | Agents: {swarm.agent_count}</div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Metric({ label, value }: Readonly<{ label: string; value: string }>) {
  return (
    <div className="rounded-xl bg-white/50 dark:bg-black/20 p-3">
      <div className="text-xs opacity-70">{label}</div>
      <div className="text-lg font-semibold">{value}</div>
    </div>
  );
}
