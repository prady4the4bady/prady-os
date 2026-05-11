import { useCallback, useEffect, useMemo, useState } from "react";
import { Brain, Check, Copy, Save, Trash2, UserPlus, Users, X } from "lucide-react";

type MemoryPolicy = "aggressive" | "balanced" | "minimal";

type PersonaRecord = {
  id: string;
  name: string;
  avatar_color: string;
  system_prompt: string;
  preferred_model_id: string;
  memory_policy: MemoryPolicy;
  tags: string[];
  compressed_summary: string | null;
  archived: boolean;
  created_at: string;
  updated_at: string;
  last_activated_at: string | null;
  activation_count: number;
  is_active: boolean;
};

type PersonaListResponse = {
  personas: PersonaRecord[];
  total: number;
};

type TopicCount = { topic: string; count: number };

type MemorySummaryResponse = {
  total_memories: number;
  oldest_memory: string | null;
  newest_memory: string | null;
  top_topics: TopicCount[];
  compression_ratio: number;
};

type FormState = {
  name: string;
  avatar_color: string;
  system_prompt: string;
  preferred_model_id: string;
  memory_policy: MemoryPolicy;
  tags_csv: string;
};

const FONT = "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif";

const emptyForm: FormState = {
  name: "",
  avatar_color: "#0A84FF",
  system_prompt: "",
  preferred_model_id: "",
  memory_policy: "balanced",
  tags_csv: "",
};

function parseTags(tagsCsv: string): string[] {
  return tagsCsv
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean)
    .slice(0, 20);
}

function prettyDate(iso: string | null): string {
  if (!iso) return "-";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

async function jsonOrThrow<T>(resp: Response): Promise<T> {
  const body = await resp.text();
  if (!resp.ok) {
    throw new Error(body || `HTTP ${resp.status}`);
  }
  return (body ? JSON.parse(body) : {}) as T;
}

interface PersonaManagerProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  layerZIndex?: number;
}

function replacePersona(list: PersonaRecord[], updated: PersonaRecord): PersonaRecord[] {
  return list.map((persona) => (persona.id === updated.id ? updated : persona));
}

export default function PersonaManager({ open, onOpenChange, layerZIndex }: Readonly<PersonaManagerProps>): JSX.Element {
  const [internalOpen, setInternalOpen] = useState(false);
  const [tab, setTab] = useState<"personas" | "memory">("personas");
  const [personas, setPersonas] = useState<PersonaRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [summary, setSummary] = useState<MemorySummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const isControlled = open !== undefined;
  const isOpen = isControlled ? open : internalOpen;
  const baseZIndex = layerZIndex ?? 9000;

  const setOpenState = (next: boolean): void => {
    if (!isControlled) {
      setInternalOpen(next);
    }
    onOpenChange?.(next);
  };

  const activePersona = useMemo(() => personas.find((p) => p.is_active) ?? null, [personas]);
  const selectedPersona = useMemo(
    () => personas.find((p) => p.id === (selectedId ?? activePersona?.id)) ?? null,
    [personas, selectedId, activePersona?.id]
  );

  const refresh = useCallback((): void => {
    void (async () => {
      setLoading(true);
      try {
        const resp = await fetch("/api/personas");
        const data = await jsonOrThrow<PersonaListResponse>(resp);
        const next = (data.personas ?? []).filter((p) => !p.archived);
        setPersonas(next);
        setSelectedId((prev) => prev ?? next[0]?.id ?? null);
      } catch (e) {
        setError(`Failed to load personas: ${String(e)}`);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const refreshSummary = useCallback((personaId: string): void => {
    void (async () => {
      try {
        const resp = await fetch(`/api/personas/${encodeURIComponent(personaId)}/memory-summary`);
        const data = await jsonOrThrow<MemorySummaryResponse>(resp);
        setSummary(data);
      } catch (e) {
        setError(`Failed to load memory summary: ${String(e)}`);
      }
    })();
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    refresh();
    const timer = globalThis.setInterval(refresh, 120_000);
    return () => globalThis.clearInterval(timer);
  }, [isOpen, refresh]);

  useEffect(() => {
    if (isOpen && tab === "memory" && selectedPersona) {
      refreshSummary(selectedPersona.id);
    }
  }, [isOpen, tab, selectedPersona, selectedPersona?.id, refreshSummary]);

  const beginCreate = (): void => {
    setEditingId("");
    setForm(emptyForm);
    setError(null);
  };

  const beginEdit = (p: PersonaRecord): void => {
    setEditingId(p.id);
    setForm({
      name: p.name,
      avatar_color: p.avatar_color,
      system_prompt: p.system_prompt,
      preferred_model_id: p.preferred_model_id,
      memory_policy: p.memory_policy,
      tags_csv: p.tags.join(", "),
    });
    setError(null);
  };

  const submitForm = (): void => {
    const payload = {
      name: form.name.trim(),
      avatar_color: form.avatar_color,
      system_prompt: form.system_prompt.trim(),
      preferred_model_id: form.preferred_model_id.trim(),
      memory_policy: form.memory_policy,
      tags: parseTags(form.tags_csv),
    };

    if (!payload.name || !payload.system_prompt || !payload.preferred_model_id) {
      setError("Name, system prompt, and preferred model are required.");
      return;
    }

    setSaving(true);
    setError(null);

    void (async () => {
      try {
        if (!editingId) {
          const resp = await fetch("/api/personas", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          const created = await jsonOrThrow<PersonaRecord>(resp);
          setPersonas((prev) => [created, ...prev]);
          setSelectedId(created.id);
        } else {
          const resp = await fetch(`/api/personas/${encodeURIComponent(editingId)}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          const updated = await jsonOrThrow<PersonaRecord>(resp);
          setPersonas((prev) => replacePersona(prev, updated));
        }
        setEditingId(null);
        setForm(emptyForm);
      } catch (e) {
        setError(`Save failed: ${String(e)}`);
      } finally {
        setSaving(false);
      }
    })();
  };

  const activatePersona = (personaId: string): void => {
    const snapshot = personas;
    setPersonas((prev) => prev.map((p) => ({ ...p, is_active: p.id === personaId })));
    setError(null);

    void (async () => {
      try {
        const resp = await fetch(`/api/personas/${encodeURIComponent(personaId)}/activate`, { method: "POST" });
        await jsonOrThrow<{ ok: boolean }>(resp);
      } catch (e) {
        setPersonas(snapshot);
        setError(`Activate failed: ${String(e)}`);
      }
    })();
  };

  const clonePersona = (personaId: string): void => {
    setError(null);
    void (async () => {
      try {
        const resp = await fetch(`/api/personas/${encodeURIComponent(personaId)}/clone`, { method: "POST" });
        const created = await jsonOrThrow<PersonaRecord>(resp);
        setPersonas((prev) => [created, ...prev]);
      } catch (e) {
        setError(`Clone failed: ${String(e)}`);
      }
    })();
  };

  const archivePersona = (personaId: string): void => {
    const snapshot = personas;
    setPersonas((prev) => prev.filter((p) => p.id !== personaId));
    setError(null);

    void (async () => {
      try {
        const resp = await fetch(`/api/personas/${encodeURIComponent(personaId)}`, { method: "DELETE" });
        await jsonOrThrow<{ ok: boolean }>(resp);
      } catch (e) {
        setPersonas(snapshot);
        setError(`Delete failed: ${String(e)}`);
      }
    })();
  };

  const compressMemory = (): void => {
    if (!selectedPersona) return;
    setError(null);
    void (async () => {
      try {
        const resp = await fetch(`/api/personas/${encodeURIComponent(selectedPersona.id)}/compress-memory`, {
          method: "POST",
        });
        await jsonOrThrow<{ accepted: boolean }>(resp);
        refreshSummary(selectedPersona.id);
      } catch (e) {
        setError(`Compression failed: ${String(e)}`);
      }
    })();
  };

  return (
    <>
      <button
        type="button"
        aria-label="Persona Manager"
        onClick={() => setOpenState(!isOpen)}
        style={{
          position: "fixed",
          top: 12,
          right: 184,
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
          fontFamily: FONT,
        }}
      >
        <Users size={14} />
        <span>Personas</span>
      </button>

      {isOpen && (
        <>
          <button
            type="button"
            aria-label="Close persona manager"
            onClick={() => setOpenState(false)}
            style={{
              position: "fixed",
              inset: 0,
              background: "transparent",
              border: "none",
              zIndex: baseZIndex,
            }}
          />
          <div
            style={{
              position: "fixed",
              top: 0,
              right: 0,
              width: 520,
              maxWidth: "100vw",
              height: "100vh",
              background: "rgba(18,18,20,0.97)",
              backdropFilter: "blur(20px)",
              WebkitBackdropFilter: "blur(20px)",
              borderLeft: "1px solid rgba(58,58,60,0.8)",
              zIndex: baseZIndex + 1,
              display: "flex",
              flexDirection: "column",
              color: "#F2F2F7",
              fontFamily: FONT,
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "14px 16px",
                borderBottom: "1px solid rgba(58,58,60,0.6)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Users size={16} color="#0A84FF" />
                <span style={{ fontSize: 15, fontWeight: 600 }}>Persona Manager</span>
              </div>
              <button
                type="button"
                onClick={() => setOpenState(false)}
                style={{ background: "none", border: "none", color: "#8E8E93", cursor: "pointer" }}
              >
                <X size={16} />
              </button>
            </div>

            <div style={{ display: "flex", gap: 8, padding: "10px 16px", borderBottom: "1px solid rgba(58,58,60,0.5)" }}>
              <button
                type="button"
                onClick={() => setTab("personas")}
                style={{
                  border: "1px solid rgba(58,58,60,0.7)",
                  borderRadius: 8,
                  background: tab === "personas" ? "rgba(10,132,255,0.2)" : "rgba(44,44,46,0.8)",
                  color: "#F2F2F7",
                  padding: "6px 10px",
                  cursor: "pointer",
                  fontSize: 12,
                }}
              >
                Personas
              </button>
              <button
                type="button"
                onClick={() => setTab("memory")}
                style={{
                  border: "1px solid rgba(58,58,60,0.7)",
                  borderRadius: 8,
                  background: tab === "memory" ? "rgba(48,209,88,0.2)" : "rgba(44,44,46,0.8)",
                  color: "#F2F2F7",
                  padding: "6px 10px",
                  cursor: "pointer",
                  fontSize: 12,
                }}
              >
                Memory
              </button>
              <div style={{ marginLeft: "auto" }}>
                <button
                  type="button"
                  onClick={beginCreate}
                  style={{
                    border: "1px solid rgba(10,132,255,0.7)",
                    borderRadius: 8,
                    background: "rgba(10,132,255,0.18)",
                    color: "#F2F2F7",
                    padding: "6px 10px",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    fontSize: 12,
                  }}
                >
                  <UserPlus size={13} /> New
                </button>
              </div>
            </div>

            {error && (
              <div
                style={{
                  margin: "10px 16px",
                  border: "1px solid rgba(255,69,58,0.5)",
                  borderRadius: 8,
                  background: "rgba(255,69,58,0.12)",
                  color: "#FF9F0A",
                  padding: "8px 10px",
                  fontSize: 12,
                }}
              >
                {error}
              </div>
            )}

            {activePersona && (
              <div
                style={{
                  margin: "10px 16px",
                  border: "1px solid rgba(48,209,88,0.5)",
                  borderRadius: 10,
                  background: "rgba(48,209,88,0.12)",
                  padding: "10px 12px",
                }}
              >
                <div style={{ fontSize: 12, color: "#9CE7B5" }}>Active Persona</div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
                  <span style={{ width: 10, height: 10, borderRadius: "50%", background: activePersona.avatar_color }} />
                  <strong style={{ fontSize: 13 }}>{activePersona.name}</strong>
                  <span style={{ marginLeft: "auto", fontSize: 11, color: "#8E8E93" }}>
                    {activePersona.preferred_model_id}
                  </span>
                </div>
              </div>
            )}

            {tab === "personas" && (
              <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr", overflowY: "auto", padding: "0 16px 12px" }}>
                {loading && <div style={{ color: "#8E8E93", fontSize: 12 }}>Loading personas...</div>}
                {!loading &&
                  personas.map((p) => (
                    <div
                      key={p.id}
                      style={{
                        border: "1px solid rgba(58,58,60,0.6)",
                        borderRadius: 10,
                        marginBottom: 10,
                        background: selectedPersona?.id === p.id ? "rgba(10,132,255,0.09)" : "rgba(44,44,46,0.5)",
                        padding: 10,
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ width: 10, height: 10, borderRadius: "50%", background: p.avatar_color }} />
                        <button
                          type="button"
                          onClick={() => setSelectedId(p.id)}
                          style={{
                            background: "none",
                            border: "none",
                            color: "#F2F2F7",
                            cursor: "pointer",
                            fontSize: 13,
                            fontWeight: 600,
                            padding: 0,
                          }}
                        >
                          {p.name}
                        </button>
                        {p.is_active && <Check size={14} color="#30D158" />}
                        <span style={{ marginLeft: "auto", color: "#8E8E93", fontSize: 11 }}>{p.memory_policy}</span>
                      </div>
                      <div style={{ marginTop: 6, fontSize: 12, color: "#8E8E93" }}>
                        {p.preferred_model_id} · activations {p.activation_count}
                      </div>
                      <div style={{ marginTop: 4, fontSize: 11, color: "#636366" }}>Updated {prettyDate(p.updated_at)}</div>
                      <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
                        <ActionButton label="Activate" onClick={() => activatePersona(p.id)} />
                        <ActionButton label="Edit" onClick={() => beginEdit(p)} />
                        <ActionButton label="Clone" icon={<Copy size={12} />} onClick={() => clonePersona(p.id)} />
                        <ActionButton label="Archive" icon={<Trash2 size={12} />} danger onClick={() => archivePersona(p.id)} />
                      </div>
                    </div>
                  ))}
              </div>
            )}

            {tab === "memory" && (
              <div style={{ flex: 1, overflowY: "auto", padding: "0 16px 16px" }}>
                {selectedPersona ? (
                  <>
                    <div style={{ border: "1px solid rgba(58,58,60,0.6)", borderRadius: 10, padding: 12, marginBottom: 12 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                        <Brain size={14} color="#30D158" />
                        <strong style={{ fontSize: 13 }}>{selectedPersona.name} memory profile</strong>
                      </div>
                      <div style={{ fontSize: 12, color: "#8E8E93", lineHeight: 1.4 }}>
                        Last activated: {prettyDate(selectedPersona.last_activated_at)}
                      </div>
                      <div style={{ marginTop: 10 }}>
                        <ActionButton label="Compress Memory" onClick={compressMemory} />
                      </div>
                    </div>

                    {summary ? (
                      <div style={{ border: "1px solid rgba(58,58,60,0.6)", borderRadius: 10, padding: 12 }}>
                        <div style={{ fontSize: 12, color: "#8E8E93" }}>Total memories: {summary.total_memories}</div>
                        <div style={{ fontSize: 12, color: "#8E8E93" }}>Oldest: {prettyDate(summary.oldest_memory)}</div>
                        <div style={{ fontSize: 12, color: "#8E8E93" }}>Newest: {prettyDate(summary.newest_memory)}</div>
                        <div style={{ fontSize: 12, color: "#8E8E93" }}>
                          Compression ratio: {(summary.compression_ratio * 100).toFixed(1)}%
                        </div>
                        <div style={{ marginTop: 8, fontSize: 12, color: "#F2F2F7" }}>Top topics</div>
                        {summary.top_topics.length === 0 && (
                          <div style={{ color: "#636366", fontSize: 12, marginTop: 4 }}>No topic data yet.</div>
                        )}
                        {summary.top_topics.map((t) => (
                          <div key={t.topic} style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 12 }}>
                            <span style={{ color: "#F2F2F7" }}>{t.topic}</span>
                            <span style={{ color: "#8E8E93" }}>{t.count}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div style={{ color: "#8E8E93", fontSize: 12 }}>Summary unavailable.</div>
                    )}
                  </>
                ) : (
                  <div style={{ color: "#8E8E93", fontSize: 12 }}>Select a persona to inspect memory profile.</div>
                )}
              </div>
            )}

            {editingId !== null && (
              <div style={{ borderTop: "1px solid rgba(58,58,60,0.6)", padding: 12, background: "rgba(28,28,30,0.95)" }}>
                <div style={{ fontSize: 12, color: "#8E8E93", marginBottom: 8 }}>
                  {editingId ? "Edit persona" : "Create persona"}
                </div>
                <FormInput label="Name" value={form.name} onChange={(v) => setForm((p) => ({ ...p, name: v }))} />
                <FormInput
                  label="Avatar Color"
                  value={form.avatar_color}
                  onChange={(v) => setForm((p) => ({ ...p, avatar_color: v }))}
                />
                <FormInput
                  label="Preferred Model"
                  value={form.preferred_model_id}
                  onChange={(v) => setForm((p) => ({ ...p, preferred_model_id: v }))}
                />
                <FormInput
                  label="Tags (csv)"
                  value={form.tags_csv}
                  onChange={(v) => setForm((p) => ({ ...p, tags_csv: v }))}
                />
                <label htmlFor="persona-memory-policy" style={{ display: "block", fontSize: 11, color: "#8E8E93", marginTop: 8 }}>Memory Policy</label>
                <select
                  id="persona-memory-policy"
                  value={form.memory_policy}
                  onChange={(e) => setForm((p) => ({ ...p, memory_policy: e.target.value as MemoryPolicy }))}
                  style={{
                    width: "100%",
                    marginTop: 4,
                    borderRadius: 8,
                    border: "1px solid rgba(58,58,60,0.7)",
                    background: "rgba(44,44,46,0.9)",
                    color: "#F2F2F7",
                    padding: "6px 8px",
                    fontSize: 12,
                  }}
                >
                  <option value="balanced">balanced</option>
                  <option value="aggressive">aggressive</option>
                  <option value="minimal">minimal</option>
                </select>
                <label htmlFor="persona-system-prompt" style={{ display: "block", fontSize: 11, color: "#8E8E93", marginTop: 8 }}>System Prompt</label>
                <textarea
                  id="persona-system-prompt"
                  value={form.system_prompt}
                  onChange={(e) => setForm((p) => ({ ...p, system_prompt: e.target.value }))}
                  rows={4}
                  style={{
                    width: "100%",
                    marginTop: 4,
                    borderRadius: 8,
                    border: "1px solid rgba(58,58,60,0.7)",
                    background: "rgba(44,44,46,0.9)",
                    color: "#F2F2F7",
                    padding: "8px 10px",
                    fontSize: 12,
                    resize: "vertical",
                  }}
                />
                <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                  <button
                    type="button"
                    onClick={submitForm}
                    disabled={saving}
                    style={{
                      border: "1px solid rgba(48,209,88,0.7)",
                      borderRadius: 8,
                      background: "rgba(48,209,88,0.18)",
                      color: "#F2F2F7",
                      padding: "6px 10px",
                      fontSize: 12,
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                    }}
                  >
                    <Save size={12} /> {saving ? "Saving..." : "Save"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditingId(null)}
                    style={{
                      border: "1px solid rgba(58,58,60,0.7)",
                      borderRadius: 8,
                      background: "rgba(44,44,46,0.8)",
                      color: "#F2F2F7",
                      padding: "6px 10px",
                      fontSize: 12,
                      cursor: "pointer",
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </>
  );
}

function ActionButton({
  label,
  onClick,
  icon,
  danger,
}: Readonly<{
  label: string;
  onClick: () => void;
  icon?: JSX.Element;
  danger?: boolean;
}>): JSX.Element {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        border: `1px solid ${danger ? "rgba(255,69,58,0.6)" : "rgba(58,58,60,0.7)"}`,
        borderRadius: 8,
        background: danger ? "rgba(255,69,58,0.12)" : "rgba(44,44,46,0.85)",
        color: "#F2F2F7",
        padding: "5px 8px",
        fontSize: 11,
        cursor: "pointer",
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
      }}
    >
      {icon}
      {label}
    </button>
  );
}

function FormInput({
  label,
  value,
  onChange,
}: Readonly<{
  label: string;
  value: string;
  onChange: (next: string) => void;
}>): JSX.Element {
  return (
    <label style={{ display: "block", marginTop: 6 }}>
      <span style={{ display: "block", fontSize: 11, color: "#8E8E93", marginBottom: 4 }}>{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          width: "100%",
          borderRadius: 8,
          border: "1px solid rgba(58,58,60,0.7)",
          background: "rgba(44,44,46,0.9)",
          color: "#F2F2F7",
          padding: "6px 8px",
          fontSize: 12,
        }}
      />
    </label>
  );
}
