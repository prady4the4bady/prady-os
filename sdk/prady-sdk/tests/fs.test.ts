import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { KryosFS } from "../src/fs.js";

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

describe("KryosFS", () => {
  it("stores the app name", () => {
    const fs = new KryosFS("demo");
    expect(fs).toBeDefined();
  });

  it("reads file content", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ content: "hello" }));
    const fs = new KryosFS("demo", "http://example");
    const result = await fs.read("notes.txt");
    expect(result).toBe("hello");
  });

  it("writes file content", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ written: true }));
    const fs = new KryosFS("demo", "http://example");
    await fs.write("notes.txt", "hello");
    expect(JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string)).toMatchObject({ app: "demo", path: "notes.txt" });
  });

  it("lists entries as names", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ entries: [{ name: "a.txt" }, { name: "b.txt" }] }));
    const fs = new KryosFS("demo", "http://example");
    const result = await fs.list("/");
    expect(result).toEqual(["a.txt", "b.txt"]);
  });

  it("deletes files", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ deleted: true }));
    const fs = new KryosFS("demo", "http://example");
    await fs.delete("a.txt");
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/sdk/fs/delete"), expect.objectContaining({ method: "DELETE" }));
  });

  it("throws on read failure", async () => {
    fetchMock.mockResolvedValueOnce(new Response("boom", { status: 500 }));
    const fs = new KryosFS("demo", "http://example");
    await expect(fs.read("notes.txt")).rejects.toThrow();
  });
});
