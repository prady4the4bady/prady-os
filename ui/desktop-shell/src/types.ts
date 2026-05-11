export type AppId =
  | "terminal"
  | "browser"
  | "files"
  | "assistant"
  | "settings"
  | "activity"
  | "models"
  | "screen"
  | "lumyn"
  | "desktop-agent"
  | "process-viewer"
  | "memory-browser";

export interface WindowItem {
  id: string;
  appId: AppId;
  title: string;
  icon: string;
  x: number;
  y: number;
  width: number;
  height: number;
  zIndex: number;
  minimized: boolean;
  maximized: boolean;
}

export interface SwarmStartRequest {
  goal: string;
  max_agents: number;
  model_id?: string;
}

export interface SwarmStartResponse {
  swarm_id: string;
  goal: string;
  max_agents: number;
  model_id: string;
  status: string;
}

export interface AgentState {
  agent_id: string;
  model_id: string;
  status: string;
  memory_namespace: string;
  task_history_count: number;
  result?: Record<string, unknown>;
}

export interface SwarmState {
  swarm_id: string;
  goal: string;
  status: string;
  agent_count: number;
  agents: AgentState[];
  started_at: string;
  finished_at?: string;
  merged_result?: Record<string, unknown>;
}

export interface SwarmStatusResponse {
  swarms: SwarmState[];
}

export interface SwarmResultResponse {
  swarm_id: string;
  status: string;
  merged_result?: Record<string, unknown>;
}

export interface PullModelRequest {
  source: string;
}

export interface PullModelResponse {
  model_id: string;
  status: string;
  benchmark_score?: number;
  tokens_per_sec?: number;
}

export interface ModelListItem {
  model_id: string;
  name: string;
  source: string;
  file_path: string;
  sha256: string;
  quantization: string;
  size_gb: number;
  pulled_at: string;
  status: string;
  benchmark_score?: number | null;
  tokens_per_sec?: number | null;
}

export interface LoadedModelsResponse {
  loaded_models: string[];
  vyrex_enabled?: boolean;
}

export interface ScreenSnapshot {
  imageBase64: string;
  ocrText?: string[];
}
