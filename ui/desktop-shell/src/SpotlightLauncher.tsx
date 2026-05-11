import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { Activity, ArrowRight, ArrowUpCircle, Cpu, History, Package2, Search, Shield, ShieldCheck, UserCircle, Wrench, X } from "lucide-react";
import { useShellWindowState } from "./ShellWindowState";

type GroupName = "Applications" | "Actions" | "Recent Tasks" | "Personas" | "Models";
type ItemKind = "application" | "action" | "task" | "persona" | "model";

interface PersonaRecord {
  id: string;
  name: string;
  preferred_model_id: string;
  memory_policy: string;
  is_active: boolean;
}

interface PersonasResponse {
  personas: PersonaRecord[];
  total: number;
}

interface ModelRecord {
  id: string;
  model_id: string;
  source: string;
  quantization: string;
  is_active: boolean;
  benchmark_tps: number | null;
}

interface ModelsResponse {
  models: ModelRecord[];
  total: number;
}

interface ServiceRecord {
  name: string;
  status: string;
  latency_ms: number | null;
}

interface ServicesResponse {
  services: ServiceRecord[];
  total: number;
}

interface TaskRun {
  id: string;
  status: string;
  task_description: string | null;
  started_at: string | null;
  replay_count: number;
}

interface TaskRunsResponse {
  runs: TaskRun[];
  total: number;
}

interface SpotlightItem {
  id: string;
  group: GroupName;
  kind: ItemKind;
  title: string;
  subtitle: string;
  searchableText: string;
  execute: () => Promise<void> | void;
  icon: JSX.Element;
}

const FONT = "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif";
const GROUP_ORDER: GroupName[] = ["Applications", "Actions", "Recent Tasks", "Personas", "Models"];

function isTypingTarget(eventTarget: EventTarget | null): boolean {
  const element = eventTarget as HTMLElement | null;
  if (!element) {
    return false;
  }
  const tag = element.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
    return true;
  }
  return element.isContentEditable;
}

function relativeTime(iso: string | null): string {
  if (!iso) {
    return "unknown time";
  }
  const elapsedMs = Date.now() - new Date(iso).getTime();
  const seconds = Math.max(0, Math.floor(elapsedMs / 1000));
  if (seconds < 60) {
    return `${seconds}s ago`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

async function jsonOrThrow<T>(resp: Response): Promise<T> {
  const body = await resp.text();
  if (!resp.ok) {
    throw new Error(body || `HTTP ${resp.status}`);
  }
  return (body ? JSON.parse(body) : {}) as T;
}

export default function SpotlightLauncher(): JSX.Element {
  const {
    openWindow,
    focusWindow,
    windows,
  } = useShellWindowState();

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [personas, setPersonas] = useState<PersonaRecord[]>([]);
  const [models, setModels] = useState<ModelRecord[]>([]);
  const [services, setServices] = useState<ServiceRecord[]>([]);
  const [tasks, setTasks] = useState<TaskRun[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);

  const inputRef = useRef<HTMLInputElement | null>(null);
  const rowRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const openAndFocusWindow = useCallback((id: string): void => {
    const existing = windows.find((windowRecord) => windowRecord.id === id);
    if (existing?.open) {
      focusWindow(id);
      return;
    }
    openWindow(id);
  }, [focusWindow, openWindow, windows]);

  const refreshData = useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const [personaResp, modelResp, watchdogResp, runsResp] = await Promise.all([
        fetch("/api/personas"),
        fetch("/api/models"),
        fetch("/api/watchdog/services"),
        fetch("/api/audit/runs?limit=10"),
      ]);

      const [personaData, modelData, watchdogData, runsData] = await Promise.all([
        jsonOrThrow<PersonasResponse>(personaResp),
        jsonOrThrow<ModelsResponse>(modelResp),
        jsonOrThrow<ServicesResponse>(watchdogResp),
        jsonOrThrow<TaskRunsResponse>(runsResp),
      ]);

      setPersonas((personaData.personas ?? []).slice(0, 20));
      setModels((modelData.models ?? []).slice(0, 20));
      setServices((watchdogData.services ?? []).slice(0, 20));
      setTasks((runsData.runs ?? []).slice(0, 10));
    } catch (refreshError) {
      setError(`Spotlight failed to load data: ${String(refreshError)}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const keyHandler = (event: KeyboardEvent): void => {
      const isSpaceShortcut = event.code === "Space" && (event.metaKey || event.ctrlKey);
      if (!isSpaceShortcut) {
        if (event.key === "Escape" && open) {
          event.preventDefault();
          setOpen(false);
        }
        return;
      }

      if (isTypingTarget(event.target)) {
        return;
      }

      event.preventDefault();
      setOpen((prev) => !prev);
    };

    globalThis.addEventListener("keydown", keyHandler);
    return () => {
      globalThis.removeEventListener("keydown", keyHandler);
    };
  }, [open]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setSelectedIndex(0);
      setInfo(null);
      return;
    }

    void refreshData();
    inputRef.current?.focus();
  }, [open, refreshData]);

  const applicationItems = useMemo<SpotlightItem[]>(() => {
    return [
      {
        id: "app-notifications",
        group: "Applications",
        kind: "application",
        title: "Notifications",
        subtitle: "Open notification center",
        searchableText: "notifications notification center alerts",
        execute: () => openAndFocusWindow("notifications"),
        icon: <Activity size={14} color="#0A84FF" />,
      },
      {
        id: "app-history",
        group: "Applications",
        kind: "application",
        title: "Task History",
        subtitle: "Open audit task history",
        searchableText: "history task history audit",
        execute: () => openAndFocusWindow("task-history"),
        icon: <History size={14} color="#0A84FF" />,
      },
      {
        id: "app-models",
        group: "Applications",
        kind: "application",
        title: "Model Hub",
        subtitle: "Open model management",
        searchableText: "models model hub",
        execute: () => openAndFocusWindow("model-hub"),
        icon: <Cpu size={14} color="#0A84FF" />,
      },
      {
        id: "app-personas",
        group: "Applications",
        kind: "application",
        title: "Persona Manager",
        subtitle: "Open persona configuration",
        searchableText: "persona personas profile manager",
        execute: () => openAndFocusWindow("persona-manager"),
        icon: <UserCircle size={14} color="#0A84FF" />,
      },
      {
        id: "app-watchdog",
        group: "Applications",
        kind: "application",
        title: "Watchdog Center",
        subtitle: "Open watchdog health panel",
        searchableText: "watchdog health incidents services",
        execute: () => openAndFocusWindow("watchdog-center"),
        icon: <Shield size={14} color="#0A84FF" />,
      },
      {
        id: "app-store",
        group: "Applications",
        kind: "application",
        title: "App Store",
        subtitle: "Manage packages and extensions",
        searchableText: "app store packages install update enable disable",
        execute: () => openAndFocusWindow("app-store"),
        icon: <Package2 size={14} color="#0A84FF" />,
      },
      {
        id: "app-security-center",
        group: "Applications",
        kind: "application",
        title: "Security Center",
        subtitle: "Manage policy grants and audit log",
        searchableText: "security policy grants audit permissions",
        execute: () => openAndFocusWindow("security-center"),
        icon: <ShieldCheck size={14} color="#0A84FF" />,
      },
      {
        id: "app-software-update",
        group: "Applications",
        kind: "application",
        title: "Software Update",
        subtitle: "Check and apply OTA system updates",
        searchableText: "software update ota upgrade patch commit rollback",
        execute: () => openAndFocusWindow("software-update"),
        icon: <ArrowUpCircle size={14} color="#0A84FF" />,
      },
    ];
  }, [openAndFocusWindow]);

  const actionItems = useMemo<SpotlightItem[]>(() => {
    const degradedCount = services.filter((service) => service.status !== "healthy" && service.status !== "unknown").length;

    return [
      {
        id: "action-open-notifications",
        group: "Actions",
        kind: "action",
        title: "Open Notifications",
        subtitle: "Show incoming alerts and updates",
        searchableText: "open notifications alerts",
        execute: () => openAndFocusWindow("notifications"),
        icon: <Wrench size={14} color="#FFD60A" />,
      },
      {
        id: "action-open-history",
        group: "Actions",
        kind: "action",
        title: "Open Task History",
        subtitle: "Inspect run history and replay",
        searchableText: "open task history replay audit",
        execute: () => openAndFocusWindow("task-history"),
        icon: <Wrench size={14} color="#FFD60A" />,
      },
      {
        id: "action-open-voice-settings",
        group: "Actions",
        kind: "action",
        title: "Voice Settings",
        subtitle: "Open voice controls and login-gated voice UI",
        searchableText: "voice settings microphone wake word",
        execute: () => {
          globalThis.dispatchEvent(new CustomEvent("kryos:open-voice-settings"));
        },
        icon: <Wrench size={14} color="#FFD60A" />,
      },
      {
        id: "action-open-model-hub",
        group: "Actions",
        kind: "action",
        title: "Open Model Hub",
        subtitle: "Inspect active and installed models",
        searchableText: "open model hub active model",
        execute: () => openAndFocusWindow("model-hub"),
        icon: <Wrench size={14} color="#FFD60A" />,
      },
      {
        id: "action-open-personas",
        group: "Actions",
        kind: "action",
        title: "Open Persona Manager",
        subtitle: "Inspect active persona",
        searchableText: "open persona manager active persona",
        execute: () => openAndFocusWindow("persona-manager"),
        icon: <Wrench size={14} color="#FFD60A" />,
      },
      {
        id: "action-open-watchdog",
        group: "Actions",
        kind: "action",
        title: "Open Watchdog Center",
        subtitle: degradedCount > 0 ? `${degradedCount} service(s) currently unhealthy` : "All tracked services healthy",
        searchableText: "open watchdog center incidents services",
        execute: () => openAndFocusWindow("watchdog-center"),
        icon: <Wrench size={14} color="#FFD60A" />,
      },
      {
        id: "action-watchdog-scan",
        group: "Actions",
        kind: "action",
        title: "Trigger Watchdog Scan",
        subtitle: "Run immediate health scan across services",
        searchableText: "watchdog scan health check",
        execute: async () => {
          const response = await fetch("/api/watchdog/scan", { method: "POST" });
          const result = await jsonOrThrow<{ scanned?: number }>(response);
          setInfo(`Watchdog scan complete (${result.scanned ?? 0} services checked).`);
          openAndFocusWindow("watchdog-center");
        },
        icon: <Wrench size={14} color="#FFD60A" />,
      },
      {
        id: "action-new-task",
        group: "Actions",
        kind: "action",
        title: "Create New Task",
        subtitle: "Launch a task run through computer-use",
        searchableText: "create new task run execute",
        execute: async () => {
          const description = query.trim() || globalThis.prompt("Task description") || "";
          if (!description.trim()) {
            setInfo("New task cancelled.");
            return;
          }
          const response = await fetch("/computer/task/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ task_description: description.trim(), max_steps: 20 }),
          });
          await jsonOrThrow<Record<string, unknown>>(response);
          setInfo("New task launched successfully.");
          openAndFocusWindow("task-history");
        },
        icon: <Wrench size={14} color="#FFD60A" />,
      },
      {
        id: "action-active-persona",
        group: "Actions",
        kind: "action",
        title: "Open Active Persona Details",
        subtitle: "Jump to currently active persona",
        searchableText: "active persona details",
        execute: async () => {
          const response = await fetch("/api/personas/active");
          const payload = await jsonOrThrow<{ active?: PersonaRecord }>(response);
          if (payload.active?.name) {
            setInfo(`Active persona: ${payload.active.name}`);
          }
          openAndFocusWindow("persona-manager");
        },
        icon: <Wrench size={14} color="#FFD60A" />,
      },
      {
        id: "action-active-model",
        group: "Actions",
        kind: "action",
        title: "Open Active Model Details",
        subtitle: "Jump to currently active model",
        searchableText: "active model details",
        execute: async () => {
          const response = await fetch("/api/models");
          const payload = await jsonOrThrow<ModelsResponse>(response);
          const activeModel = (payload.models ?? []).find((model) => model.is_active);
          setInfo(activeModel ? `Active model: ${activeModel.model_id}` : "No active model configured.");
          openAndFocusWindow("model-hub");
        },
        icon: <Wrench size={14} color="#FFD60A" />,
      },
      {
        id: "action-latest-incidents",
        group: "Actions",
        kind: "action",
        title: "Open Latest Incidents Feed",
        subtitle: "Show recent watchdog incidents",
        searchableText: "latest incidents feed watchdog",
        execute: () => openAndFocusWindow("watchdog-center"),
        icon: <Wrench size={14} color="#FFD60A" />,
      },
      {
        id: "action-replay-latest",
        group: "Actions",
        kind: "action",
        title: "Replay Most Recent Task",
        subtitle: tasks[0] ? `Replay ${tasks[0].task_description ?? tasks[0].id}` : "No recent task available",
        searchableText: "replay recent task",
        execute: async () => {
          if (!tasks[0]) {
            setInfo("No recent task available to replay.");
            return;
          }
          const response = await fetch(`/api/audit/runs/${encodeURIComponent(tasks[0].id)}/replay`, {
            method: "POST",
          });
          await jsonOrThrow<Record<string, unknown>>(response);
          setInfo(`Replayed task ${tasks[0].id}.`);
          openAndFocusWindow("task-history");
        },
        icon: <Wrench size={14} color="#FFD60A" />,
      },
    ];
  }, [openAndFocusWindow, query, services, tasks]);

  const taskItems = useMemo<SpotlightItem[]>(() => {
    return tasks.slice(0, 5).map((task) => ({
      id: `task-${task.id}`,
      group: "Recent Tasks",
      kind: "task",
      title: task.task_description || task.id,
      subtitle: `${task.status} • ${relativeTime(task.started_at)} • replayed ${task.replay_count}x`,
      searchableText: `${task.id} ${task.task_description ?? ""} ${task.status}`.toLowerCase(),
      execute: async () => {
        const response = await fetch(`/api/audit/runs/${encodeURIComponent(task.id)}/replay`, {
          method: "POST",
        });
        await jsonOrThrow<Record<string, unknown>>(response);
        setInfo(`Replayed task ${task.id}.`);
        openAndFocusWindow("task-history");
      },
      icon: <History size={14} color="#8E8E93" />,
    }));
  }, [openAndFocusWindow, tasks]);

  const personaItems = useMemo<SpotlightItem[]>(() => {
    return personas.slice(0, 8).map((persona) => ({
      id: `persona-${persona.id}`,
      group: "Personas",
      kind: "persona",
      title: persona.name,
      subtitle: `${persona.preferred_model_id} • ${persona.memory_policy}${persona.is_active ? " • active" : ""}`,
      searchableText: `${persona.name} ${persona.preferred_model_id} ${persona.memory_policy}`.toLowerCase(),
      execute: () => {
        setInfo(`Selected persona ${persona.name}.`);
        openAndFocusWindow("persona-manager");
      },
      icon: <UserCircle size={14} color={persona.is_active ? "#30D158" : "#8E8E93"} />,
    }));
  }, [openAndFocusWindow, personas]);

  const modelItems = useMemo<SpotlightItem[]>(() => {
    return models.slice(0, 8).map((model) => ({
      id: `model-${model.id}`,
      group: "Models",
      kind: "model",
      title: model.model_id,
      subtitle: `${model.source} • ${model.quantization}${model.is_active ? " • active" : ""}`,
      searchableText: `${model.model_id} ${model.source} ${model.quantization}`.toLowerCase(),
      execute: () => {
        setInfo(`Selected model ${model.model_id}.`);
        openAndFocusWindow("model-hub");
      },
      icon: <Cpu size={14} color={model.is_active ? "#30D158" : "#8E8E93"} />,
    }));
  }, [models, openAndFocusWindow]);

  const allItems = useMemo<SpotlightItem[]>(() => {
    return [
      ...applicationItems,
      ...actionItems,
      ...taskItems,
      ...personaItems,
      ...modelItems,
    ];
  }, [applicationItems, actionItems, taskItems, personaItems, modelItems]);

  const filteredItems = useMemo<SpotlightItem[]>(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) {
      return allItems;
    }
    return allItems.filter((item) => {
      return item.title.toLowerCase().includes(needle)
        || item.subtitle.toLowerCase().includes(needle)
        || item.searchableText.includes(needle);
    });
  }, [allItems, query]);

  useEffect(() => {
    if (!open) {
      return;
    }
    if (filteredItems.length === 0) {
      setSelectedIndex(0);
      return;
    }
    setSelectedIndex((prev) => Math.min(prev, filteredItems.length - 1));
  }, [filteredItems, open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const selectedElement = rowRefs.current[selectedIndex];
    selectedElement?.scrollIntoView({ block: "nearest" });
  }, [open, selectedIndex]);

  const groupedItems = useMemo<Record<GroupName, SpotlightItem[]>>(() => {
    const groups: Record<GroupName, SpotlightItem[]> = {
      Applications: [],
      Actions: [],
      "Recent Tasks": [],
      Personas: [],
      Models: [],
    };
    for (const item of filteredItems) {
      groups[item.group].push(item);
    }
    return groups;
  }, [filteredItems]);

  const activateSelected = useCallback(async (): Promise<void> => {
    if (!filteredItems[selectedIndex]) {
      return;
    }
    setError(null);
    try {
      await filteredItems[selectedIndex].execute();
      setOpen(false);
    } catch (activationError) {
      setError(`Action failed: ${String(activationError)}`);
    }
  }, [filteredItems, selectedIndex]);

  const onInputKeyDown = useCallback((event: ReactKeyboardEvent<HTMLInputElement>): void => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (filteredItems.length > 0) {
        setSelectedIndex((prev) => (prev + 1) % filteredItems.length);
      }
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (filteredItems.length > 0) {
        setSelectedIndex((prev) => (prev - 1 + filteredItems.length) % filteredItems.length);
      }
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      void activateSelected();
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
    }
  }, [activateSelected, filteredItems.length]);

  const panelStyle: CSSProperties = {
    width: "min(760px, calc(100vw - 40px))",
    maxHeight: "80vh",
    background: "rgba(24,24,27,0.92)",
    border: "1px solid rgba(58,58,60,0.75)",
    borderRadius: 16,
    backdropFilter: "blur(20px)",
    WebkitBackdropFilter: "blur(20px)",
    boxShadow: "0 28px 72px rgba(0,0,0,0.5)",
    color: "#F2F2F7",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    fontFamily: FONT,
  };

  return (
    <>
      {open && (
        <dialog
          open
          aria-modal="true"
          aria-label="Spotlight Launcher"
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 12000,
            background: "rgba(0,0,0,0.36)",
            backdropFilter: "blur(8px)",
            WebkitBackdropFilter: "blur(8px)",
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "center",
            paddingTop: "12vh",
          }}
        >
          <div style={panelStyle}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                borderBottom: "1px solid rgba(58,58,60,0.55)",
                padding: "12px 14px",
              }}
            >
              <Search size={16} color="#8E8E93" />
              <input
                ref={inputRef}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={onInputKeyDown}
                placeholder="Search commands, tasks, personas, models..."
                aria-label="Spotlight search"
                style={{
                  flex: 1,
                  background: "transparent",
                  border: "none",
                  outline: "none",
                  color: "#F2F2F7",
                  fontSize: 16,
                  fontFamily: FONT,
                }}
              />
              <button
                type="button"
                aria-label="Close Spotlight"
                onClick={() => setOpen(false)}
                style={{
                  border: "none",
                  background: "none",
                  color: "#8E8E93",
                  display: "inline-flex",
                  cursor: "pointer",
                }}
              >
                <X size={16} />
              </button>
            </div>

            <div style={{ padding: "8px 14px", borderBottom: "1px solid rgba(58,58,60,0.45)", fontSize: 11, color: "#8E8E93" }}>
              Cmd+Space / Ctrl+Space • Arrow keys to navigate • Enter to run • Escape to close
            </div>

            {error && (
              <div style={{ margin: "10px 14px 0", fontSize: 12, color: "#FF453A" }}>{error}</div>
            )}
            {info && (
              <div style={{ margin: "10px 14px 0", fontSize: 12, color: "#30D158" }}>{info}</div>
            )}

            <div style={{ overflowY: "auto", padding: "10px 12px 14px" }}>
              {loading && (
                <div style={{ color: "#8E8E93", fontSize: 12, padding: "8px 4px" }}>Loading Spotlight data...</div>
              )}

              {!loading && filteredItems.length === 0 && (
                <div style={{ color: "#8E8E93", fontSize: 12, padding: "8px 4px" }}>No matches found for your query.</div>
              )}

              {!loading && GROUP_ORDER.map((group) => {
                const items = groupedItems[group];
                if (items.length === 0) {
                  return null;
                }
                return (
                  <section key={group} style={{ marginBottom: 12 }}>
                    <h3
                      style={{
                        margin: 0,
                        padding: "6px 6px 4px",
                        fontSize: 11,
                        textTransform: "uppercase",
                        letterSpacing: 0.6,
                        color: "#8E8E93",
                        fontWeight: 600,
                      }}
                    >
                      {group}
                    </h3>

                    {items.map((item) => {
                      const index = filteredItems.findIndex((candidate) => candidate.id === item.id);
                      const selected = index === selectedIndex;
                      return (
                        <button
                          key={item.id}
                          ref={(element) => {
                            rowRefs.current[index] = element;
                          }}
                          type="button"
                          onClick={() => {
                            setSelectedIndex(index);
                            void activateSelected();
                          }}
                          onMouseEnter={() => setSelectedIndex(index)}
                          style={{
                            width: "100%",
                            border: selected ? "1px solid rgba(10,132,255,0.75)" : "1px solid rgba(58,58,60,0.25)",
                            background: selected ? "rgba(10,132,255,0.2)" : "rgba(44,44,46,0.45)",
                            borderRadius: 10,
                            color: "#F2F2F7",
                            padding: "10px 10px",
                            marginBottom: 6,
                            cursor: "pointer",
                            textAlign: "left",
                            display: "flex",
                            alignItems: "center",
                            gap: 10,
                            outline: selected ? "2px solid rgba(10,132,255,0.35)" : "none",
                          }}
                        >
                          <span style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: 22, height: 22 }}>
                            {item.icon}
                          </span>
                          <span style={{ flex: 1, minWidth: 0 }}>
                            <span style={{ display: "block", fontSize: 13, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {item.title}
                            </span>
                            <span style={{ display: "block", fontSize: 11, color: "#A1A1A6", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {item.subtitle}
                            </span>
                          </span>
                          <ArrowRight size={13} color={selected ? "#F2F2F7" : "#8E8E93"} />
                        </button>
                      );
                    })}
                  </section>
                );
              })}
            </div>
          </div>
        </dialog>
      )}
    </>
  );
}
