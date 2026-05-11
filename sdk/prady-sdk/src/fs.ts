async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export class KryosFS {
  constructor(
    private readonly appName: string,
    private readonly apiBase: string = "http://localhost:8001"
  ) {}

  async read(relativePath: string): Promise<string> {
    const response = await fetch(
      `${this.apiBase}/sdk/fs/read?app=${encodeURIComponent(this.appName)}&path=${encodeURIComponent(relativePath)}`
    );
    const data = await readJson<{ content: string }>(response);
    return data.content;
  }

  async write(relativePath: string, content: string): Promise<void> {
    const response = await fetch(`${this.apiBase}/sdk/fs/write`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ app: this.appName, path: relativePath, content }),
    });
    await readJson<{ written: boolean }>(response);
  }

  async list(relativePath: string): Promise<string[]> {
    const response = await fetch(
      `${this.apiBase}/sdk/fs/list?app=${encodeURIComponent(this.appName)}&path=${encodeURIComponent(relativePath)}`
    );
    const data = await readJson<{ entries?: Array<{ name: string }> } | string[]>(response);
    if (Array.isArray(data)) {
      return data;
    }
    return (data.entries ?? []).map((entry) => entry.name);
  }

  async delete(relativePath: string): Promise<void> {
    const response = await fetch(
      `${this.apiBase}/sdk/fs/delete?app=${encodeURIComponent(this.appName)}&path=${encodeURIComponent(relativePath)}`,
      { method: "DELETE" }
    );
    await readJson<{ deleted: boolean }>(response);
  }
}
