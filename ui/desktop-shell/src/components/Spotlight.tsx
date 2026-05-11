import { FormEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { startSwarm } from "../api/swarm";
import type { SwarmState } from "../types";
import { useClickOutside } from "../hooks/useClickOutside";

const SWARM_BASE =
  (import.meta.env as Record<string, string>)
    .VITE_SWARM_URL ?? "http://localhost:8000";

interface Props {
  open: boolean;
  onClose: () => void;
  onSwarmStarted: (id: string) => void;
  swarms: SwarmState[];
}

type Category = "Apps" | "AI Tasks" | "Web Search";
const CATEGORIES: Category[] = ["Apps", "AI Tasks", "Web Search"];

export function Spotlight({ open, onClose, onSwarmStarted, swarms }: Readonly<Props>) {
  const [query, setQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState<Category>("Apps");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string>("");
  const containerRef = useRef<HTMLDivElement>(null);
  useClickOutside(containerRef, onClose, open);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape" && open) onClose();
    }
    globalThis.addEventListener("keydown", onKey);
    return () => globalThis.removeEventListener("keydown", onKey);
  }, [onClose, open]);

  useEffect(() => {
    if (!open) { setQuery(""); setResult(""); setLoading(false); }
  }, [open]);

  async function submitAITask(goal: string) {
    setLoading(true);
    setResult("");
    try {
      const resp = await fetch(`${SWARM_BASE}/task/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal }),
      });
      if (resp.ok) {
        const data = (await resp.json()) as { result?: string; task_id?: string };
        setResult(data.result ?? `Task queued: ${data.task_id ?? "unknown"}`);
      } else {
        const fallback = await startSwarm({ goal, max_agents: 3 });
        onSwarmStarted(fallback.swarm_id);
        setResult(`Swarm launched: ${fallback.swarm_id}`);
      }
    } catch {
      setResult("Failed to submit task.");
    } finally {
      setLoading(false);
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!query.trim()) return;
    if (activeCategory === "AI Tasks") {
      await submitAITask(query.trim());
    } else if (activeCategory === "Web Search") {
      setResult(`Searching: ${query}`);
    }
  }

  const filteredSwarms = swarms.filter((s) =>
    s.goal.toLowerCase().includes(query.toLowerCase())
  );

  function getIdleMessage(): string {
    if (activeCategory === "AI Tasks") {
      return "Type a goal and press Enter to run an AI task";
    }
    if (activeCategory === "Web Search") {
      return "Type and press Enter to search";
    }
    return "Cmd+Space anytime • Type to search";
  }

  function renderAppsResults(): ReactNode {
    if (!(activeCategory === "Apps" && query)) {
      return null;
    }

    if (filteredSwarms.length === 0) {
      return <div className="text-xs opacity-50 text-center py-4">No matches for "{query}"</div>;
    }

    return filteredSwarms.map((s) => (
      <div key={s.swarm_id} className="rounded-lg px-3 py-2 hover:bg-white/30 cursor-pointer text-sm">
        <span className="font-medium">{s.goal}</span>
        <span className="ml-2 opacity-60 text-xs">{s.status}</span>
      </div>
    ));
  }

  function renderBody(): ReactNode {
    if (loading) {
      return <div className="text-sm opacity-70 py-4 text-center">Running…</div>;
    }

    if (result) {
      return <div className="rounded-xl bg-white/60 dark:bg-black/25 p-3 text-sm whitespace-pre-wrap">{result}</div>;
    }

    const appsResults = renderAppsResults();
    if (appsResults) {
      return appsResults;
    }

    return <div className="text-xs opacity-50 text-center py-4">{getIdleMessage()}</div>;
  }

  return (
    <AnimatePresence>
      {open ? (
        <div className="absolute inset-0 bg-black/30 backdrop-blur-sm flex items-start justify-center pt-24 z-[70]">
          <motion.div
            ref={containerRef}
            className="glass w-full rounded-2xl overflow-hidden shadow-2xl"
            style={{ maxWidth: 680 }}
            initial={{ opacity: 0, scale: 0.98, filter: "blur(4px)" }}
            animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0, scale: 0.98, filter: "blur(4px)" }}
            transition={{ duration: 0.18, ease: "easeOut" }}
          >
            <form onSubmit={onSubmit}>
              <div className="flex items-center px-4 py-3 border-b border-white/20">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="opacity-50 mr-3 shrink-0" aria-hidden="true">
                  <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
                </svg>
                <input
                  autoFocus
                  placeholder="Search or ask anything…"
                  className="flex-1 bg-transparent outline-none text-base placeholder-current/50"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
                {query ? (
                  <button type="button" className="opacity-50 hover:opacity-100 text-xs px-2 py-1 rounded" onClick={() => setQuery("")}>esc</button>
                ) : null}
              </div>
            </form>

            <div className="flex gap-1 px-4 py-2 border-b border-white/10">
              {CATEGORIES.map((cat) => (
                <button
                  key={cat}
                  className={`text-xs px-3 py-1 rounded-full transition-colors ${activeCategory === cat ? "bg-blue-500 text-white" : "hover:bg-white/20"}`}
                  onClick={() => setActiveCategory(cat)}
                >
                  {cat}
                </button>
              ))}
            </div>

            <div className="min-h-32 max-h-80 overflow-auto p-3 space-y-1">{renderBody()}</div>
          </motion.div>
        </div>
      ) : null}
    </AnimatePresence>
  );
}
