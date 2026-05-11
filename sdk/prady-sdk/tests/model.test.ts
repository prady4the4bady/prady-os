import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { KryosModel } from "../src/model.js";

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

describe("KryosModel", () => {
  it("uses the default api base", () => {
    const model = new KryosModel();
    expect(model).toBeDefined();
  });

  it("returns root content from query responses", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ content: "hello" }));
    const model = new KryosModel("http://example");
    const result = await model.query("hi");
    expect(result).toBe("hello");
  });

  it("returns choice content when present", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ choices: [{ message: { content: "world" } }] }));
    const model = new KryosModel("http://example");
    const result = await model.query("hi");
    expect(result).toBe("world");
  });

  it("sends model options in query payload", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ content: "ok" }));
    const model = new KryosModel("http://example");
    await model.query("hi", { max_tokens: 12, temperature: 0.4, model: "x" });
    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string) as { prompt: string; max_tokens: number; temperature: number; model: string };
    expect(body.max_tokens).toBe(12);
    expect(body.model).toBe("x");
  });

  it("lists models", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ models: [{ id: "m1", name: "Model 1", active: true }] }));
    const model = new KryosModel();
    const models = await model.listModels();
    expect(models[0].id).toBe("m1");
  });

  it("throws on model API failure", async () => {
    fetchMock.mockResolvedValueOnce(new Response("boom", { status: 500 }));
    const model = new KryosModel("http://example");
    await expect(model.query("hi")).rejects.toThrow();
  });
});
