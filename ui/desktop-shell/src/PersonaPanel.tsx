import React, { useEffect, useMemo, useState } from 'react';

interface PersonaRecord {
  id: string;
  name: string;
  system_prompt: string;
  model_id: string;
  memory_scope: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface PersonaListResponse {
  personas: PersonaRecord[];
}

interface ActivePersonaResponse {
  active: PersonaRecord | null;
}

interface ModelItem {
  name: string;
}

interface ModelsListResponse {
  models: ModelItem[];
}

interface PersonaFormState {
  name: string;
  system_prompt: string;
  model_id: string;
  memory_scope: string;
}

const API = 'http://localhost:8100/api';

const emptyForm: PersonaFormState = {
  name: '',
  system_prompt: '',
  model_id: '',
  memory_scope: 'default',
};

export default function PersonaPanel() {
  const [personas, setPersonas] = useState<PersonaRecord[]>([]);
  const [activePersonaId, setActivePersonaId] = useState<string | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [createForm, setCreateForm] = useState<PersonaFormState>(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<PersonaFormState>(emptyForm);

  const style = useMemo<React.CSSProperties>(
    () => ({
      position: 'fixed',
      left: 600,
      top: 76,
      width: 560,
      maxHeight: '76vh',
      overflow: 'auto',
      zIndex: 49,
      borderRadius: 14,
      border: '1px solid rgba(255,255,255,0.12)',
      background: 'rgba(28, 28, 30, 0.72)',
      backdropFilter: 'blur(20px) saturate(180%)',
      WebkitBackdropFilter: 'blur(20px) saturate(180%)',
      boxShadow: '0 10px 30px rgba(0,0,0,0.35)',
      color: '#ebebf5',
      fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif",
      padding: 14,
    }),
    []
  );

  const loadModels = async () => {
    try {
      const res = await fetch(`${API}/models/list`);
      if (!res.ok) return;
      const data = (await res.json()) as ModelsListResponse;
      const names = (data.models || []).map((m) => m.name);
      setModels(names);

      setCreateForm((prev) => ({
        ...prev,
        model_id: prev.model_id || names[0] || '',
      }));
    } catch {
      // no-op
    }
  };

  const loadPersonas = async () => {
    try {
      const [listRes, activeRes] = await Promise.all([
        fetch(`${API}/persona`),
        fetch(`${API}/persona/active`),
      ]);

      if (listRes.ok) {
        const data = (await listRes.json()) as PersonaListResponse;
        setPersonas(data.personas || []);
      }

      if (activeRes.ok) {
        const active = (await activeRes.json()) as ActivePersonaResponse;
        setActivePersonaId(active.active?.id || null);
      }
    } catch {
      // no-op
    }
  };

  useEffect(() => {
    void loadModels();
    void loadPersonas();
  }, []);

  const createPersona = async () => {
    if (!createForm.name.trim() || !createForm.system_prompt.trim() || !createForm.model_id.trim()) return;

    const res = await fetch(`${API}/persona`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(createForm),
    });

    if (res.ok) {
      setCreateForm({ ...emptyForm, model_id: models[0] || '' });
      void loadPersonas();
    }
  };

  const beginEdit = (persona: PersonaRecord) => {
    setEditingId(persona.id);
    setEditForm({
      name: persona.name,
      system_prompt: persona.system_prompt,
      model_id: persona.model_id,
      memory_scope: persona.memory_scope,
    });
  };

  const saveEdit = async (personaId: string) => {
    const res = await fetch(`${API}/persona/${personaId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(editForm),
    });

    if (res.ok) {
      setEditingId(null);
      setEditForm(emptyForm);
      void loadPersonas();
    }
  };

  const activatePersona = async (personaId: string) => {
    const res = await fetch(`${API}/persona/${personaId}/activate`, { method: 'POST' });
    if (res.ok) {
      setActivePersonaId(personaId);
      void loadPersonas();
    }
  };

  const deletePersona = async (personaId: string, personaName: string) => {
    if (!globalThis.confirm(`Delete persona ${personaName}?`)) return;
    const res = await fetch(`${API}/persona/${personaId}`, { method: 'DELETE' });
    if (res.ok) {
      if (activePersonaId === personaId) {
        setActivePersonaId(null);
      }
      if (editingId === personaId) {
        setEditingId(null);
      }
      void loadPersonas();
    }
  };

  const inputStyle: React.CSSProperties = {
    borderRadius: 8,
    border: '1px solid rgba(255,255,255,0.12)',
    background: 'rgba(255,255,255,0.08)',
    color: '#fff',
    padding: 8,
  };

  return (
    <section style={style}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10, fontSize: 12 }}>
        <strong>Personas</strong>
        <span>Active: {activePersonaId ? 'SET' : 'NONE'} • Total: {personas.length}</span>
      </div>

      <div style={{ border: '1px solid rgba(255,255,255,0.08)', borderRadius: 10, padding: 10, marginBottom: 12, display: 'grid', gap: 8 }}>
        <strong style={{ fontSize: 12 }}>Create Persona</strong>
        <input
          value={createForm.name}
          onChange={(e) => setCreateForm((p) => ({ ...p, name: e.target.value }))}
          placeholder="Name"
          style={inputStyle}
        />
        <textarea
          value={createForm.system_prompt}
          onChange={(e) => setCreateForm((p) => ({ ...p, system_prompt: e.target.value }))}
          placeholder="System prompt"
          rows={4}
          style={inputStyle}
        />
        <select
          value={createForm.model_id}
          onChange={(e) => setCreateForm((p) => ({ ...p, model_id: e.target.value }))}
          style={inputStyle}
        >
          {models.length === 0 && <option value="">No models found</option>}
          {models.map((modelName) => (
            <option key={modelName} value={modelName}>
              {modelName}
            </option>
          ))}
        </select>
        <select
          value={createForm.memory_scope}
          onChange={(e) => setCreateForm((p) => ({ ...p, memory_scope: e.target.value }))}
          style={inputStyle}
        >
          <option value="default">default</option>
          <option value="task">task</option>
          <option value="global">global</option>
        </select>
        <button
          onClick={() => void createPersona()}
          style={{ borderRadius: 8, border: 'none', background: '#0a84ff', color: '#fff', padding: '8px 10px' }}
        >
          Create Persona
        </button>
      </div>

      <div style={{ display: 'grid', gap: 8 }}>
        {personas.map((persona) => {
          const isEditing = editingId === persona.id;
          const isActive = activePersonaId === persona.id || persona.is_active;

          return (
            <article key={persona.id} style={{ border: '1px solid rgba(255,255,255,0.08)', borderRadius: 10, padding: 10, background: 'rgba(0,0,0,0.2)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: isActive ? '#30d158' : 'rgba(255,255,255,0.25)',
                    }}
                  />
                  <strong>{persona.name}</strong>
                </div>
                <span style={{ fontSize: 11, color: 'rgba(235,235,245,0.65)' }}>{persona.model_id}</span>
              </div>

              {isEditing ? (
                <div style={{ display: 'grid', gap: 8 }}>
                  <input
                    value={editForm.name}
                    onChange={(e) => setEditForm((p) => ({ ...p, name: e.target.value }))}
                    style={inputStyle}
                  />
                  <textarea
                    value={editForm.system_prompt}
                    onChange={(e) => setEditForm((p) => ({ ...p, system_prompt: e.target.value }))}
                    rows={4}
                    style={inputStyle}
                  />
                  <select
                    value={editForm.model_id}
                    onChange={(e) => setEditForm((p) => ({ ...p, model_id: e.target.value }))}
                    style={inputStyle}
                  >
                    {models.map((modelName) => (
                      <option key={modelName} value={modelName}>
                        {modelName}
                      </option>
                    ))}
                  </select>
                  <select
                    value={editForm.memory_scope}
                    onChange={(e) => setEditForm((p) => ({ ...p, memory_scope: e.target.value }))}
                    style={inputStyle}
                  >
                    <option value="default">default</option>
                    <option value="task">task</option>
                    <option value="global">global</option>
                  </select>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button
                      onClick={() => void saveEdit(persona.id)}
                      style={{ borderRadius: 8, border: 'none', background: '#30d158', color: '#fff', padding: '6px 10px' }}
                    >
                      Save
                    </button>
                    <button
                      onClick={() => setEditingId(null)}
                      style={{ borderRadius: 8, border: '1px solid rgba(255,255,255,0.2)', background: 'transparent', color: '#fff', padding: '6px 10px' }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <div style={{ fontSize: 12, whiteSpace: 'pre-wrap', marginBottom: 8 }}>{persona.system_prompt}</div>
                  <div style={{ fontSize: 11, color: 'rgba(235,235,245,0.65)', marginBottom: 8 }}>Memory scope: {persona.memory_scope}</div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button
                      onClick={() => void activatePersona(persona.id)}
                      style={{ borderRadius: 8, border: 'none', background: '#0a84ff', color: '#fff', padding: '6px 10px' }}
                    >
                      Activate
                    </button>
                    <button
                      onClick={() => beginEdit(persona)}
                      style={{ borderRadius: 8, border: '1px solid rgba(255,255,255,0.2)', background: 'transparent', color: '#fff', padding: '6px 10px' }}
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => void deletePersona(persona.id, persona.name)}
                      style={{ borderRadius: 8, border: '1px solid rgba(255,69,58,0.4)', background: 'rgba(255,69,58,0.16)', color: '#ff8b82', padding: '6px 10px' }}
                    >
                      Delete
                    </button>
                  </div>
                </>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
