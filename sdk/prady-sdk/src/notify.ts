async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export class KryosNotify {
  constructor(private readonly apiBase: string = "http://localhost:8007") {}

  async send(title: string, body: string, severity: "info" | "warning" | "critical" = "info"): Promise<void> {
    const response = await fetch(`${this.apiBase}/notify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, body, severity, source: "sdk-app" }),
    });
    await readJson<{ ok: boolean }>(response);
  }
}
