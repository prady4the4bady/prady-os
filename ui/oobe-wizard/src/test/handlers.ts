import { http, HttpResponse } from "msw";

export const handlers = [
  http.get("http://localhost:8000/api/models/list", () =>
    HttpResponse.json({ models: [{ id: "llama3-8b" }, { id: "phi-4" }] })
  ),
  http.post("http://localhost:8000/api/models/load", () =>
    HttpResponse.json({ status: "loading" })
  ),
  http.post("http://localhost:8001/api/soul/init", () => HttpResponse.json({ ok: true })),
  http.post("http://localhost:8099/api/oobe/complete", () => HttpResponse.json({ status: "ok" })),
];