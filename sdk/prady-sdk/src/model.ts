import type { ModelInfo, ModelOptions } from "./types.js";

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export class KryosModel {
  constructor(private readonly apiBase: string = "http://localhost:8000") {}

  async query(prompt: string, options: ModelOptions = {}): Promise<string> {
    const response = await fetch(`${this.apiBase}/v1/chat/completions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, ...options }),
    });
    const data = await readJson<{ choices?: Array<{ message?: { content?: string } }>; content?: string }>(response);
    return data.content ?? data.choices?.[0]?.message?.content ?? "";
  }

  async listModels(): Promise<ModelInfo[]> {
    const response = await fetch("http://localhost:8003/models");
    const data = await readJson<{ models?: ModelInfo[] } | ModelInfo[]>(response);
    return Array.isArray(data) ? data : data.models ?? [];
  }
}
