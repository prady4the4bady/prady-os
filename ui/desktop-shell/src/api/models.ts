import type {
  LoadedModelsResponse,
  ModelListItem,
  PullModelRequest,
  PullModelResponse,
} from "../types";

async function readJsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`HTTP ${res.status}: ${body}`);
  }
  return (await res.json()) as T;
}

function parseSseBlock(block: string, previousEvent: string): { eventName: string; payloadLine: string } {
  const lines = block.split("\n");
  let eventName = previousEvent;
  let payloadLine = "";
  for (const line of lines) {
    if (line.startsWith("event:")) {
      eventName = line.replace("event:", "").trim();
    }
    if (line.startsWith("data:")) {
      payloadLine = line.replace("data:", "").trim();
    }
  }
  return { eventName, payloadLine };
}

function pullCompletionFromLine(line: string): PullModelResponse | null {
  if (!line.startsWith("data:")) {
    return null;
  }

  const payloadLine = line.replace(/^data:\s*/, "");
  try {
    const parsed = JSON.parse(payloadLine) as PullModelResponse & { message?: string };
    if (parsed.message) {
      throw new Error(parsed.message);
    }
    if (parsed.status === "ready" || parsed.model_id) {
      return parsed;
    }
  } catch {
    return null;
  }

  return null;
}

export async function pullModel(payload: PullModelRequest): Promise<PullModelResponse> {
  const chunks: string[] = [];
  const res = await fetch("/models/pull", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok || !res.body) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    chunks.push(decoder.decode(value, { stream: true }));
  }

  const streamText = chunks.join("");
  const lines = streamText.split("\n");
  let final: PullModelResponse | null = null;
  for (const line of lines) {
    const parsed = pullCompletionFromLine(line);
    if (parsed) {
      final = parsed;
    }
  }

  if (!final) {
    throw new Error("Model pull did not return completion payload");
  }
  return final;
}

export async function streamPullModel(
  payload: PullModelRequest,
  onEvent: (event: { event: string; data: Record<string, unknown> }) => void
): Promise<void> {
  const res = await fetch("/models/pull", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok || !res.body) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let eventName = "message";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });

    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);

      const parsedBlock = parseSseBlock(block, eventName);
      eventName = parsedBlock.eventName;
      const payloadLine = parsedBlock.payloadLine;

      if (payloadLine) {
        try {
          const parsed = JSON.parse(payloadLine) as Record<string, unknown>;
          onEvent({ event: eventName, data: parsed });
        } catch {
          // Ignore malformed event payload.
        }
      }

      boundary = buffer.indexOf("\n\n");
    }
  }
}

export async function listModels(): Promise<ModelListItem[]> {
  const res = await fetch("/models/list");
  return readJsonOrThrow<ModelListItem[]>(res);
}

export async function getModel(modelId: string): Promise<ModelListItem> {
  const res = await fetch(`/models/${modelId}`);
  return readJsonOrThrow<ModelListItem>(res);
}

export async function getModelBenchmark(modelId: string): Promise<{ benchmark_score: number | null; tokens_per_sec: number | null }> {
  const res = await fetch(`/models/${modelId}/benchmark`);
  return readJsonOrThrow<{ benchmark_score: number | null; tokens_per_sec: number | null }>(res);
}

export async function deleteModel(modelId: string): Promise<void> {
  const res = await fetch(`/models/${modelId}`, { method: "DELETE" });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
}

export async function activateModel(modelId: string): Promise<void> {
  const res = await fetch(`/gateway/models/${modelId}/activate`, { method: "POST" });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
}

export async function listLoadedModels(): Promise<LoadedModelsResponse> {
  const res = await fetch("/gateway/models/loaded");
  return readJsonOrThrow<LoadedModelsResponse>(res);
}

export async function getVyrexEnabled(): Promise<boolean> {
  try {
    const data = await listLoadedModels();
    if (typeof data.vyrex_enabled === "boolean") {
      return data.vyrex_enabled;
    }
    return true;
  } catch {
    return false;
  }
}
