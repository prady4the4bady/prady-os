import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { KryosTask } from "../src/task.js";

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

describe("KryosTask", () => {
  it("uses the default api base", () => {
    const task = new KryosTask();
    expect(task).toBeDefined();
  });

  it("schedules a task and returns the id", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ schedule_id: "s1" }));
    const task = new KryosTask("http://example");
    const result = await task.schedule("run", new Date("2026-05-11T00:00:00Z"));
    expect(result).toBe("s1");
  });

  it("includes repeat options when scheduling", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ schedule_id: "s1" }));
    const task = new KryosTask("http://example");
    await task.schedule("run", new Date("2026-05-11T00:00:00Z"), { repeat: "daily" });
    const payload = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string) as { repeat: string };
    expect(payload.repeat).toBe("daily");
  });

  it("cancels schedules", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ cancelled: true }));
    const task = new KryosTask("http://example");
    await task.cancel("s1");
    expect(fetchMock).toHaveBeenCalledWith("http://example/tasks/s1", expect.objectContaining({ method: "DELETE" }));
  });

  it("lists scheduled tasks", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ tasks: [{ schedule_id: "s1", description: "run", run_at: "2026-05-11T00:00:00Z", status: "scheduled" }] }));
    const task = new KryosTask("http://example");
    const result = await task.list();
    expect(result[0].schedule_id).toBe("s1");
  });

  it("throws on list failure", async () => {
    fetchMock.mockResolvedValueOnce(new Response("boom", { status: 500 }));
    const task = new KryosTask("http://example");
    await expect(task.list()).rejects.toThrow();
  });
});
