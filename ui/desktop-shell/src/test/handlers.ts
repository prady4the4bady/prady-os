import { http, HttpResponse } from "msw";

function readStringValue(value: unknown, fallback: string): string {
  return typeof value === "string" ? value : fallback;
}

const mockPackageCatalog = [
  {
    package_id: "notification-center",
    name: "Notification Center",
    version: "1.0.0",
    type: "panel",
    description: "Unified alert center for agent, system, and scheduler events.",
    entrypoint: "http://localhost:8100",
    service_name: "notification-center",
    dependencies: [],
    permissions: ["notifications:read", "notifications:write"],
    healthcheck_path: "/api/notifications/health",
    source: "catalog",
    status: "enabled",
    installed_at: new Date(Date.now() - 3_600_000).toISOString(),
    updated_at: new Date(Date.now() - 3_600_000).toISOString(),
  },
  {
    package_id: "task-history",
    name: "Task History",
    version: "1.0.0",
    type: "panel",
    description: "Audit log browser and replay surface for completed tasks.",
    entrypoint: "http://localhost:8100",
    service_name: "task-history",
    dependencies: [],
    permissions: ["audit:read"],
    healthcheck_path: "/api/audit/health",
    source: "catalog",
    status: "installed",
    installed_at: new Date(Date.now() - 7_200_000).toISOString(),
    updated_at: new Date(Date.now() - 7_200_000).toISOString(),
  },
  {
    package_id: "model-hub",
    name: "Model Hub",
    version: "1.0.0",
    type: "panel",
    description: "Model lifecycle management, pull jobs, and activation controls.",
    entrypoint: "http://localhost:8113",
    service_name: "model-hub",
    dependencies: [],
    permissions: ["models:read", "models:write"],
    healthcheck_path: "/health",
    source: "catalog",
    status: "enabled",
    installed_at: new Date(Date.now() - 10_800_000).toISOString(),
    updated_at: new Date(Date.now() - 10_800_000).toISOString(),
  },
  {
    package_id: "persona-manager",
    name: "Persona Manager",
    version: "1.0.0",
    type: "panel",
    description: "Persona lifecycle, activation, memory policy, and prompt tuning.",
    entrypoint: "http://localhost:8114",
    service_name: "persona-manager",
    dependencies: ["model-hub"],
    permissions: ["persona:read", "persona:write"],
    healthcheck_path: "/health",
    source: "catalog",
    status: "disabled",
    installed_at: new Date(Date.now() - 86_400_000).toISOString(),
    updated_at: new Date(Date.now() - 86_400_000).toISOString(),
  },
  {
    package_id: "watchdog-center",
    name: "Watchdog Center",
    version: "1.0.0",
    type: "panel",
    description: "Service health monitoring, incidents, and remediation controls.",
    entrypoint: "http://localhost:8115",
    service_name: "watchdog-center",
    dependencies: [],
    permissions: ["watchdog:read", "watchdog:execute"],
    healthcheck_path: "/health",
    source: "catalog",
    status: "enabled",
    installed_at: new Date(Date.now() - 43_200_000).toISOString(),
    updated_at: new Date(Date.now() - 43_200_000).toISOString(),
  },
  {
    package_id: "spotlight-launcher",
    name: "Spotlight Launcher",
    version: "1.0.0",
    type: "panel",
    description: "Global launcher for apps, actions, and semantic lookup.",
    entrypoint: "http://localhost:3000",
    service_name: "spotlight-launcher",
    dependencies: [],
    permissions: ["launcher:read"],
    healthcheck_path: null,
    source: "catalog",
    status: "available",
    installed_at: null,
    updated_at: new Date(Date.now() - 21_600_000).toISOString(),
  },
];

const mockPackageOperations = [
  {
    id: "op-1",
    package_id: "model-hub",
    operation: "update",
    status: "success",
    message: "Updated to latest catalog version",
    started_at: new Date(Date.now() - 120_000).toISOString(),
    completed_at: new Date(Date.now() - 115_000).toISOString(),
    created_at: new Date(Date.now() - 120_000).toISOString(),
  },
  {
    id: "op-2",
    package_id: "persona-manager",
    operation: "disable",
    status: "success",
    message: "Service disabled",
    started_at: new Date(Date.now() - 300_000).toISOString(),
    completed_at: new Date(Date.now() - 299_000).toISOString(),
    created_at: new Date(Date.now() - 300_000).toISOString(),
  },
];

export const handlers = [
  http.get("http://localhost:8099/api/oobe/status", () => {
    return HttpResponse.json({ complete: true });
  }),
  http.get("/api/oobe/status", () => {
    return HttpResponse.json({ complete: true });
  }),
  http.get("/api/system/about", () => {
    return HttpResponse.json({
      name: "Prady OS",
      version: "1.0.0",
      channel: "stable",
      build: "phase-38",
    });
  }),
  http.get("/api/system/health", () => {
    return HttpResponse.json({
      status: "healthy",
      checks: {
        oobe: "ok",
        hardware: "ok",
        sdk_registry: "ok",
      },
    });
  }),
  http.post("/swarm/start", async ({ request }) => {
    const body = (await request.json()) as { goal: string };
    return HttpResponse.json({
      swarm_id: "swarm-test-1",
      goal: body.goal,
      max_agents: 5,
      model_id: "lumyn-agent",
      status: "running",
    });
  }),
  http.get("/swarm/status", () => {
    return HttpResponse.json({ swarms: [] });
  }),
  http.get("/swarm/:id/result", () => {
    return HttpResponse.json({
      swarm_id: "swarm-test-1",
      status: "done",
      merged_result: { combined_reasoning: "Agent A finished task" },
    });
  }),
  http.post("/models/pull", async ({ request }) => {
    const body = (await request.json()) as { source: string };
    const completePayload = {
      model_id: `local-${body.source}`,
      status: "ready",
      progress: 100,
    };
    const payload = [
      `event: status\ndata: ${JSON.stringify({ stage: "downloading", progress: 35 })}\n\n`,
      `event: status\ndata: ${JSON.stringify({ stage: "quantizing", progress: 70 })}\n\n`,
      `event: complete\ndata: ${JSON.stringify(completePayload)}\n\n`,
    ].join("");
    return new HttpResponse(payload, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    });
  }),
  http.get("/models/list", () =>
    HttpResponse.json([
      {
        model_id: "local-lumyn-agent",
        name: "lumyn-agent.gguf",
        source: "hf://Qwen/Qwen3-30B-A3B",
        file_path: "/models/lumyn-agent.gguf",
        sha256: "abc",
        quantization: "Q4_K_M",
        size_gb: 5.5,
        pulled_at: new Date().toISOString(),
        status: "ready",
        benchmark_score: 0.44,
        tokens_per_sec: 72.1,
      },
    ])
  ),
  http.delete("/models/:id", () => HttpResponse.json({ ok: true })),
  http.post("/models/:id/activate", () => HttpResponse.json({ ok: true })),
  http.post("/gateway/models/:id/activate", () => HttpResponse.json({ ok: true })),
  http.get("/gateway/models/loaded", () => HttpResponse.json({ loaded_models: ["lumyn-agent"], vyrex_enabled: true })),
  http.get("/screen/latest", () => {
    return HttpResponse.json({ imageBase64: "", ocrText: [] });
  }),

  // --- Lumyn skill endpoints ---
  http.get("http://localhost:8000/lumyn/skills", () =>
    HttpResponse.json({
      skills: [
        {
          skill_id: "skill-test-1",
          name: "test_skill",
          description: "A test skill",
          status: "active",
          elite: false,
          use_count: 5,
          success_rate: 0.8,
          avg_latency_ms: 120,
          last_used_at: Date.now() / 1000,
        },
      ],
      total: 1,
    })
  ),

  http.post("http://localhost:8000/lumyn/skill/acquire", async ({ request }) => {
    const body = (await request.json()) as { task_description: string };
    return HttpResponse.json({
      skill: {
        skill_id: "skill-acquired-1",
        name: "acquired_skill",
        description: `Skill for: ${body.task_description}`,
        status: "active",
        elite: false,
        use_count: 0,
        success_rate: 0,
        avg_latency_ms: 0,
        last_used_at: null,
      },
    });
  }),

  http.post("http://localhost:8000/lumyn/skill/execute", async ({ request }) => {
    const body = (await request.json()) as { skill_id: string };
    return HttpResponse.json({
      result: {
        skill_id: body.skill_id,
        success: true,
        output: "Executed successfully",
        error: null,
        latency_ms: 100,
      },
    });
  }),

  http.delete("http://localhost:8000/lumyn/skills/:id", () => HttpResponse.json({ deleted: true })),

  // --- Soul endpoints ---
  http.get("http://localhost:8000/soul/:userId", ({ params }) => {
    const userId = params.userId as string;
    return HttpResponse.json({
      user_id: userId,
      fields: {
        name: "Kryos User",
        personality: "curious and helpful",
        communication_style: "friendly",
        preferred_model: "lumyn-agent",
        memory_summary: [],
      },
    });
  }),

  http.put("http://localhost:8000/soul/:userId", async ({ request, params }) => {
    const userId = params.userId as string;
    const body = (await request.json()) as { fields: Record<string, unknown> };
    return HttpResponse.json({ user_id: userId, fields: body.fields });
  }),

  http.post("http://localhost:8000/soul/:userId/memory", () => HttpResponse.json({ ok: true })),

  // --- AgentNet endpoints ---
  http.get("/agentnet/identities", () =>
    HttpResponse.json({
      identities: { "lumyn-bridge": "-----BEGIN PUBLIC KEY-----\nMOCK\n-----END PUBLIC KEY-----" },
      total: 1,
    })
  ),

  http.post("/agentnet/verify", async ({ request }) => {
    const body = (await request.json()) as { from_agent: string };
    return HttpResponse.json({ valid: true, from_agent: body.from_agent });
  }),

  // --- Phase 8: Screen / Input endpoints ---
  http.get("http://localhost:8000/input/screenshot", () =>
    HttpResponse.json({ image_b64: "iVBORw0KGgo=", format: "png", ocr_text: [] })
  ),
  http.post("http://localhost:8000/input/action", () =>
    HttpResponse.json({ success: true, action: "click", params: { x: 100, y: 200 } })
  ),
  http.get("http://localhost:8000/vision/status", () =>
    HttpResponse.json({ ready: true, active_model: "llava", registered_models: ["llava"] })
  ),
  http.post("http://localhost:8000/vision/capture", () =>
    HttpResponse.json({ image_b64: "iVBORw0KGgo=" })
  ),

  // --- Phase 8: Task executor endpoints ---
  http.post("http://localhost:8000/task/execute", () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            'data: {"type":"step","task_id":"test-task","step":1,"action":"done","params":{},"reasoning":"Goal complete","success":true}\n\n'
          )
        );
        controller.enqueue(
          encoder.encode(
            'data: {"type":"result","task_id":"test-task","goal":"test","success":true,"summary":"Done","steps_taken":1}\n\n'
          )
        );
        controller.close();
      },
    });
    return new HttpResponse(stream, {
      headers: { "Content-Type": "text/event-stream" },
    });
  }),
  http.delete("http://localhost:8000/task/:taskId", () =>
    HttpResponse.json({ task_id: "test-task", aborted: true })
  ),
  http.get("http://localhost:8000/task/history", () =>
    HttpResponse.json({ history: [], total: 0 })
  ),

  // --- Phase 8: Process manager endpoints ---
  http.get("http://localhost:8000/processes/list", () =>
    HttpResponse.json({
      processes: [
        { pid: 1234, name: "firefox", cpu_percent: 5.2, memory_mb: 256, status: "running" },
      ],
    })
  ),
  http.post("http://localhost:8000/processes/launch", () =>
    HttpResponse.json({
      pid: 9999,
      name: "firefox",
      binary: "/usr/bin/firefox",
      args: [],
      started_at: Date.now() / 1000,
    })
  ),
  http.delete("http://localhost:8000/processes/:pid", () =>
    HttpResponse.json({ success: true, pid: 1234 })
  ),
  http.get("http://localhost:8000/processes/windows", () =>
    HttpResponse.json({
      windows: [
        { pid: 1234, title: "Firefox", x: 0, y: 0, width: 1200, height: 800, focused: true },
      ],
    })
  ),

  // --- Phase 8: Memory store endpoints ---
  http.post("http://localhost:8000/memory/store", () =>
    HttpResponse.json({
      id: "mem-1",
      agent_id: "ui-user",
      content: "test",
      tags: [],
      created_at: Date.now() / 1000,
      access_count: 0,
    })
  ),
  http.post("http://localhost:8000/memory/search", () =>
    HttpResponse.json({
      results: [
        {
          id: "mem-1",
          agent_id: "ui-user",
          content: "test memory",
          tags: ["test"],
          created_at: Date.now() / 1000,
          access_count: 1,
        },
      ],
      count: 1,
    })
  ),
  http.delete("http://localhost:8000/memory/:id", () =>
    HttpResponse.json({ success: true, id: "mem-1" })
  ),
  http.get("http://localhost:8000/memory/stats", () =>
    HttpResponse.json({
      total_entries: 5,
      db_size_mb: 0.001,
      agents: ["ui-user", "task-executor-default"],
    })
  ),
  // Phase 9 — Watchdog (legacy; kept for old tests)
  http.get("http://localhost:8000/api/watchdog/status", () =>
    HttpResponse.json({ services: [{ name: "kryos-swarm", status: "healthy", uptime: 3600 }] })
  ),
  http.post("http://localhost:8000/api/watchdog/restart/:service", () =>
    HttpResponse.json({ restarted: true })
  ),
  // Phase 25 — Watchdog v2 (relative paths, proxied through agent-runtime)
  http.get("/api/watchdog/health", () =>
    HttpResponse.json({ status: "ok", service: "watchdog", port: 8115 })
  ),
  http.get("/api/watchdog/services", () =>
    HttpResponse.json({
      total: 7,
      services: [
        { name: "agent-runtime",    status: "healthy",  last_check_at: new Date(Date.now() - 8000).toISOString(),  last_ok_at: new Date(Date.now() - 8000).toISOString(),  last_error: null,                               consecutive_failures: 0, latency_ms: 42,   check_count: 10, updated_at: new Date(Date.now() - 8000).toISOString() },
        { name: "notification-bus", status: "healthy",  last_check_at: new Date(Date.now() - 9000).toISOString(),  last_ok_at: new Date(Date.now() - 9000).toISOString(),  last_error: null,                               consecutive_failures: 0, latency_ms: 38,   check_count: 10, updated_at: new Date(Date.now() - 9000).toISOString() },
        { name: "audit-log",        status: "healthy",  last_check_at: new Date(Date.now() - 10000).toISOString(), last_ok_at: new Date(Date.now() - 10000).toISOString(), last_error: null,                               consecutive_failures: 0, latency_ms: 55,   check_count: 10, updated_at: new Date(Date.now() - 10000).toISOString() },
        { name: "model-hub",        status: "degraded", last_check_at: new Date(Date.now() - 11000).toISOString(), last_ok_at: new Date(Date.now() - 40000).toISOString(), last_error: "connection timeout",               consecutive_failures: 2, latency_ms: 2400, check_count: 10, updated_at: new Date(Date.now() - 11000).toISOString() },
        { name: "persona-service",  status: "healthy",  last_check_at: new Date(Date.now() - 12000).toISOString(), last_ok_at: new Date(Date.now() - 12000).toISOString(), last_error: null,                               consecutive_failures: 0, latency_ms: 29,   check_count: 10, updated_at: new Date(Date.now() - 12000).toISOString() },
        { name: "task-scheduler",   status: "healthy",  last_check_at: new Date(Date.now() - 13000).toISOString(), last_ok_at: new Date(Date.now() - 13000).toISOString(), last_error: null,                               consecutive_failures: 0, latency_ms: 61,   check_count: 10, updated_at: new Date(Date.now() - 13000).toISOString() },
        { name: "memory-service",   status: "healthy",  last_check_at: new Date(Date.now() - 14000).toISOString(), last_ok_at: new Date(Date.now() - 14000).toISOString(), last_error: null,                               consecutive_failures: 0, latency_ms: 47,   check_count: 10, updated_at: new Date(Date.now() - 14000).toISOString() },
      ],
    })
  ),
  http.get("/api/watchdog/services/:name", ({ params }) =>
    HttpResponse.json({
      name: params["name"],
      status: "healthy",
      last_check_at: new Date(Date.now() - 8000).toISOString(),
      last_ok_at:    new Date(Date.now() - 8000).toISOString(),
      last_error: null,
      consecutive_failures: 0,
      latency_ms: 42,
      check_count: 5,
      updated_at: new Date(Date.now() - 8000).toISOString(),
    })
  ),
  http.post("/api/watchdog/services/:name/check", ({ params }) =>
    HttpResponse.json({
      name: params["name"],
      status: "healthy",
      last_check_at: new Date().toISOString(),
      last_ok_at:    new Date().toISOString(),
      last_error: null,
      consecutive_failures: 0,
      latency_ms: 38,
      check_count: 6,
      updated_at: new Date().toISOString(),
    })
  ),
  http.post("/api/watchdog/services/:name/restart", ({ params }) =>
    HttpResponse.json({
      ok: true,
      service: params["name"],
      unit: `kryos-${String(params["name"])}.service`,
      message: "restart command sent",
    })
  ),
  http.get("/api/watchdog/incidents", () =>
    HttpResponse.json({
      total: 2,
      limit: 20,
      offset: 0,
      incidents: [
        {
          id: "inc-1",
          service_name: "model-hub",
          status: "degraded",
          started_at: new Date(Date.now() - 300000).toISOString(),
          resolved_at: null,
          message: "model-hub entered degraded state: connection timeout",
          created_at: new Date(Date.now() - 300000).toISOString(),
        },
        {
          id: "inc-2",
          service_name: "model-hub",
          status: "down",
          started_at: new Date(Date.now() - 3600000).toISOString(),
          resolved_at: new Date(Date.now() - 3400000).toISOString(),
          message: "model-hub entered down state: connection refused",
          created_at: new Date(Date.now() - 3600000).toISOString(),
        },
      ],
    })
  ),
  http.get("/api/watchdog/incidents/stats", () =>
    HttpResponse.json({
      total: 2,
      open: 1,
      resolved: 1,
      by_service: { "model-hub": 2 },
      by_status:  { degraded: 1, down: 1 },
    })
  ),
  http.post("/api/watchdog/scan", () =>
    HttpResponse.json({
      scanned: 7,
      services: [
        { name: "agent-runtime",    status: "healthy"  },
        { name: "notification-bus", status: "healthy"  },
        { name: "audit-log",        status: "healthy"  },
        { name: "model-hub",        status: "degraded" },
        { name: "persona-service",  status: "healthy"  },
        { name: "task-scheduler",   status: "healthy"  },
        { name: "memory-service",   status: "healthy"  },
      ],
    })
  ),
  // Phase 9 — Loop runner
  http.get("http://localhost:8000/api/loop/status", () =>
    HttpResponse.json({ running: true, paused: false, tasks_processed: 0 })
  ),
  http.post("http://localhost:8000/api/loop/pause", () =>
    HttpResponse.json({ paused: true })
  ),
  http.post("http://localhost:8000/api/loop/resume", () =>
    HttpResponse.json({ paused: false })
  ),
  // Phase 9 — Task queue
  http.post("http://localhost:8000/api/queue/push", () =>
    HttpResponse.json({ task_id: "q-1", status: "pending" })
  ),
  http.get("http://localhost:8000/api/queue/list", () =>
    HttpResponse.json({ tasks: [], total: 0 })
  ),
  // Phase 9 — Models
  http.post("http://localhost:8000/api/models/load", () =>
    HttpResponse.json({ model_id: "test-model", status: "loading" })
  ),
  http.get("http://localhost:8000/api/models/list", () =>
    HttpResponse.json({ models: [{ id: "lumyn-agent", name: "Lumyn Agent", status: "ready" }] })
  ),
  // Phase 9 — Vyrex policy
  http.post("http://localhost:8000/api/vyrex/policy", () =>
    HttpResponse.json({ ok: true })
  ),
  // Phase 9 — Task execute (Spotlight AI Tasks)
  http.post("http://localhost:8000/task/execute", () =>
    HttpResponse.json({ result: "Task completed.", task_id: "t-1" })
  ),
  // Phase 9 — Memory store (NotificationCentre persistence)
  http.post("http://localhost:8000/api/memory/store", () =>
    HttpResponse.json({ id: "notif-1", stored: true })
  ),
  // Phase 10 — OOBE status
  http.get("http://localhost:8099/api/oobe/status", () =>
    HttpResponse.json({ complete: true })
  ),

  // Phase 11 — Agent Runtime (http://localhost:8100)
  http.get("http://localhost:8100/agents/", () =>
    HttpResponse.json([
      {
        agent_id: "agent-test-1",
        model_id: "phi3",
        policy_id: "task-executor",
        pid: 12345,
        status: "running",
        started_at: Date.now() / 1000,
        stopped_at: null,
        exit_code: null,
      },
    ])
  ),
  http.post("http://localhost:8100/agents/spawn", async ({ request }) => {
    const body = (await request.json()) as { model_id: string; policy_id: string };
    return HttpResponse.json(
      {
        agent_id: "agent-spawned-1",
        model_id: body.model_id,
        policy_id: body.policy_id,
        pid: 99999,
        status: "running",
        started_at: Date.now() / 1000,
        stopped_at: null,
        exit_code: null,
      },
      { status: 201 }
    );
  }),
  http.delete("http://localhost:8100/agents/:agentId", ({ params }) =>
    HttpResponse.json({
      agent_id: params.agentId as string,
      model_id: "phi3",
      policy_id: "task-executor",
      pid: 12345,
      status: "stopped",
      started_at: Date.now() / 1000,
      stopped_at: Date.now() / 1000,
      exit_code: 0,
    })
  ),
  http.post("http://localhost:8100/agents/:agentId/prompt", ({ params }) => {
    const agentId = params.agentId as string;
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        const tokens = ["Hello", " from", " agent", " ", agentId.slice(0, 8), "!"];
        for (const token of tokens) {
          controller.enqueue(
            encoder.encode(
              `data: ${JSON.stringify({ token, agent_id: agentId })}\n\n`
            )
          );
        }
        controller.enqueue(
          encoder.encode(
            `data: ${JSON.stringify({ done: true, agent_id: agentId })}\n\n`
          )
        );
        controller.close();
      },
    });
    return new HttpResponse(stream, {
      headers: { "Content-Type": "text/event-stream" },
    });
  }),
  http.get("http://localhost:8100/health", () =>
    HttpResponse.json({ status: "ok", agents: 1 })
  ),
  http.post("http://localhost:8100/agents/active-model", async ({ request }) => {
    const body = (await request.json()) as { model_id: string };
    return HttpResponse.json({ ok: true, active_model: body.model_id });
  }),
  http.get("http://localhost:8101/automation/screen/info", () =>
    HttpResponse.json({ width: 1920, height: 1080, scale: 1 })
  ),
  http.get("http://localhost:8101/automation/stats", () =>
    HttpResponse.json({ actions_last_minute: 0, rate_limit: 120 })
  ),
  http.post("http://localhost:8101/automation/screenshot", () =>
    HttpResponse.json({ image: "base64mock==", width: 1920, height: 1080 })
  ),
  http.post("http://localhost:8101/automation/mouse/move", () =>
    HttpResponse.json({ ok: true })
  ),
  http.post("http://localhost:8101/automation/keyboard/type", () =>
    HttpResponse.json({ ok: true })
  ),
  http.post("http://localhost:8101/automation/vision-verify", () =>
    HttpResponse.json({ verified: true, confidence: 0.97, diff_regions: [] })
  ),
  http.post("http://localhost:8102/lumyn/task", async ({ request }) => {
    const body = (await request.json()) as { task: string; model_id: string };
    return HttpResponse.json({
      task_id: "lumyn-task-1",
      status: "done",
      backend: "lumyn-agent",
      result: { output: `Executed: ${body.task}`, model: body.model_id },
    });
  }),
  http.get("http://localhost:8102/lumyn/status", () =>
    HttpResponse.json({
      tasks: [
        {
          task_id: "lumyn-task-1",
          status: "done",
          task: "Open browser",
          model_id: "lumyn-default",
        },
      ],
      memory_summary: { skills_count: 1, skills: ["default.yaml"], models_registered: 2 },
    })
  ),
  http.post("http://localhost:8102/lumyn/model/pull", async ({ request }) => {
    const body = (await request.json()) as { source: string; url: string };
    return HttpResponse.json({
      ok: true,
      model: {
        id: "mock-model",
        source: body.source,
        url: body.url,
        path: "/models/mock-model",
        status: "ready",
        size_bytes: 1048576,
      },
    });
  }),
  http.get("http://localhost:8102/lumyn/models", () =>
    HttpResponse.json({
      models: [
        {
          id: "lumyn-default",
          source: "ollama",
          url: "ollama://lumyn-default",
          status: "ready",
          size_bytes: 0,
        },
        {
          id: "mock-model",
          source: "huggingface",
          url: "https://huggingface.co/mock/model",
          status: "ready",
          size_bytes: 1048576,
        },
      ],
      default_model: "lumyn-default",
    })
  ),
  http.delete("http://localhost:8102/lumyn/models/:modelId", ({ params }) =>
    HttpResponse.json({ ok: true, deleted: params.modelId as string })
  ),
  http.post("http://localhost:8102/lumyn/skills", () =>
    HttpResponse.json({ skills: ["default.yaml"] })
  ),
  http.post("http://localhost:8102/lumyn/default-model", async ({ request }) => {
    const body = (await request.json()) as { model_id: string };
    return HttpResponse.json({ ok: true, default_model: body.model_id });
  }),

  // ── wayland-mcp (port 8103) ───────────────────────────────────────────────
  http.post("http://localhost:8103/wayland/move", () =>
    HttpResponse.json({ ok: true, backend: "wayland" })
  ),
  http.post("http://localhost:8103/wayland/click", () =>
    HttpResponse.json({ ok: true, backend: "wayland" })
  ),
  http.post("http://localhost:8103/wayland/type", () =>
    HttpResponse.json({ ok: true, backend: "wayland" })
  ),
  http.post("http://localhost:8103/wayland/screenshot", () =>
    HttpResponse.json({ image: "", width: 1920, height: 1080, backend: "grim" })
  ),
  http.get("http://localhost:8103/wayland/windows", () =>
    HttpResponse.json({
      windows: [{ id: "1", name: "Firefox", app_id: "firefox", focused: true }],
      backend: "swaymsg",
    })
  ),
  http.post("http://localhost:8103/wayland/focus", () =>
    HttpResponse.json({ ok: true, backend: "swaymsg" })
  ),
  http.get("http://localhost:8103/wayland/session-type", () =>
    HttpResponse.json({ type: "wayland" })
  ),

  // ── automation route-input (port 8101) ────────────────────────────────────
  http.post("http://localhost:8101/automation/route-input", async ({ request }) => {
    await request.json();
    return HttpResponse.json({ backend: "wayland", result: { ok: true }, latency_ms: 12 });
  }),

  // ── swarm-coordinator (port 8104) ─────────────────────────────────────────
  http.post("http://localhost:8104/swarm/task", async ({ request }) => {
    const body = (await request.json()) as { description: string; max_agents?: number };
    return HttpResponse.json(
      { task_id: "test-task-1", status: "running", subtask_count: body.max_agents ?? 3 },
      { status: 202 }
    );
  }),
  http.get("http://localhost:8104/swarm/tasks", () =>
    HttpResponse.json({
      tasks: [
        {
          id: "test-task-1",
          description: "Example swarm task",
          status: "done",
          created_at: Date.now() / 1000,
        },
      ],
      total: 1,
    })
  ),
  http.get("http://localhost:8104/swarm/task/:taskId", ({ params }) =>
    HttpResponse.json({
      id: params.taskId as string,
      description: "Example swarm task",
      max_agents: 3,
      subtasks: [],
      status: "done",
      created_at: Date.now() / 1000,
      completed_at: Date.now() / 1000,
    })
  ),
  http.delete("http://localhost:8104/swarm/task/:taskId", ({ params }) =>
    HttpResponse.json({ ok: true, task_id: params.taskId as string })
  ),
  http.get("http://localhost:8104/swarm/agents", () =>
    HttpResponse.json({ agents: [], count: 0 })
  ),
  http.get("http://localhost:8104/swarm/graph/:taskId", ({ params }) =>
    HttpResponse.json({
      nodes: [
        { id: params.taskId as string, label: "Main task", status: "done", depth: 0, index_in_row: 0 },
        { id: "sub-1", label: "Subtask A", status: "done", depth: 1, index_in_row: 0, agent_id: "agent-0", result: "ok" },
        { id: "sub-2", label: "Subtask B", status: "done", depth: 1, index_in_row: 1, agent_id: "agent-1", result: "ok" },
      ],
      edges: [
        { from: params.taskId as string, to: "sub-1" },
        { from: params.taskId as string, to: "sub-2" },
      ],
    })
  ),

  // ── vyrex-proxy (port 8105) ────────────────────────────────────────────
  http.post("http://localhost:8105/proxy/generate", () =>
    HttpResponse.json({ model: "llava", response: "YES", done: true, prompt_eval_count: 10, eval_count: 1 })
  ),
  http.post("http://localhost:8105/proxy/chat", () =>
    HttpResponse.json({ model: "llava", message: { role: "assistant", content: "Hello" }, done: true })
  ),
  http.get("http://localhost:8105/proxy/models", () =>
    HttpResponse.json({ models: [{ name: "llava", size: 4_000_000_000, status: "ready" }] })
  ),
  http.post("http://localhost:8105/proxy/models/pull", () =>
    HttpResponse.json({ status: "success" })
  ),
  http.get("http://localhost:8105/proxy/metrics", () =>
    HttpResponse.json({ requests: [], total: 0 })
  ),
  http.get("http://localhost:8105/proxy/metrics/summary", () =>
    HttpResponse.json({
      total_requests: 0,
      avg_latency_ms: 0,
      p95_latency_ms: 0,
      tokens_per_second_avg: 0,
      active_models: [],
      vram_used_mb: 0,
      vram_total_mb: 0,
      queue_depth: 0,
    })
  ),
  http.get("http://localhost:8105/proxy/health", () =>
    HttpResponse.json({ status: "ok", ollama_reachable: true, proxy_version: "1.0.0" })
  ),

  // ── model-hub via agent-runtime /api proxy ───────────────────────────────
  http.post("/api/models/pull", () =>
    HttpResponse.json({ job_id: "job-model-pull-1", status: "queued" })
  ),
  http.get("/api/models/pull/:job_id/progress", ({ params }) => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            `data: ${JSON.stringify({ job_id: params.job_id, status: "downloading", message: "resolving repository", bytes_downloaded: 120, total_bytes: 1000, percent: 12, speed_bps: 1500000 })}\n\n`
          )
        );
        controller.enqueue(
          encoder.encode(
            `data: ${JSON.stringify({ job_id: params.job_id, status: "downloading", message: "downloading model files", bytes_downloaded: 760, total_bytes: 1000, percent: 76, speed_bps: 2800000 })}\n\n`
          )
        );
        controller.enqueue(
          encoder.encode(
            `data: ${JSON.stringify({ job_id: params.job_id, status: "complete", message: "pull complete", bytes_downloaded: 1000, total_bytes: 1000, percent: 100, speed_bps: 0 })}\n\n`
          )
        );
        controller.close();
      },
    });
    return new HttpResponse(stream, {
      headers: { "Content-Type": "text/event-stream" },
    });
  }),
  http.get("/api/models", () =>
    HttpResponse.json({
      total: 3,
      models: [
        {
          id: "m1",
          model_id: "qwen3-30b-a3b-q4",
          source: "huggingface",
          url: "https://huggingface.co/Qwen/Qwen3-30B-A3B",
          quantization: "q4",
          size_bytes: 5480000000,
          path: "/models/qwen3-30b-a3b-q4",
          is_active: true,
          pulled_at: "2026-05-08T01:00:00Z",
          last_used_at: "2026-05-08T02:30:00Z",
          benchmark_tps: 54.2,
          benchmark_latency_ms: 182.5,
        },
        {
          id: "m2",
          model_id: "llama-3-8b-instruct-q8",
          source: "huggingface",
          url: "https://huggingface.co/meta-llama/Meta-Llama-3-8B-Instruct",
          quantization: "q8",
          size_bytes: 8140000000,
          path: "/models/llama-3-8b-instruct-q8",
          is_active: false,
          pulled_at: "2026-05-07T18:00:00Z",
          last_used_at: "2026-05-07T21:20:00Z",
          benchmark_tps: 31.8,
          benchmark_latency_ms: 241.9,
        },
        {
          id: "m3",
          model_id: "deepseek-r1-distill-qwen-7b-f16",
          source: "github",
          url: "https://github.com/example/deepseek-r1-distill-qwen-7b",
          quantization: "f16",
          size_bytes: 13700000000,
          path: "/models/deepseek-r1-distill-qwen-7b-f16",
          is_active: false,
          pulled_at: "2026-05-06T13:00:00Z",
          last_used_at: null,
          benchmark_tps: null,
          benchmark_latency_ms: null,
        },
      ],
    })
  ),
  http.post("/api/models/:model_id/activate", ({ params }) =>
    HttpResponse.json({ ok: true, model_id: params.model_id, path: `/models/${params.model_id}` })
  ),
  http.delete("/api/models/:model_id", ({ params }) =>
    HttpResponse.json({ ok: true, deleted: params.model_id })
  ),
  http.get("/api/models/:model_id/benchmark", ({ params }) =>
    HttpResponse.json({
      model_id: params.model_id,
      tokens_per_second: 48.7,
      latency_ms: 205.4,
    })
  ),
  http.get("/api/models/health", () =>
    HttpResponse.json({ status: "ok", models: 3, jobs: 0 })
  ),
  // legacy aliases used by older UI paths
  http.get("/api/models/list", () =>
    HttpResponse.json({
      models: [
        {
          model_id: "qwen3-30b-a3b-q4",
          size_bytes: 5480000000,
          quantization: "q4",
        },
      ],
      total: 1,
    })
  ),
  http.post("/api/models/set-default", async ({ request }) => {
    const body = (await request.json()) as { model_id?: string; alias?: string };
    return HttpResponse.json({ ok: true, model_id: body.model_id ?? body.alias ?? "unknown" });
  }),
  http.get("/api/models/config", () => HttpResponse.json({ default_model: "qwen3-30b-a3b-q4" })),

  // ── memory-service via agent-runtime /api proxy ─────────────────────────
  http.post("/api/memory", () =>
    HttpResponse.json({ id: "mem-1", created_at: "2026-05-08T00:00:00Z" })
  ),
  http.get("/api/memory/search", () =>
    HttpResponse.json({
      results: [
        {
          id: "mem-1",
          type: "task",
          content: "test memory",
          tags: [],
          importance: 0.5,
          access_count: 1,
          created_at: "2026-05-08T00:00:00Z",
          score: 0.9,
        },
      ],
    })
  ),
  http.get("/api/memory/:id", () =>
    HttpResponse.json({
      id: "mem-1",
      type: "task",
      content: "test memory",
      tags: [],
      importance: 0.5,
      access_count: 1,
      created_at: "2026-05-08T00:00:00Z",
      score: 0.9,
    })
  ),
  http.patch("/api/memory/:id", () => HttpResponse.json({ ok: true })),
  http.delete("/api/memory/:id", () => new HttpResponse(null, { status: 200 })),
  http.post("/api/memory/ingest-task", () => HttpResponse.json({ id: "mem-2" })),
  http.post("/api/session/start", () => HttpResponse.json({ session_id: "sess-1" })),
  http.post("/api/session/end", () => HttpResponse.json({ ok: true })),
  http.get("/api/session/list", () => HttpResponse.json({ sessions: [] })),
  http.get("/api/context/build", () => HttpResponse.json({ context: "## User Memory Context\n- test" })),

  // ── persona-service via agent-runtime /api proxy ───────────────────────
  http.post("/api/persona", async ({ request }) => {
    const body = (await request.json()) as {
      name: string;
      system_prompt: string;
      model_id: string;
      memory_scope: string;
    };
    return HttpResponse.json({
      id: "persona-1",
      name: body.name,
      system_prompt: body.system_prompt,
      model_id: body.model_id,
      memory_scope: body.memory_scope,
      is_active: false,
      created_at: "2026-05-08T00:00:00Z",
      updated_at: "2026-05-08T00:00:00Z",
    });
  }),
  http.get("/api/persona", () =>
    HttpResponse.json({
      personas: [
        {
          id: "persona-1",
          name: "Default Assistant",
          system_prompt: "You are helpful and concise.",
          model_id: "llama3:8b",
          memory_scope: "default",
          is_active: true,
          created_at: "2026-05-08T00:00:00Z",
          updated_at: "2026-05-08T00:00:00Z",
        },
      ],
    })
  ),
  http.get("/api/persona/active", () =>
    HttpResponse.json({
      active: {
        id: "persona-1",
        name: "Default Assistant",
        system_prompt: "You are helpful and concise.",
        model_id: "llama3:8b",
        memory_scope: "default",
        is_active: true,
        created_at: "2026-05-08T00:00:00Z",
        updated_at: "2026-05-08T00:00:00Z",
      },
    })
  ),
  http.get("/api/persona/:id", ({ params }) =>
    HttpResponse.json({
      id: params.id as string,
      name: "Persona",
      system_prompt: "Prompt",
      model_id: "llama3:8b",
      memory_scope: "default",
      is_active: false,
      created_at: "2026-05-08T00:00:00Z",
      updated_at: "2026-05-08T00:00:00Z",
    })
  ),
  http.patch("/api/persona/:id", async ({ params, request }) => {
    const body = (await request.json()) as {
      name?: string;
      system_prompt?: string;
      model_id?: string;
      memory_scope?: string;
    };
    return HttpResponse.json({
      id: params.id as string,
      name: body.name || "Persona",
      system_prompt: body.system_prompt || "Prompt",
      model_id: body.model_id || "llama3:8b",
      memory_scope: body.memory_scope || "default",
      is_active: false,
      created_at: "2026-05-08T00:00:00Z",
      updated_at: "2026-05-08T00:00:00Z",
    });
  }),
  http.delete("/api/persona/:id", ({ params }) => HttpResponse.json({ ok: true, deleted: params.id as string })),
  http.post("/api/persona/:id/activate", ({ params }) =>
    HttpResponse.json({
      ok: true,
      active: {
        id: params.id as string,
        name: "Persona",
        system_prompt: "Prompt",
        model_id: "llama3:8b",
        memory_scope: "default",
        is_active: true,
        created_at: "2026-05-08T00:00:00Z",
        updated_at: "2026-05-08T00:00:00Z",
      },
    })
  ),

  // ── Phase 24 persona manager routes (/api/personas*) ────────────────────
  http.get("/api/personas", () =>
    HttpResponse.json({
      personas: [
        {
          id: "persona-24-1",
          name: "Analyst",
          avatar_color: "#0A84FF",
          system_prompt: "You are analytical and concise.",
          preferred_model_id: "qwen3-30b-a3b-q4",
          memory_policy: "balanced",
          tags: ["work", "reports"],
          compressed_summary: null,
          archived: false,
          created_at: "2026-05-08T00:00:00Z",
          updated_at: "2026-05-08T00:00:00Z",
          last_activated_at: "2026-05-08T00:00:00Z",
          activation_count: 3,
          is_active: true,
        },
        {
          id: "persona-24-2",
          name: "Operator",
          avatar_color: "#30D158",
          system_prompt: "You are operationally focused and prioritize incident response.",
          preferred_model_id: "llama-3-8b-instruct-q8",
          memory_policy: "aggressive",
          tags: ["ops", "watchdog"],
          compressed_summary: null,
          archived: false,
          created_at: "2026-05-08T00:00:00Z",
          updated_at: "2026-05-08T00:00:00Z",
          last_activated_at: null,
          activation_count: 1,
          is_active: false,
        },
        {
          id: "persona-24-3",
          name: "Researcher",
          avatar_color: "#AF52DE",
          system_prompt: "You reason deeply and provide evidence-backed responses.",
          preferred_model_id: "deepseek-r1-distill-qwen-7b-f16",
          memory_policy: "minimal",
          tags: ["research", "deep-work"],
          compressed_summary: null,
          archived: false,
          created_at: "2026-05-08T00:00:00Z",
          updated_at: "2026-05-08T00:00:00Z",
          last_activated_at: null,
          activation_count: 0,
          is_active: false,
        },
      ],
      total: 3,
    })
  ),
  http.post("/api/personas", async ({ request }) => {
    const body = (await request.json()) as {
      name: string;
      avatar_color: string;
      system_prompt: string;
      preferred_model_id: string;
      memory_policy: string;
      tags: string[];
    };
    return HttpResponse.json({
      id: "persona-24-created",
      name: body.name,
      avatar_color: body.avatar_color,
      system_prompt: body.system_prompt,
      preferred_model_id: body.preferred_model_id,
      memory_policy: body.memory_policy,
      tags: body.tags,
      compressed_summary: null,
      archived: false,
      created_at: "2026-05-08T00:00:00Z",
      updated_at: "2026-05-08T00:00:00Z",
      last_activated_at: null,
      activation_count: 0,
      is_active: false,
    });
  }),
  http.get("/api/personas/active", () =>
    HttpResponse.json({
      active: {
        id: "persona-24-1",
        name: "Analyst",
        avatar_color: "#0A84FF",
        system_prompt: "You are analytical and concise.",
        preferred_model_id: "qwen3-30b-a3b-q4",
        memory_policy: "balanced",
        tags: ["work", "reports"],
        compressed_summary: null,
        archived: false,
        created_at: "2026-05-08T00:00:00Z",
        updated_at: "2026-05-08T00:00:00Z",
        last_activated_at: "2026-05-08T00:00:00Z",
        activation_count: 3,
        is_active: true,
      },
    })
  ),
  http.get("/api/personas/:id", ({ params }) =>
    HttpResponse.json({
      id: params.id as string,
      name: "Persona",
      avatar_color: "#5E5CE6",
      system_prompt: "You are a specialist assistant.",
      preferred_model_id: "qwen3-30b-a3b-q4",
      memory_policy: "balanced",
      tags: ["tag1"],
      compressed_summary: "compressed",
      archived: false,
      created_at: "2026-05-08T00:00:00Z",
      updated_at: "2026-05-08T00:00:00Z",
      last_activated_at: null,
      activation_count: 0,
      is_active: false,
    })
  ),
  http.patch("/api/personas/:id", async ({ params, request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json({
      id: params.id as string,
      name: readStringValue(body.name, "Persona"),
      avatar_color: readStringValue(body.avatar_color, "#5E5CE6"),
      system_prompt: readStringValue(body.system_prompt, "Updated prompt"),
      preferred_model_id: readStringValue(body.preferred_model_id, "qwen3-30b-a3b-q4"),
      memory_policy: readStringValue(body.memory_policy, "balanced"),
      tags: Array.isArray(body.tags) ? body.tags : ["tag1"],
      compressed_summary: null,
      archived: false,
      created_at: "2026-05-08T00:00:00Z",
      updated_at: "2026-05-08T00:00:00Z",
      last_activated_at: null,
      activation_count: 1,
      is_active: false,
    });
  }),
  http.delete("/api/personas/:id", ({ params }) => HttpResponse.json({ ok: true, archived: params.id as string })),
  http.post("/api/personas/:id/clone", ({ params }) =>
    HttpResponse.json({
      id: `clone-${String(params.id)}`,
      name: "Copy of Persona",
      avatar_color: "#5E5CE6",
      system_prompt: "You are a specialist assistant.",
      preferred_model_id: "qwen3-30b-a3b-q4",
      memory_policy: "balanced",
      tags: ["tag1"],
      compressed_summary: null,
      archived: false,
      created_at: "2026-05-08T00:00:00Z",
      updated_at: "2026-05-08T00:00:00Z",
      last_activated_at: null,
      activation_count: 0,
      is_active: false,
    })
  ),
  http.post("/api/personas/:id/activate", ({ params }) =>
    HttpResponse.json({
      ok: true,
      active: {
        id: params.id as string,
        name: "Activated Persona",
        avatar_color: "#30D158",
        system_prompt: "Prompt",
        preferred_model_id: "qwen3-30b-a3b-q4",
        memory_policy: "balanced",
        tags: ["active"],
        compressed_summary: null,
        archived: false,
        created_at: "2026-05-08T00:00:00Z",
        updated_at: "2026-05-08T00:00:00Z",
        last_activated_at: "2026-05-08T00:00:00Z",
        activation_count: 5,
        is_active: true,
      },
      hot_swap: { attempted: true, ok: true },
    })
  ),
  http.get("/api/personas/:id/memory-summary", () =>
    HttpResponse.json({
      total_memories: 42,
      oldest_memory: "2026-01-01T00:00:00Z",
      newest_memory: "2026-05-08T00:00:00Z",
      top_topics: [
        { topic: "work", count: 16 },
        { topic: "research", count: 11 },
      ],
      compression_ratio: 0.42,
    })
  ),
  http.post("/api/personas/:id/compress-memory", ({ params }) =>
    HttpResponse.json({ accepted: true, persona_id: params.id as string, status: "queued" }, { status: 202 })
  ),

  // ── task-scheduler via agent-runtime /api/scheduler proxy ────────────────
  http.post("/api/scheduler/job", async ({ request }) => {
    const body = (await request.json()) as {
      name: string;
      cron_expr?: string;
      interval_seconds?: number;
      payload?: Record<string, unknown>;
      persona_id?: string;
      enabled?: boolean;
    };
    return HttpResponse.json(
      {
        id: "job-test-1",
        name: body.name,
        cron_expr: body.cron_expr ?? null,
        interval_seconds: body.interval_seconds ?? null,
        payload: body.payload ?? {},
        persona_id: body.persona_id ?? null,
        enabled: body.enabled ?? true,
        last_run: null,
        next_run: null,
        created_at: "2026-05-08T00:00:00Z",
      },
      { status: 201 }
    );
  }),
  http.get("/api/scheduler/job", () =>
    HttpResponse.json({
      jobs: [
        {
          id: "job-test-1",
          name: "nightly-report",
          cron_expr: "0 2 * * *",
          interval_seconds: null,
          payload: {},
          persona_id: null,
          enabled: true,
          last_run: null,
          next_run: null,
          created_at: "2026-05-08T00:00:00Z",
        },
      ],
      total: 1,
    })
  ),
  http.get("/api/scheduler/job/:id", ({ params }) =>
    HttpResponse.json({
      id: params.id as string,
      name: "nightly-report",
      cron_expr: "0 2 * * *",
      interval_seconds: null,
      payload: {},
      persona_id: null,
      enabled: true,
      last_run: null,
      next_run: null,
      created_at: "2026-05-08T00:00:00Z",
    })
  ),
  http.patch("/api/scheduler/job/:id", async ({ params, request }) => {
    const body = (await request.json()) as { name?: string; enabled?: boolean };
    return HttpResponse.json({
      id: params.id as string,
      name: body.name ?? "nightly-report",
      cron_expr: "0 2 * * *",
      interval_seconds: null,
      payload: {},
      persona_id: null,
      enabled: body.enabled ?? true,
      last_run: null,
      next_run: null,
      created_at: "2026-05-08T00:00:00Z",
    });
  }),
  http.delete("/api/scheduler/job/:id", () => new HttpResponse(null, { status: 204 })),
  http.post("/api/scheduler/job/:id/run-now", ({ params }) =>
    HttpResponse.json({ ok: true, job_id: params.id as string, queued: true }, { status: 202 })
  ),
  http.get("/api/scheduler/job/:id/runs", () =>
    HttpResponse.json({
      runs: [
        {
          id: "run-test-1",
          job_id: "job-test-1",
          status: "done",
          result: JSON.stringify({ output: "ok" }),
          error: null,
          started_at: "2026-05-08T02:00:00Z",
          finished_at: "2026-05-08T02:00:05Z",
        },
      ],
      total: 1,
    })
  ),
  http.get("/api/scheduler/health", () =>
    HttpResponse.json({ status: "ok", scheduler_running: true })
  ),

  // ── notification-bus via agent-runtime /api/notifications proxy ──────────
  http.get("/api/notifications/stream", () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            'data: {"id":"mock-1","type":"system","title":"Connected","body":"","source":"system","severity":"info","read":false,"created_at":"2024-01-01T00:00:00Z"}\n\n'
          )
        );
        controller.close();
      },
    });
    return new HttpResponse(stream, {
      headers: { "Content-Type": "text/event-stream" },
    });
  }),

  http.post("/api/notifications/notify", async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json(
      {
        id: "mock-notif-id",
        type: body["type"] ?? "system",
        title: body["title"] ?? "",
        body: body["body"] ?? "",
        source: body["source"] ?? "system",
        severity: body["severity"] ?? "info",
        read: false,
        created_at: new Date().toISOString(),
      },
      { status: 201 }
    );
  }),

  http.get("/api/notifications/notification", () =>
    HttpResponse.json({
      notifications: [
        {
          id: "mock-notif-1",
          type: "job_complete",
          title: "Job completed",
          body: "result ok",
          source: "task-scheduler",
          severity: "success",
          read: false,
          created_at: new Date().toISOString(),
        },
      ],
      total: 1,
    })
  ),

  http.get("/api/notifications/notification/:id", ({ params }) =>
    HttpResponse.json({
      id: params["id"],
      type: "system",
      title: "Mock Notification",
      body: "",
      source: "system",
      severity: "info",
      read: false,
      created_at: new Date().toISOString(),
    })
  ),

  http.patch("/api/notifications/notification/:id/read", ({ params }) =>
    HttpResponse.json({ ok: true, id: params["id"] })
  ),

  http.post("/api/notifications/notification/read-all", () =>
    HttpResponse.json({ ok: true, updated: 1 })
  ),

  http.delete(
    "/api/notifications/notification/:id",
    () => new HttpResponse(null, { status: 204 })
  ),

  // ---------------------------------------------------------------------------
  // Audit Log handlers
  // ---------------------------------------------------------------------------

  http.get("/api/audit/runs/stats", () =>
    HttpResponse.json({
      total: 5,
      by_status: { done: 3, failed: 2, stopped: 0 },
    })
  ),

  http.get("/api/audit/runs", () =>
    HttpResponse.json({
      total: 3,
      limit: 100,
      offset: 0,
      runs: [
        {
          id: "run-001",
          task_id: "notif-aaa",
          agent_id: "computer-use",
          persona_id: null,
          status: "done",
          started_at: new Date(Date.now() - 300_000).toISOString(),
          finished_at: new Date(Date.now() - 295_000).toISOString(),
          steps_json: JSON.stringify([{ action: "click", params: { x: 100, y: 200 } }]),
          result_json: JSON.stringify({ title: "Task completed", type: "task_complete" }),
          error: null,
          replay_count: 0,
          source: "computer-use",
          task_description: "Click the submit button on the form",
          created_at: new Date(Date.now() - 300_000).toISOString(),
        },
        {
          id: "run-002",
          task_id: "notif-bbb",
          agent_id: "task-scheduler",
          persona_id: null,
          status: "failed",
          started_at: new Date(Date.now() - 600_000).toISOString(),
          finished_at: new Date(Date.now() - 590_000).toISOString(),
          steps_json: "[]",
          result_json: JSON.stringify({ title: "Job nightly-report failed", type: "job_failed" }),
          error: "timeout after 120s",
          replay_count: 1,
          source: "task-scheduler",
          task_description: "nightly-report",
          created_at: new Date(Date.now() - 600_000).toISOString(),
        },
        {
          id: "run-003",
          task_id: "notif-ccc",
          agent_id: "computer-use",
          persona_id: null,
          status: "done",
          started_at: new Date(Date.now() - 900_000).toISOString(),
          finished_at: new Date(Date.now() - 898_000).toISOString(),
          steps_json: "[]",
          result_json: "{}",
          error: null,
          replay_count: 0,
          source: "computer-use",
          task_description: "Open the file manager and navigate to Downloads",
          created_at: new Date(Date.now() - 900_000).toISOString(),
        },
      ],
    })
  ),

  http.get("/api/audit/runs/:run_id", ({ params }) =>
    HttpResponse.json({
      id: params["run_id"],
      task_id: "notif-aaa",
      agent_id: "computer-use",
      persona_id: null,
      status: "done",
      started_at: new Date(Date.now() - 300_000).toISOString(),
      finished_at: new Date(Date.now() - 295_000).toISOString(),
      steps_json: JSON.stringify([
        { action: "screenshot", params: {}, reasoning: "initial screenshot" },
        { action: "click", params: { x: 640, y: 400 }, reasoning: "clicking submit" },
        { action: "done", params: {}, reasoning: "task complete" },
      ]),
      result_json: JSON.stringify({ title: "Task completed", type: "task_complete" }),
      error: null,
      replay_count: 0,
      source: "computer-use",
      task_description: String(params["run_id"]).startsWith("run-")
        ? "Click the submit button on the form"
        : "Replayed task",
      created_at: new Date(Date.now() - 300_000).toISOString(),
    })
  ),

  http.post("/api/audit/runs/:run_id/replay", () =>
    HttpResponse.json({ ok: true, run_id: crypto.randomUUID(), replayed_from: "run-001" })
  ),

  http.post("/computer/task/run", async ({ request }) => {
    const body = (await request.json()) as { task_description?: string; max_steps?: number };
    return HttpResponse.json({
      status: "done",
      message: `Task queued: ${body.task_description ?? "untitled task"}`,
      steps: [{ action: "queued", params: { max_steps: body.max_steps ?? 20 } }],
      actions: [],
    });
  }),

  http.get("/api/audit/health", () =>
    HttpResponse.json({ status: "ok", service: "audit-log" })
  ),

  // ---------------------------------------------------------------------------
  // Package Manager handlers
  // ---------------------------------------------------------------------------
  http.get("/api/packages", ({ request }) => {
    const url = new URL(request.url);
    const status = url.searchParams.get("status");
    const type = url.searchParams.get("type");
    const q = url.searchParams.get("q")?.toLowerCase() ?? "";

    const filtered = mockPackageCatalog.filter((pkg) => {
      if (status && pkg.status !== status) {
        return false;
      }
      if (type && pkg.type !== type) {
        return false;
      }
      if (q) {
        const haystack = `${pkg.package_id} ${pkg.name} ${pkg.description}`.toLowerCase();
        if (!haystack.includes(q)) {
          return false;
        }
      }
      return true;
    });

    return HttpResponse.json({ packages: filtered, total: filtered.length });
  }),

  http.get("/api/packages/catalog", () =>
    HttpResponse.json({ packages: mockPackageCatalog, total: mockPackageCatalog.length })
  ),

  http.get("/api/packages/operations", ({ request }) => {
    const url = new URL(request.url);
    const packageId = url.searchParams.get("package_id");
    const filtered = packageId
      ? mockPackageOperations.filter((op) => op.package_id === packageId)
      : mockPackageOperations;
    return HttpResponse.json({
      operations: filtered,
      total: filtered.length,
      limit: 50,
      offset: 0,
    });
  }),

  http.get("/api/packages/operations/stats", () =>
    HttpResponse.json({
      total_operations: mockPackageOperations.length,
      packages_installed: mockPackageCatalog.filter((pkg) => pkg.status !== "available").length,
      packages_available: mockPackageCatalog.filter((pkg) => pkg.status === "available").length,
      by_operation: {
        install: 1,
        update: 1,
        disable: 1,
      },
    })
  ),

  http.get("/api/packages/:packageId", ({ params }) => {
    const pkg = mockPackageCatalog.find((item) => item.package_id === params.packageId);
    if (!pkg) {
      return HttpResponse.json({ detail: "Package not found" }, { status: 404 });
    }
    return HttpResponse.json(pkg);
  }),

  http.post("/api/packages/install", async ({ request }) => {
    const body = (await request.json()) as { package_id?: string };
    return HttpResponse.json(
      {
        ok: true,
        operation_id: "mock-op-install",
        package_id: body.package_id ?? "unknown",
        status: "installed",
      },
      { status: 202 }
    );
  }),

  http.post("/api/packages/:packageId/update", ({ params }) =>
    HttpResponse.json({ ok: true, operation_id: "mock-op-update", package_id: params.packageId }, { status: 202 })
  ),

  http.post("/api/packages/:packageId/enable", ({ params }) =>
    HttpResponse.json({ ok: true, operation_id: "mock-op-enable", package_id: params.packageId }, { status: 202 })
  ),

  http.post("/api/packages/:packageId/disable", ({ params }) =>
    HttpResponse.json({ ok: true, operation_id: "mock-op-disable", package_id: params.packageId }, { status: 202 })
  ),

  http.post("/api/packages/:packageId/check", ({ params }) =>
    HttpResponse.json({
      package_id: params.packageId,
      healthy: true,
      status_code: 200,
      checked_at: new Date().toISOString(),
      entrypoint: "http://localhost:8100",
    })
  ),

  http.delete("/api/packages/:packageId", ({ params }) =>
    HttpResponse.json({ ok: true, operation_id: "mock-op-remove", package_id: params.packageId }, { status: 202 })
  ),

  // --- Phase 28: Security policy endpoints ---
  http.get("/api/security/policies", () =>
    HttpResponse.json({
      grants: [
        { id: "grant-1", subject_type: "package", subject_id: "notification-center", permission: "network", scope: "global", expires_at: null, granted_by: "admin", created_at: new Date(Date.now() - 86400000).toISOString(), active: true },
        { id: "grant-2", subject_type: "persona", subject_id: "assistant", permission: "persona-activation", scope: "session", expires_at: null, granted_by: "admin", created_at: new Date(Date.now() - 43200000).toISOString(), active: true },
        { id: "grant-3", subject_type: "service", subject_id: "watchdog", permission: "service-restart", scope: "global", expires_at: null, granted_by: "security-center-ui", created_at: new Date(Date.now() - 3600000).toISOString(), active: true },
        { id: "grant-4", subject_type: "package", subject_id: "task-history", permission: "package-install", scope: "global", expires_at: new Date(Date.now() + 3600000).toISOString(), granted_by: "admin", created_at: new Date(Date.now() - 1800000).toISOString(), active: true },
      ],
      total: 4,
    })
  ),

  http.get("/api/security/policies/:subjectType/:subjectId", ({ params }) =>
    HttpResponse.json({
      grants: [
        { id: "grant-1", subject_type: params.subjectType, subject_id: params.subjectId, permission: "network", scope: "global", expires_at: null, granted_by: "admin", created_at: new Date(Date.now() - 86400000).toISOString(), active: true },
      ],
      total: 1,
    })
  ),

  http.post("/api/security/grant", () =>
    HttpResponse.json({ ok: true, grant_id: "mock-grant-id", subject_type: "package", subject_id: "test", permission: "network", scope: "global", expires_at: null, granted_by: "security-center-ui", created_at: new Date().toISOString() }, { status: 201 })
  ),

  http.post("/api/security/revoke", () =>
    HttpResponse.json({ ok: true, revoked: "network" })
  ),

  http.post("/api/security/check", () =>
    HttpResponse.json({ allowed: true, reason: "grant found", subject_type: "package", subject_id: "test", permission: "network" })
  ),

  http.get("/api/security/audit", () =>
    HttpResponse.json({
      entries: [
        { id: "audit-1", subject_type: "package", subject_id: "notification-center", permission: "package-install", action: "check", allowed: false, reason: "no grant found", created_at: new Date(Date.now() - 120000).toISOString() },
        { id: "audit-2", subject_type: "persona", subject_id: "assistant", permission: "persona-activation", action: "check", allowed: true, reason: "grant found", created_at: new Date(Date.now() - 90000).toISOString() },
        { id: "audit-3", subject_type: "service", subject_id: "watchdog", permission: "service-restart", action: "grant", allowed: true, reason: "admin granted", created_at: new Date(Date.now() - 60000).toISOString() },
        { id: "audit-4", subject_type: "package", subject_id: "task-history", permission: "package-remove", action: "check", allowed: false, reason: "no grant found", created_at: new Date(Date.now() - 30000).toISOString() },
        { id: "audit-5", subject_type: "service", subject_id: "model-hub", permission: "model-activation", action: "check", allowed: true, reason: "fail-open: policy unavailable", created_at: new Date().toISOString() },
      ],
      total: 5,
    })
  ),

  http.get("/api/security/audit/stats", () =>
    HttpResponse.json({ total: 5, allowed: 3, denied: 2, by_permission: { "package-install": 1, "persona-activation": 1, "service-restart": 1, "package-remove": 1, "model-activation": 1 } })
  ),

  http.get("/api/security/health", () =>
    HttpResponse.json({ status: "ok", service: "security-policy" })
  ),

  // --- Phase 30: OTA service endpoints ---
  http.get("/api/ota/status", () =>
    HttpResponse.json({
      active_slot: "a",
      version: "1.0.0",
      last_check_ts: new Date(Date.now() - 60_000).toISOString(),
      state: "IDLE",
    })
  ),

  http.post("/api/ota/check", () =>
    HttpResponse.json({
      update_available: true,
      version: "1.0.1",
      changelog: [
        "Improved OTA slot switching safety",
        "Security and stability updates",
      ],
    })
  ),

  http.post("/api/ota/download", () =>
    HttpResponse.json({ download_id: "download-ota-1" })
  ),

  http.post("/api/ota/apply", () =>
    HttpResponse.json({ status: "applied", slot: "b" })
  ),

  http.post("/api/ota/commit", () =>
    HttpResponse.json({ status: "committed", next_slot: "b" })
  ),

  http.post("/api/ota/rollback", () =>
    HttpResponse.json({ status: "rolled_back", active_slot: "a" })
  ),
    // --- Phase 31: Voice Service endpoints ---
    http.get("/api/voice/status", () =>
      HttpResponse.json({
        listening: false,
        wake_word_detected: false,
        last_transcript: "Hello Kryos",
        last_response: "Hi there! How can I help?",
      })
    ),

    http.post("/api/voice/transcribe", async ({ request }) => {
      await request.json();
      return HttpResponse.json({
        transcript: "what time is it",
        confidence: 0.92,
      });
    }),

    http.post("/api/voice/speak", async ({ request }) => {
      await request.json();
      const silenceWav = "UklGRiYAAABXQVZFZm10IBAAAAABAAEAQB8AAAB9AAACABAAZGF0YQIAAAAAAA==";
      return HttpResponse.json({
        audio_base64: silenceWav,
        duration_ms: 100,
      });
    }),

    http.post("/api/voice/pipeline", async ({ request }) => {
      await request.json();
      const silenceWav = "UklGRiYAAABXQVZFZm10IBAAAAABAAEAQB8AAAB9AAACABAAZGF0YQIAAAAAAA==";
      return HttpResponse.json({
        transcript: "set a timer for five minutes",
        response_text: "Timer set for 5 minutes.",
        audio_base64: silenceWav,
        total_latency_ms: 456,
        stt_latency_ms: 120,
        agent_latency_ms: 180,
        tts_latency_ms: 156,
      });
    }),

    http.get("/api/voice/models", () =>
      HttpResponse.json({
        stt_models: ["tiny", "base", "small", "medium", "large"],
        tts_models: ["en_US-lessac-medium", "en_US-amy-medium", "en_US-libritts_high-medium"],
      })
    ),

    http.post("/api/voice/models/:name/load", ({ params }) =>
      HttpResponse.json({
        model: params["name"],
        status: "loaded",
      })
    ),

    http.post("/api/voice/wake-word/enable", () =>
      HttpResponse.json({ listening: true })
    ),

    http.post("/api/voice/wake-word/disable", () =>
      HttpResponse.json({ listening: false })
    ),

    // --- Phase 32: Auth + RBAC endpoints ---
    http.post("/auth/login", async ({ request }) => {
      const body = (await request.json()) as { username?: string; password?: string };
      if (!body.username || body.password === "wrong") {
        return HttpResponse.json({ detail: "invalid credentials" }, { status: 401 });
      }
      return HttpResponse.json({
        access_token: `access-${body.username}`,
        refresh_token: `refresh-${body.username}`,
        token_type: "bearer",
        expires_in: 900,
        session_id: `${body.username}:session`,
        user: {
          username: body.username,
          role: body.username === "admin" ? "admin" : "guest",
          persona_id: null,
          model_id: null,
          theme: "system",
          voice: "en_US-lessac-medium",
        },
      });
    }),

    http.post("/auth/refresh", async ({ request }) => {
      const body = (await request.json()) as { refresh_token?: string };
      if (!body.refresh_token || body.refresh_token.includes("revoked")) {
        return HttpResponse.json({ detail: "refresh token revoked" }, { status: 401 });
      }
      return HttpResponse.json({
        access_token: "access-refreshed",
        refresh_token: "refresh-rotated",
        token_type: "bearer",
        expires_in: 900,
      });
    }),

    http.post("/auth/logout", () => HttpResponse.json({ ok: true })),

    http.get("/auth/me", () =>
      HttpResponse.json({
        username: "alice",
        role: "guest",
        persona_id: null,
        model_id: null,
        theme: "system",
        voice: "en_US-lessac-medium",
        session_id: "alice:session",
      })
    ),

    http.get("/auth/verify", ({ request }) => {
      const auth = request.headers.get("authorization") ?? "";
      if (!auth.startsWith("Bearer ")) {
        return HttpResponse.json({ detail: "missing bearer token" }, { status: 401 });
      }
      return HttpResponse.json({ username: "alice", role: "guest", session_id: "alice:session" });
    }),

    http.get("/users", () =>
      HttpResponse.json({
        users: [
          { username: "admin", role: "admin", model_id: null, persona_id: null, theme: "system", voice: "en_US-lessac-medium" },
          { username: "alice", role: "guest", model_id: null, persona_id: null, theme: "system", voice: "en_US-lessac-medium" },
        ],
        total: 2,
      })
    ),

    http.post("/users/:username/role", ({ params }) =>
      HttpResponse.json({ username: params.username, role: "operator" })
    ),

    http.get("/users/:username/prefs", ({ params }) =>
      HttpResponse.json({
        username: params.username,
        model_id: "llama3",
        persona_id: "assistant",
        theme: "system",
        voice: "en_US-lessac-medium",
      })
    ),

    http.patch("/users/:username/prefs", async ({ params, request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({
        username: params.username,
        model_id: (body.model_id as string | undefined) ?? "llama3",
        persona_id: (body.persona_id as string | undefined) ?? "assistant",
        theme: (body.theme as string | undefined) ?? "system",
        voice: (body.voice as string | undefined) ?? "en_US-lessac-medium",
      });
    }),
    http.get("/api/hardware/current", () =>
      HttpResponse.json({
        cpu: { temp_c: 62.4, usage_pct: 31.2, freq_mhz: 2890, cores: 8, throttled: false },
        memory: { total_mb: 16384, used_mb: 7420, available_mb: 8964, swap_used_mb: 120, pressure: "low" },
        disks: [{ device: "/dev/nvme0n1", mount: "/", total_gb: 476, used_gb: 238, pct: 50, smart_status: "ok", temp_c: 41, reallocated_sectors: 0 }],
        battery: { present: true, pct: 82, status: "discharging", time_remaining_min: 170, health_pct: 93 },
        network: [{ iface: "wlan0", bytes_sent_ps: 145200, bytes_recv_ps: 843000, latency_ms: 18.4, link_up: true, speed_mbps: 866 }],
        gpu: { present: false, vendor: null, model: null, temp_c: null, usage_pct: null, vram_used_mb: null },
        health_score: 0.86,
        anomaly_score: 0.91,
        anomaly_detected: false,
      })
    ),
    http.get("/api/hardware/history", ({ request }) => {
      const url = new URL(request.url);
      const metric = url.searchParams.get("metric") ?? "cpu_temp";
      const now = Date.now();
      const points = Array.from({ length: 24 }).map((_, i) => ({
        ts: new Date(now - (23 - i) * 3600_000).toISOString(),
        value: metric === "battery_pct" ? Math.max(0, 92 - i) : metric === "disk_pct" ? 48 + (i % 3) : metric === "memory_used" ? 7200 + i * 5 : 54 + (i % 8),
      }));
      return HttpResponse.json({ metric, points });
    }),
    http.get("/api/hardware/alerts", () =>
      HttpResponse.json([
        {
          alert_id: "alert-cpu-warn",
          severity: "warning",
          component: "cpu",
          message: "CPU temperature is elevated",
          first_seen: new Date(Date.now() - 30 * 60_000).toISOString(),
          last_seen: new Date(Date.now() - 5 * 60_000).toISOString(),
          count: 3,
        },
      ])
    ),
    http.post("/api/hardware/alerts/:alertId/dismiss", ({ params }) =>
      HttpResponse.json({ status: "dismissed", alert_id: params.alertId })
    ),
    http.get("/api/hardware/baseline", () =>
      HttpResponse.json({ status: "ready", samples_trained: 240, min_samples_required: 100 })
    ),
    http.post("/api/hardware/baseline/train", () =>
      HttpResponse.json({ status: "complete", samples_trained: 260, model_retrained: true })
    ),
    http.get("/api/sdk/apps", () =>
      HttpResponse.json([
        {
          app_id: "weather-app-a1b2c3d4",
          display_name: "Weather App",
          version: "1.0.0",
          author: "Demo Developer",
          status: "running",
          permissions: ["network", "notifications"],
          capabilities: ["get:weather", "get:forecast"],
          installed_ts: new Date().toISOString(),
          last_active_ts: new Date().toISOString(),
        },
      ])
    ),
    http.post("/api/sdk/apps/install", () =>
      HttpResponse.json({ app_id: "new-app-x1y2z3w4", status: "installed", message: "App installed successfully" })
    ),
    http.post("/api/sdk/apps/validate", () =>
      HttpResponse.json({ valid: true, errors: [], permissions: ["model-inference", "notifications"] })
    ),
    http.delete("/api/sdk/apps/:appId", () => HttpResponse.json({ uninstalled: true })),
    http.post("/api/sdk/apps/:appId/start", ({ params }) =>
      HttpResponse.json({ status: "running", container_id: `container-${params.appId}` })
    ),
    http.post("/api/sdk/apps/:appId/stop", () => HttpResponse.json({ status: "stopped" })),
    http.get("/api/sdk/apps/:appId/status", ({ params }) =>
      HttpResponse.json({
        app_id: params.appId,
        status: "running",
        container_id: `container-${params.appId}`,
        uptime_seconds: 3600,
        memory_used_mb: 128.5,
        cpu_pct: 2.3,
      })
    ),
    http.post("/api/sdk/delegate", () =>
      HttpResponse.json({ app_id: "weather-app-a1b2c3d4", result: { answer: "22°C, partly cloudy" }, latency_ms: 143 })
    ),
    http.get("/api/sdk/capabilities", () =>
      HttpResponse.json([
        { capability: "get:weather", app_id: "weather-app-a1b2c3d4", app_name: "Weather App", avg_latency_ms: 143.0 },
        { capability: "get:forecast", app_id: "weather-app-a1b2c3d4", app_name: "Weather App", avg_latency_ms: 201.0 },
      ])
    ),
    http.get("/api/sdk/health", () =>
      HttpResponse.json({ status: "ok", service: "sdk-registry", version: "1.0.0", installed_apps: 1, running_apps: 1 })
    ),
];
