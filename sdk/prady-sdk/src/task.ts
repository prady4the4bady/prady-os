import type { ScheduleOptions, ScheduledTask } from "./types.js";

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export class KryosTask {
  constructor(private readonly apiBase: string = "http://localhost:8005") {}

  async schedule(description: string, runAt: Date, options: ScheduleOptions = {}): Promise<string> {
    const response = await fetch(`${this.apiBase}/tasks/schedule`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description, run_at: runAt.toISOString(), ...options }),
    });
    const data = await readJson<{ schedule_id: string }>(response);
    return data.schedule_id;
  }

  async cancel(scheduleId: string): Promise<void> {
    const response = await fetch(`${this.apiBase}/tasks/${encodeURIComponent(scheduleId)}`, {
      method: "DELETE",
    });
    await readJson<{ cancelled: boolean }>(response);
  }

  async list(): Promise<ScheduledTask[]> {
    const response = await fetch(`${this.apiBase}/tasks`);
    const data = await readJson<{ tasks?: ScheduledTask[] } | ScheduledTask[]>(response);
    return Array.isArray(data) ? data : data.tasks ?? [];
  }
}
