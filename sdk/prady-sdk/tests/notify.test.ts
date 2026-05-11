import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { KryosNotify } from "../src/notify.js";

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

describe("KryosNotify", () => {
  it("uses the default api base", () => {
    const notify = new KryosNotify();
    expect(notify).toBeDefined();
  });

  it("posts with default severity info", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true }));
    const notify = new KryosNotify("http://example");
    await notify.send("Title", "Body");
    const payload = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string) as { severity: string; source: string };
    expect(payload.severity).toBe("info");
    expect(payload.source).toBe("sdk-app");
  });

  it("posts with custom severity", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true }));
    const notify = new KryosNotify("http://example");
    await notify.send("Title", "Body", "critical");
    const payload = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string) as { severity: string };
    expect(payload.severity).toBe("critical");
  });

  it("sends the title and body", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true }));
    const notify = new KryosNotify("http://example");
    await notify.send("Title", "Body");
    const payload = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string) as { title: string; body: string };
    expect(payload.title).toBe("Title");
    expect(payload.body).toBe("Body");
  });

  it("throws on notify failure", async () => {
    fetchMock.mockResolvedValueOnce(new Response("boom", { status: 500 }));
    const notify = new KryosNotify("http://example");
    await expect(notify.send("Title", "Body")).rejects.toThrow();
  });
});
