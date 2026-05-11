import { useState } from "react";
import { listLoadedModels } from "../api/models";
import { getSwarmStatus, startSwarm } from "../api/swarm";

export function TerminalApp() {
  const [command, setCommand] = useState("");
  const [lines, setLines] = useState<string[]>([
    "PradyOS Terminal v0.1",
    "Try: kryos run \"task\" | kryos status | kryos models list",
  ]);

  function append(line: string) {
    setLines((prev) => [...prev, line]);
  }

  async function execute(cmd: string) {
    append(`$ ${cmd}`);
    if (cmd.startsWith("kryos run")) {
      const match = /"(.+)"/.exec(cmd);
      const goal = match?.[1] ?? "Untitled task";
      const res = await startSwarm({ goal, max_agents: 5 });
      append(`Started swarm: ${res.swarm_id}`);
      return;
    }
    if (cmd === "kryos status") {
      const status = await getSwarmStatus();
      append(`Active swarms: ${status.swarms.length}`);
      return;
    }
    if (cmd === "kryos models list") {
      const models = await listLoadedModels();
      const list = models.loaded_models ?? [];
      append(`Loaded models: ${list.join(", ") || "none"}`);
      return;
    }
    append("Unknown command");
  }

  return (
    <div className="h-full flex flex-col bg-black text-green-300 font-mono text-xs rounded-b-2xl">
      <div className="p-3 flex-1 overflow-auto space-y-1">
        {lines.map((line, idx) => (
          <div key={`${line}-${idx}`}>{line}</div>
        ))}
      </div>
      <form
        className="border-t border-white/10 p-2"
        onSubmit={(e) => {
          e.preventDefault();
          const cmd = command.trim();
          if (!cmd) {
            return;
          }
          setCommand("");
          void execute(cmd);
        }}
      >
        <input
          className="w-full bg-transparent outline-none"
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          placeholder="Enter command..."
        />
      </form>
    </div>
  );
}
