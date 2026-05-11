export interface TaskOptions {
  priority?: number;
  timeout_ms?: number;
}

export interface TaskResult {
  task_id: string;
  status: string;
  result?: string;
  error?: string;
}

export interface Skill {
  skill_id: string;
  description: string;
  avg_score: number;
}

export interface ModelOptions {
  max_tokens?: number;
  temperature?: number;
  model?: string;
}

export interface ModelInfo {
  id: string;
  name: string;
  active: boolean;
}

export interface ScheduleOptions {
  repeat?: "once" | "daily" | "weekly";
}

export interface ScheduledTask {
  schedule_id: string;
  description: string;
  run_at: string;
  status: string;
}
