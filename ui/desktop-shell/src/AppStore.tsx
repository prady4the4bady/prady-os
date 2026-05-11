import React, { useCallback, useEffect, useRef, useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Package {
  package_id: string;
  name: string;
  version: string;
  type: string;
  description: string;
  entrypoint: string;
  service_name: string | null;
  dependencies: string[];
  permissions: string[];
  healthcheck_path: string | null;
  source: string;
  status: "available" | "installed" | "enabled" | "disabled" | "broken";
  installed_at: string | null;
  updated_at: string;
}

interface PackageOperation {
  id: string;
  package_id: string;
  operation: string;
  status: "pending" | "running" | "success" | "failed";
  message: string | null;
  started_at: string;
  completed_at: string | null;
  created_at: string;
}

interface SDKApp {
  app_id: string;
  display_name: string;
  version: string;
  author: string;
  status: "running" | "stopped" | "error";
  permissions: string[];
  capabilities: string[];
  installed_ts: string;
  last_active_ts: string | null;
}

interface CapabilityEntry {
  capability: string;
  app_id: string;
  app_name: string;
  avg_latency_ms: number;
}

type JsonPrimitive = string | number | boolean | null;
type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };
type JsonObject = { [key: string]: JsonValue };

type Tab = "browse" | "installed" | "operations" | "developer";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface AppStoreProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  layerZIndex: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function typeBadgeColor(type: string): string {
  switch (type) {
    case "panel":
      return "#2563eb";
    case "service":
      return "#7c3aed";
    case "agent":
      return "#059669";
    case "tool":
      return "#d97706";
    default:
      return "#6b7280";
  }
}

function statusColor(status: string): string {
  switch (status) {
    case "enabled":
      return "#10b981";
    case "installed":
      return "#3b82f6";
    case "disabled":
      return "#9ca3af";
    case "broken":
      return "#ef4444";
    case "available":
      return "#6b7280";
    default:
      return "#6b7280";
  }
}

function opStatusColor(status: string): string {
  switch (status) {
    case "success":
      return "#10b981";
    case "failed":
      return "#ef4444";
    case "running":
      return "#3b82f6";
    default:
      return "#9ca3af";
  }
}

function colorFromId(value: string): string {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) | 0;
  }
  const colors = ["#2563eb", "#7c3aed", "#059669", "#d97706", "#db2777", "#0891b2"];
  return colors[Math.abs(hash) % colors.length];
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface PackageCardProps {
  pkg: Package;
  onAction: (packageId: string, action: string) => Promise<void>;
  loading: string | null; // "packageId:action"
  error: string | null; // packageId that has an error message
  errorMsg: string | null;
}

function PackageCard({ pkg, onAction, loading, error, errorMsg }: Readonly<PackageCardProps>): JSX.Element {
  const busy = (action: string) => loading === `${pkg.package_id}:${action}`;

  const actionButton = (
    label: string,
    action: string,
    color: string
  ): JSX.Element => (
    <button
      key={action}
      disabled={!!loading}
      onClick={() => onAction(pkg.package_id, action)}
      style={{
        padding: "3px 10px",
        fontSize: 12,
        borderRadius: 4,
        border: "none",
        cursor: loading ? "not-allowed" : "pointer",
        background: color,
        color: "#fff",
        opacity: loading ? 0.6 : 1,
        marginRight: 6,
        marginBottom: 4,
      }}
    >
      {busy(action) ? "…" : label}
    </button>
  );

  const actions: JSX.Element[] = [];
  if (pkg.status === "available") {
    actions.push(actionButton("Install", "install", "#2563eb"));
  }
  if (pkg.status === "installed" || pkg.status === "disabled") {
    actions.push(actionButton("Enable", "enable", "#059669"));
  }
  if (pkg.status === "enabled") {
    actions.push(actionButton("Disable", "disable", "#d97706"));
  }
  if (pkg.status === "installed" || pkg.status === "enabled" || pkg.status === "disabled" || pkg.status === "broken") {
    actions.push(
      actionButton("Update", "update", "#7c3aed"),
      actionButton("Remove", "remove", "#ef4444"),
      actionButton("Check", "check", "#6b7280")
    );
  }

  return (
    <div
      style={{
        background: "#1e2229",
        border: "1px solid #2d3340",
        borderRadius: 8,
        padding: "14px 16px",
        marginBottom: 10,
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontWeight: 600, fontSize: 14, color: "#e5e7eb" }}>{pkg.name}</span>
            <span style={{ fontSize: 11, color: "#9ca3af" }}>v{pkg.version}</span>
            <span
              style={{
                fontSize: 10,
                padding: "1px 6px",
                borderRadius: 10,
                background: typeBadgeColor(pkg.type),
                color: "#fff",
                fontWeight: 500,
              }}
            >
              {pkg.type}
            </span>
            <span
              style={{
                fontSize: 10,
                padding: "1px 6px",
                borderRadius: 10,
                border: `1px solid ${statusColor(pkg.status)}`,
                color: statusColor(pkg.status),
              }}
            >
              {pkg.status}
            </span>
          </div>
          <p style={{ margin: "6px 0 0", fontSize: 12, color: "#9ca3af", lineHeight: 1.5 }}>
            {pkg.description}
          </p>
          {pkg.dependencies.length > 0 && (
            <p style={{ margin: "4px 0 0", fontSize: 11, color: "#6b7280" }}>
              Requires: {pkg.dependencies.join(", ")}
            </p>
          )}
        </div>
      </div>
      {error === pkg.package_id && errorMsg && (
        <div
          style={{
            marginTop: 8,
            padding: "6px 10px",
            background: "#3b1212",
            border: "1px solid #7f1d1d",
            borderRadius: 4,
            fontSize: 11,
            color: "#fca5a5",
          }}
        >
          {errorMsg}
        </div>
      )}
      {actions.length > 0 && (
        <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap" }}>{actions}</div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function AppStore({ open, onOpenChange, layerZIndex }: Readonly<AppStoreProps>): JSX.Element | null {
  const [tab, setTab] = useState<Tab>("browse");
  const [packages, setPackages] = useState<Package[]>([]);
  const [operations, setOperations] = useState<PackageOperation[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionErrorMsg, setActionErrorMsg] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [statsTotal, setStatsTotal] = useState<number>(0);
  const [sdkApps, setSdkApps] = useState<SDKApp[]>([]);
  const [sdkCapabilities, setSdkCapabilities] = useState<CapabilityEntry[]>([]);
  const [sdkInstallUrl, setSdkInstallUrl] = useState("");
  const [sdkManifestJson, setSdkManifestJson] = useState("{\n  \"name\": \"my-app\",\n  \"display_name\": \"My App\"\n}");
  const [sdkInstallState, setSdkInstallState] = useState<"idle" | "validating" | "permission-review" | "installing" | "success" | "error">("idle");
  const [sdkInstallMessage, setSdkInstallMessage] = useState("");
  const [sdkInstallErrors, setSdkInstallErrors] = useState<string[]>([]);
  const [sdkPendingManifest, setSdkPendingManifest] = useState<JsonObject | null>(null);
  const [sdkPendingPermissions, setSdkPendingPermissions] = useState<string[]>([]);
  const [sdkActionLoading, setSdkActionLoading] = useState<string | null>(null);
  const refreshRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchPackages = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (search) params.set("q", search);
      if (typeFilter !== "all") params.set("type", typeFilter);
      const res = await fetch(`/api/packages?${params.toString()}`);
      if (res.ok) {
        const data = (await res.json()) as { packages: Package[]; total: number };
        setPackages(data.packages);
      }
    } catch {
      // ignore network errors in dev
    } finally {
      setLoading(false);
    }
  }, [search, typeFilter]);

  const fetchOperations = useCallback(async () => {
    try {
      const res = await fetch("/api/packages/operations?limit=30");
      if (res.ok) {
        const data = (await res.json()) as { operations: PackageOperation[]; total: number };
        setOperations(data.operations);
        setStatsTotal(data.total);
      }
    } catch {
      // ignore
    }
  }, []);

  const fetchSdkApps = useCallback(async () => {
    try {
      const res = await fetch("/api/sdk/apps");
      if (res.ok) {
        const data = (await res.json()) as SDKApp[];
        setSdkApps(data);
      }
    } catch {
      // ignore
    }
  }, []);

  const fetchSdkCapabilities = useCallback(async () => {
    try {
      const res = await fetch("/api/sdk/capabilities");
      if (res.ok) {
        const data = (await res.json()) as CapabilityEntry[];
        setSdkCapabilities(data);
      }
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    void fetchPackages();
    void fetchOperations();
  }, [open, fetchPackages, fetchOperations]);

  useEffect(() => {
    if (!open || tab !== "developer") {
      return;
    }
    void fetchSdkApps();
    void fetchSdkCapabilities();
  }, [open, tab, fetchSdkApps, fetchSdkCapabilities]);

  // auto-refresh operations every 30s
  useEffect(() => {
    if (!open) {
      if (refreshRef.current !== null) clearInterval(refreshRef.current);
      return;
    }
    refreshRef.current = setInterval(() => {
      void fetchOperations();
    }, 30_000);
    return () => {
      if (refreshRef.current !== null) clearInterval(refreshRef.current);
    };
  }, [open, fetchOperations]);

  useEffect(() => {
    if (!open || tab !== "developer") {
      return;
    }
    const interval = setInterval(() => {
      void fetchSdkApps();
    }, 15_000);
    return () => clearInterval(interval);
  }, [open, tab, fetchSdkApps]);

  const handleAction = useCallback(
    async (packageId: string, action: string) => {
      setActionError(null);
      setActionErrorMsg(null);
      setActionLoading(`${packageId}:${action}`);
      try {
        let res: Response;
        if (action === "install") {
          res = await fetch("/api/packages/install", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ package_id: packageId }),
          });
        } else if (action === "remove") {
          res = await fetch(`/api/packages/${packageId}`, { method: "DELETE" });
        } else {
          res = await fetch(`/api/packages/${packageId}/${action}`, { method: "POST" });
        }

        if (res.ok) {
          await fetchPackages();
          await fetchOperations();
        } else {
          const body = (await res.json()) as { detail?: string };
          setActionError(packageId);
          setActionErrorMsg(body.detail ?? `${action} failed (${res.status})`);
        }
      } catch (err) {
        setActionError(packageId);
        setActionErrorMsg(err instanceof Error ? err.message : "Network error");
      } finally {
        setActionLoading(null);
      }
    },
    [fetchPackages, fetchOperations]
  );

  const validateManifestPayload = useCallback(async (manifest: JsonObject) => {
    setSdkInstallState("validating");
    setSdkInstallMessage("Validating manifest...");
    setSdkInstallErrors([]);
    const response = await fetch("/api/sdk/apps/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ manifest_json: manifest }),
    });
    const data = (await response.json()) as { valid?: boolean; errors?: string[]; permissions?: string[] };
    if (!response.ok || !data.valid) {
      setSdkInstallState("error");
      setSdkInstallErrors(data.errors ?? ["Manifest validation failed"]);
      setSdkInstallMessage("Manifest validation failed");
      return false;
    }
    const permissions = data.permissions ?? [];
    setSdkPendingManifest(manifest);
    setSdkPendingPermissions(permissions);
    setSdkInstallState("permission-review");
    setSdkInstallMessage("Review permissions before installation");
    return true;
  }, []);

  const validateManifestJson = useCallback(async () => {
    try {
      const manifest = JSON.parse(sdkManifestJson) as JsonObject;
      await validateManifestPayload(manifest);
    } catch {
      setSdkInstallState("error");
      setSdkInstallErrors(["Manifest JSON is invalid"]);
      setSdkInstallMessage("Manifest JSON is invalid");
    }
  }, [sdkManifestJson, validateManifestPayload]);

  const validateManifestUrl = useCallback(async () => {
    try {
      if (!sdkInstallUrl.trim()) {
        setSdkInstallState("error");
        setSdkInstallErrors(["Manifest URL is required"]);
        setSdkInstallMessage("Manifest URL is required");
        return;
      }
      const response = await fetch(sdkInstallUrl);
      const manifest = (await response.json()) as JsonObject;
      await validateManifestPayload(manifest);
    } catch {
      setSdkInstallState("error");
      setSdkInstallErrors(["Failed to load manifest from URL"]);
      setSdkInstallMessage("Failed to load manifest from URL");
    }
  }, [sdkInstallUrl, validateManifestPayload]);

  const completeSdkInstall = useCallback(async () => {
    if (!sdkPendingManifest) {
      return;
    }
    setSdkInstallState("installing");
    setSdkInstallMessage("Installing app...");
    setSdkInstallErrors([]);
    const response = await fetch("/api/sdk/apps/install", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ manifest_json: sdkPendingManifest }),
    });
    const data = (await response.json()) as { app_id?: string; message?: string; detail?: { errors?: string[] } };
    if (!response.ok) {
      setSdkInstallState("error");
      setSdkInstallErrors(data.detail?.errors ?? [data.message ?? "Install failed"]);
      setSdkInstallMessage("Install failed");
      return;
    }
    setSdkInstallState("success");
    setSdkInstallMessage(`Installed ${data.app_id ?? "SDK app"}`);
    setSdkPendingManifest(null);
    setSdkPendingPermissions([]);
    setSdkInstallUrl("");
    setSdkManifestJson("{\n  \"name\": \"my-app\",\n  \"display_name\": \"My App\"\n}");
    void fetchSdkApps();
  }, [fetchSdkApps, sdkPendingManifest]);

  const handleSdkAction = useCallback(
    async (appId: string, action: "start" | "stop" | "delete") => {
      if (action === "delete" && !window.confirm(`Are you sure you want to uninstall ${appId}? This will delete all app data.`)) {
        return;
      }
      setSdkActionLoading(`${appId}:${action}`);
      try {
        const response = await fetch(
          action === "delete" ? `/api/sdk/apps/${appId}` : `/api/sdk/apps/${appId}/${action}`,
          { method: action === "delete" ? "DELETE" : "POST" }
        );
        if (response.ok) {
          await fetchSdkApps();
          await fetchSdkCapabilities();
        }
      } finally {
        setSdkActionLoading(null);
      }
    },
    [fetchSdkApps, fetchSdkCapabilities]
  );

  if (!open) return null;

  const installed = packages.filter((p) => p.status !== "available");
  const browse = packages;

  const tabPackages = tab === "installed" ? installed : browse;

  return (
    <dialog
      open
      aria-label="App Store"
      style={{
        position: "fixed",
        top: 0,
        right: 0,
        width: 480,
        height: "100vh",
        background: "#13161b",
        borderLeft: "1px solid #2d3340",
        zIndex: layerZIndex,
        display: "flex",
        flexDirection: "column",
        boxShadow: "-4px 0 24px rgba(0,0,0,0.5)",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "16px 20px 12px",
          borderBottom: "1px solid #2d3340",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <span style={{ fontWeight: 700, fontSize: 16, color: "#e5e7eb" }}>App Store</span>
        <button
          onClick={() => onOpenChange(false)}
          style={{
            background: "none",
            border: "none",
            color: "#9ca3af",
            cursor: "pointer",
            fontSize: 20,
            lineHeight: 1,
            padding: "0 4px",
          }}
          aria-label="Close App Store"
        >
          ×
        </button>
      </div>

      {/* Search + filter */}
      <div style={{ padding: "10px 16px", borderBottom: "1px solid #2d3340", display: "flex", gap: 8 }}>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search packages…"
          style={{
            flex: 1,
            padding: "6px 10px",
            background: "#1e2229",
            border: "1px solid #2d3340",
            borderRadius: 6,
            color: "#e5e7eb",
            fontSize: 13,
            outline: "none",
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") void fetchPackages();
          }}
        />
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          style={{
            padding: "6px 8px",
            background: "#1e2229",
            border: "1px solid #2d3340",
            borderRadius: 6,
            color: "#e5e7eb",
            fontSize: 12,
            cursor: "pointer",
          }}
        >
          <option value="all">All types</option>
          <option value="panel">Panel</option>
          <option value="service">Service</option>
          <option value="agent">Agent</option>
          <option value="tool">Tool</option>
        </select>
        <button
          onClick={() => void fetchPackages()}
          style={{
            padding: "6px 12px",
            background: "#2563eb",
            border: "none",
            borderRadius: 6,
            color: "#fff",
            fontSize: 12,
            cursor: "pointer",
          }}
        >
          Search
        </button>
      </div>

      {/* Tabs */}
      <div
        style={{
          display: "flex",
          borderBottom: "1px solid #2d3340",
          paddingLeft: 16,
        }}
      >
        {(["browse", "installed", "operations", "developer"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: "10px 16px",
              background: "none",
              border: "none",
              borderBottom: tab === t ? "2px solid #2563eb" : "2px solid transparent",
              color: tab === t ? "#e5e7eb" : "#6b7280",
              fontSize: 13,
              cursor: "pointer",
              textTransform: "capitalize",
              marginBottom: -1,
            }}
          >
              {t === "browse" ? "Browse" : t === "developer" ? "Developer" : t}
            {t === "installed" && installed.length > 0 && (
              <span
                style={{
                  marginLeft: 6,
                  background: "#2563eb",
                  color: "#fff",
                  borderRadius: 10,
                  fontSize: 10,
                  padding: "1px 5px",
                }}
              >
                {installed.length}
              </span>
            )}
            {t === "operations" && statsTotal > 0 && (
              <span
                style={{
                  marginLeft: 6,
                  background: "#374151",
                  color: "#9ca3af",
                  borderRadius: 10,
                  fontSize: 10,
                  padding: "1px 5px",
                }}
              >
                {statsTotal}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Body */}
      <div style={{ flex: 1, overflowY: "auto", padding: "12px 16px" }}>
        {loading && (
          <div style={{ color: "#6b7280", fontSize: 13, textAlign: "center", marginTop: 40 }}>
            Loading…
          </div>
        )}

        {!loading && tab !== "operations" && tab !== "developer" && (
          <>
            {tabPackages.length === 0 ? (
              <div style={{ color: "#6b7280", fontSize: 13, textAlign: "center", marginTop: 40 }}>
                {tab === "installed" ? "No packages installed yet." : "No packages found."}
              </div>
            ) : (
              tabPackages.map((pkg) => (
                <PackageCard
                  key={pkg.package_id}
                  pkg={pkg}
                  onAction={handleAction}
                  loading={actionLoading}
                  error={actionError}
                  errorMsg={actionErrorMsg}
                />
              ))
            )}
          </>
        )}

        {!loading && tab === "operations" && (
          <>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 10,
              }}
            >
              <span style={{ fontSize: 12, color: "#6b7280" }}>
                {statsTotal} total operations · auto-refreshes every 30s
              </span>
              <button
                onClick={() => void fetchOperations()}
                style={{
                  padding: "4px 10px",
                  background: "#1e2229",
                  border: "1px solid #2d3340",
                  borderRadius: 4,
                  color: "#9ca3af",
                  fontSize: 11,
                  cursor: "pointer",
                }}
              >
                Refresh
              </button>
            </div>
            {operations.length === 0 ? (
              <div style={{ color: "#6b7280", fontSize: 13, textAlign: "center", marginTop: 40 }}>
                No operations recorded yet.
              </div>
            ) : (
              operations.map((op) => (
                <div
                  key={op.id}
                  style={{
                    background: "#1e2229",
                    border: "1px solid #2d3340",
                    borderRadius: 6,
                    padding: "10px 14px",
                    marginBottom: 8,
                    fontSize: 12,
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 8,
                    }}
                  >
                    <span style={{ color: "#e5e7eb", fontWeight: 600 }}>{op.package_id}</span>
                    <span
                      style={{
                        padding: "1px 7px",
                        borderRadius: 10,
                        background: opStatusColor(op.status),
                        color: "#fff",
                        fontSize: 10,
                        fontWeight: 600,
                      }}
                    >
                      {op.status}
                    </span>
                  </div>
                  <div style={{ color: "#9ca3af", marginTop: 4 }}>
                    {op.operation}{op.message ? ` · ${op.message}` : ""}
                  </div>
                  <div style={{ color: "#4b5563", marginTop: 2, fontSize: 11 }}>
                    {new Date(op.started_at).toLocaleString()}
                  </div>
                </div>
              ))
            )}
          </>
        )}

        {!loading && tab === "developer" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <section style={{ background: "#1e2229", border: "1px solid #2d3340", borderRadius: 8, padding: 16 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                <div>
                  <div style={{ fontWeight: 700, color: "#e5e7eb" }}>Installed SDK Apps</div>
                  <div style={{ fontSize: 11, color: "#9ca3af" }}>Start, stop, or uninstall sandboxed apps</div>
                </div>
                <button onClick={() => void fetchSdkApps()} style={{ padding: "4px 10px", background: "#374151", border: "none", borderRadius: 4, color: "#e5e7eb", fontSize: 11, cursor: "pointer" }}>Refresh</button>
              </div>
              {sdkApps.length === 0 ? (
                <div style={{ color: "#6b7280", fontSize: 13 }}>No SDK apps installed yet.</div>
              ) : (
                <div style={{ display: "grid", gap: 8 }}>
                  {sdkApps.map((sdkApp) => (
                    <div key={sdkApp.app_id} style={{ background: "#13161b", border: "1px solid #2d3340", borderRadius: 6, padding: 12 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "flex-start" }}>
                        <div>
                          <div style={{ color: "#e5e7eb", fontWeight: 600 }}>{sdkApp.display_name}</div>
                          <div style={{ fontSize: 11, color: "#9ca3af" }}>{sdkApp.version} · {sdkApp.author}</div>
                          <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 4 }}>{sdkApp.capabilities.join(", ")}</div>
                        </div>
                        <span style={{ padding: "2px 8px", borderRadius: 10, fontSize: 10, color: "#fff", background: sdkApp.status === "running" ? "#10b981" : sdkApp.status === "error" ? "#ef4444" : "#6b7280" }}>{sdkApp.status}</span>
                      </div>
                      <div style={{ marginTop: 10 }}>
                        <button onClick={() => void handleSdkAction(sdkApp.app_id, "start")} disabled={sdkActionLoading !== null} style={{ marginRight: 6, padding: "4px 10px", border: "none", borderRadius: 4, background: "#2563eb", color: "#fff", cursor: "pointer" }}>Start</button>
                        <button onClick={() => void handleSdkAction(sdkApp.app_id, "stop")} disabled={sdkActionLoading !== null} style={{ marginRight: 6, padding: "4px 10px", border: "none", borderRadius: 4, background: "#d97706", color: "#fff", cursor: "pointer" }}>Stop</button>
                        <button onClick={() => void handleSdkAction(sdkApp.app_id, "delete")} disabled={sdkActionLoading !== null} style={{ padding: "4px 10px", border: "none", borderRadius: 4, background: "#ef4444", color: "#fff", cursor: "pointer" }}>Uninstall</button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section style={{ background: "#1e2229", border: "1px solid #2d3340", borderRadius: 8, padding: 16 }}>
              <div style={{ fontWeight: 700, color: "#e5e7eb", marginBottom: 4 }}>Install New SDK App</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <div>
                  <div style={{ fontSize: 12, color: "#9ca3af", marginBottom: 6 }}>Install from Manifest URL</div>
                  <input value={sdkInstallUrl} onChange={(e) => setSdkInstallUrl(e.target.value)} placeholder="https://example.com/my-app/kryos.app.json" style={{ width: "100%", padding: "6px 10px", background: "#13161b", border: "1px solid #2d3340", borderRadius: 6, color: "#e5e7eb" }} />
                  <div style={{ fontSize: 11, color: "#6b7280", marginTop: 6 }}>The manifest must be a valid kryos.app.json file. All permissions will be shown before installation.</div>
                  <button onClick={() => void validateManifestUrl()} style={{ marginTop: 8, padding: "6px 12px", border: "none", borderRadius: 4, background: "#2563eb", color: "#fff", cursor: "pointer" }}>Install</button>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: "#9ca3af", marginBottom: 6 }}>Paste Manifest JSON</div>
                  <textarea value={sdkManifestJson} onChange={(e) => setSdkManifestJson(e.target.value)} rows={8} style={{ width: "100%", padding: 10, background: "#13161b", border: "1px solid #2d3340", borderRadius: 6, color: "#e5e7eb", fontFamily: "monospace" }} />
                  <button onClick={() => void validateManifestJson()} style={{ marginTop: 8, padding: "6px 12px", border: "none", borderRadius: 4, background: "#7c3aed", color: "#fff", cursor: "pointer" }}>Validate & Install</button>
                </div>
              </div>
              {sdkInstallState !== "idle" && <div style={{ marginTop: 10, fontSize: 12, color: sdkInstallState === "error" ? "#fca5a5" : "#9ca3af" }}>{sdkInstallMessage || sdkInstallState}</div>}
              {sdkInstallErrors.length > 0 && <div style={{ marginTop: 8, fontSize: 12, color: "#fca5a5" }}>{sdkInstallErrors.join(" · ")}</div>}
            </section>

            <section style={{ background: "#1e2229", border: "1px solid #2d3340", borderRadius: 8, padding: 16 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                <div>
                  <div style={{ fontWeight: 700, color: "#e5e7eb" }}>Active Capabilities</div>
                  <div style={{ fontSize: 11, color: "#9ca3af" }}>What Kryos agent can delegate to your apps right now</div>
                </div>
                <button onClick={() => void fetchSdkCapabilities()} style={{ padding: "4px 10px", background: "#374151", border: "none", borderRadius: 4, color: "#e5e7eb", fontSize: 11, cursor: "pointer" }}>Refresh</button>
              </div>
              {sdkCapabilities.length === 0 ? (
                <div style={{ color: "#6b7280", fontSize: 13 }}>No running SDK apps — install and start an app to see its capabilities here</div>
              ) : (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  {sdkCapabilities.map((entry) => (
                    <span key={`${entry.app_id}:${entry.capability}`} style={{ background: colorFromId(entry.app_id), color: "#fff", padding: "4px 10px", borderRadius: 999, fontSize: 11 }}>
                      {entry.capability} from app {entry.app_name}
                    </span>
                  ))}
                </div>
              )}
            </section>
          </div>
        )}

        {tab === "developer" && sdkInstallState === "permission-review" && sdkPendingManifest && (
          <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "grid", placeItems: "center", zIndex: layerZIndex + 1 }}>
            <div style={{ width: 420, background: "#13161b", border: "1px solid #2d3340", borderRadius: 12, padding: 18 }}>
              <div style={{ fontWeight: 700, color: "#e5e7eb", marginBottom: 8 }}>Grant these permissions?</div>
              <div style={{ fontSize: 12, color: "#9ca3af", marginBottom: 12 }}>{String(sdkPendingManifest.display_name ?? sdkPendingManifest.name ?? "SDK app")}</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 16 }}>
                {sdkPendingPermissions.map((permission) => (
                  <span key={permission} style={{ padding: "4px 8px", borderRadius: 999, background: "#1e2229", color: "#e5e7eb", fontSize: 11 }}>{permission}</span>
                ))}
              </div>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
                <button onClick={() => { setSdkInstallState("idle"); setSdkPendingManifest(null); setSdkPendingPermissions([]); }} style={{ padding: "6px 12px", border: "1px solid #2d3340", borderRadius: 6, background: "transparent", color: "#9ca3af", cursor: "pointer" }}>Cancel</button>
                <button onClick={() => void completeSdkInstall()} style={{ padding: "6px 12px", border: "none", borderRadius: 6, background: "#2563eb", color: "#fff", cursor: "pointer" }}>Install</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </dialog>
  );
}

