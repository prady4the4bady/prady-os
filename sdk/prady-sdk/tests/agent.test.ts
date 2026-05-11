import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PraxAgent } from "../src/agent.js";

const fetchMock = vi.fn();

function jsonResponse(body: object, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("PraxAgent", () => {
  it("uses the default api base", () => {
    const agent = new PraxAgent();
    expect(agent).toBeDefined();
  });

  it("assigns a task successfully", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ task_id: "t1", status: "queued", result: "ok" }));
    const agent = new PraxAgent("http://example");
    const result = await agent.assignTask("do it", { priority: 2 });
    expect(result.task_id).toBe("t1");
    expect(fetchMock).toHaveBeenCalledWith("http://example/tasks", expect.objectContaining({ method: "POST" }));
  });

  it("includes task options in the request body", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ task_id: "t1", status: "queued" }));
    const agent = new PraxAgent("http://example");
    await agent.assignTask("do it", { timeout_ms: 5000 });
    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string) as { description: string; timeout_ms: number };
    expect(body.timeout_ms).toBe(5000);
    expect(body.description).toBe("do it");
  });

  it("reads task status by id", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ task_id: "t1", status: "done", result: "ok" }));
    const agent = new PraxAgent("http://example");
    const result = await agent.getTaskStatus("t1");
    expect(result.result).toBe("ok");
  });

  it("lists skills from the SDK service", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ skills: [{ skill_id: "s1", description: "desc", avg_score: 0.8 }] }));
    const agent = new PraxAgent();
    const skills = await agent.listSkills();
    expect(skills[0].skill_id).toBe("s1");
  });

  it("throws on task errors", async () => {
    fetchMock.mockResolvedValueOnce(new Response("boom", { status: 500 }));
    const agent = new PraxAgent("http://example");
    await expect(agent.assignTask("do it")).rejects.toThrow();
  });
});
