import type {
  SwarmResultResponse,
  SwarmStartRequest,
  SwarmStartResponse,
  SwarmStatusResponse,
} from "../types";

async function readJsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`HTTP ${res.status}: ${body}`);
  }
  return (await res.json()) as T;
}

export async function startSwarm(payload: SwarmStartRequest): Promise<SwarmStartResponse> {
  const res = await fetch("/swarm/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readJsonOrThrow<SwarmStartResponse>(res);
}

export async function getSwarmStatus(): Promise<SwarmStatusResponse> {
  const res = await fetch("/swarm/status");
  return readJsonOrThrow<SwarmStatusResponse>(res);
}

export async function cancelSwarm(swarmId: string): Promise<{ swarm_id: string; cancelled: boolean }> {
  const res = await fetch(`/swarm/${swarmId}/cancel`, { method: "POST" });
  return readJsonOrThrow<{ swarm_id: string; cancelled: boolean }>(res);
}

export async function getSwarmResult(swarmId: string): Promise<SwarmResultResponse> {
  const res = await fetch(`/swarm/${swarmId}/result`);
  return readJsonOrThrow<SwarmResultResponse>(res);
}
