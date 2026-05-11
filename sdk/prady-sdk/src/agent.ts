import type { Skill, TaskOptions, TaskResult } from "./types.js";

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export class PraxAgent {
  constructor(private readonly apiBase: string = "http://localhost:8001") {}

  async assignTask(description: string, options: TaskOptions = {}): Promise<TaskResult> {
    const response = await fetch(`${this.apiBase}/tasks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description, ...options }),
    });
    return readJson<TaskResult>(response);
  }

  async getTaskStatus(taskId: string): Promise<TaskResult> {
    const response = await fetch(`${this.apiBase}/tasks/${encodeURIComponent(taskId)}`);
    return readJson<TaskResult>(response);
  }

  async listSkills(): Promise<Skill[]> {
    const response = await fetch("http://localhost:8018/learn/skills");
    const data = await readJson<{ skills?: Skill[]; items?: Skill[] } | Skill[]>(response);
    if (Array.isArray(data)) {
      return data;
    }
    return data.skills ?? data.items ?? [];
  }
}
