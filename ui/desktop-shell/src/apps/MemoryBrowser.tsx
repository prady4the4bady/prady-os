import { useCallback, useEffect, useState } from "react";

const SWARM_BASE = (import.meta.env as Record<string, string>)
  .VITE_SWARM_URL ?? "http://localhost:8000";

interface MemoryEntry {
  id: string;
  agent_id: string;
  content: string;
  tags: string[];
  created_at: number;
  access_count: number;
}

interface MemoryStats {
  total_entries: number;
  db_size_mb: number;
  agents: string[];
}

export function MemoryBrowser() {
  const [stats, setStats] = useState<MemoryStats | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<MemoryEntry[]>([]);
  const [searching, setSearching] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [addContent, setAddContent] = useState("");
  const [addAgentId, setAddAgentId] = useState("ui-user");
  const [addTags, setAddTags] = useState("");
  const [adding, setAdding] = useState(false);

  const refreshStats = useCallback(async () => {
    try {
      const res = await fetch(`${SWARM_BASE}/memory/stats`);
      if (res.ok) setStats((await res.json()) as MemoryStats);
    } catch (error: unknown) {
      void error;
    }
  }, []);

  useEffect(() => {
    void refreshStats();
  }, [refreshStats]);

  const handleSearch = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!query.trim()) return;
      setSearching(true);
      try {
        const res = await fetch(`${SWARM_BASE}/memory/search`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ agent_id: "ui-user", query: query.trim(), top_k: 20 }),
        });
        if (res.ok) {
          const d = (await res.json()) as { results: MemoryEntry[] };
          setResults(d.results ?? []);
        }
      } catch (error: unknown) {
        void error;
      }
      setSearching(false);
    },
    [query]
  );

  const handleDelete = useCallback(
    async (id: string) => {
      await fetch(`${SWARM_BASE}/memory/${id}`, { method: "DELETE" }).catch(() => {});
      setResults((prev) => prev.filter((r) => r.id !== id));
      void refreshStats();
    },
    [refreshStats]
  );

  const handleAdd = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!addContent.trim()) return;
      setAdding(true);
      try {
        const tags = addTags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean);
        await fetch(`${SWARM_BASE}/memory/store`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ agent_id: addAgentId.trim(), content: addContent.trim(), tags }),
        });
        setAddContent("");
        setAddTags("");
        setShowAdd(false);
        void refreshStats();
      } catch (error: unknown) {
        void error;
      }
      setAdding(false);
    },
    [addContent, addAgentId, addTags, refreshStats]
  );

  return (
    <div className="h-full p-3 flex flex-col gap-3 text-sm overflow-auto">
      {/* Stats bar */}
      {stats && (
        <div className="flex items-center gap-4 text-xs bg-white/10 rounded-xl px-3 py-2">
          <span>
            <span className="font-semibold">{stats.total_entries}</span> entries
          </span>
          <span>
            <span className="font-semibold">{stats.db_size_mb.toFixed(2)}</span> MB
          </span>
          <span className="opacity-60">{stats.agents.length} agent(s)</span>
          <span className="opacity-60 truncate">{stats.agents.join(", ")}</span>
          <button
            className="ml-auto text-blue-400 hover:text-blue-300"
            onClick={() => setShowAdd((v) => !v)}
          >
            {showAdd ? "✕" : "+ Add"}
          </button>
        </div>
      )}

      {/* Add memory form */}
      {showAdd && (
        <form
          onSubmit={handleAdd}
          className="bg-white/10 rounded-xl p-3 flex flex-col gap-2"
        >
          <div className="font-medium text-xs mb-1">Add Memory</div>
          <input
            className="rounded-lg px-2 py-1 bg-white/20 text-xs focus:outline-none"
            placeholder="Agent ID"
            value={addAgentId}
            onChange={(e) => setAddAgentId(e.target.value)}
          />
          <textarea
            className="rounded-lg px-2 py-1 bg-white/20 text-xs focus:outline-none resize-none"
            rows={3}
            placeholder="Memory content…"
            value={addContent}
            onChange={(e) => setAddContent(e.target.value)}
          />
          <input
            className="rounded-lg px-2 py-1 bg-white/20 text-xs focus:outline-none"
            placeholder="Tags (comma-separated)"
            value={addTags}
            onChange={(e) => setAddTags(e.target.value)}
          />
          <button
            type="submit"
            disabled={adding || !addContent.trim()}
            className="self-end px-3 py-1 rounded-lg bg-blue-500 text-white text-xs hover:bg-blue-600 disabled:opacity-40"
          >
            {adding ? "Storing…" : "Store"}
          </button>
        </form>
      )}

      {/* Search */}
      <form onSubmit={handleSearch} className="flex gap-2">
        <input
          className="flex-1 rounded-lg px-3 py-1.5 bg-white/20 focus:outline-none focus:ring-2 focus:ring-blue-400"
          placeholder="Search memories…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button
          type="submit"
          disabled={searching || !query.trim()}
          className="px-3 py-1.5 rounded-lg bg-blue-500 text-white font-medium hover:bg-blue-600 disabled:opacity-40"
        >
          {searching ? "…" : "Search"}
        </button>
      </form>

      {/* Results */}
      <div className="flex-1 space-y-2">
        {results.map((entry) => (
          <div key={entry.id} className="rounded-xl bg-white/10 p-3">
            <div className="flex items-start justify-between gap-2">
              <p className="flex-1 text-xs leading-relaxed">{entry.content}</p>
              <button
                onClick={() => void handleDelete(entry.id)}
                className="text-red-400 hover:text-red-300 text-xs flex-shrink-0"
                title="Delete"
              >
                ✕
              </button>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs opacity-60">
              <span className="font-mono bg-white/10 px-1.5 rounded">{entry.agent_id}</span>
              {entry.tags.map((tag) => (
                <span key={tag} className="bg-blue-500/20 text-blue-300 px-1.5 rounded">
                  {tag}
                </span>
              ))}
              <span className="ml-auto">×{entry.access_count}</span>
              <span>{new Date(entry.created_at * 1000).toLocaleDateString()}</span>
            </div>
          </div>
        ))}
        {results.length === 0 && query && !searching && (
          <div className="text-center opacity-50 py-8">No results</div>
        )}
        {results.length === 0 && !query && (
          <div className="text-center opacity-40 py-8">Search to browse memories</div>
        )}
      </div>
    </div>
  );
}
