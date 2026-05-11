import { useMemo, useState } from "react";

export interface UserProfile {
  username: string;
  role: "admin" | "operator" | "guest";
  persona_id?: string | null;
  model_id?: string | null;
  theme?: string | null;
  voice?: string | null;
}

interface LoginSuccess {
  access_token: string;
  refresh_token: string;
  user: UserProfile;
}

interface Props {
  switching?: boolean;
  onLoginSuccess: (payload: LoginSuccess) => void;
  onCancel?: () => void;
}

export default function LoginScreen({ switching = false, onLoginSuccess, onCancel }: Readonly<Props>): JSX.Element {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = useMemo(() => username.trim().length > 0 && password.length > 0 && !busy, [busy, password.length, username]);

  const submit = async (): Promise<void> => {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username.trim(), password }),
      });

      if (resp.status === 401) {
        setError("Wrong username or password.");
        return;
      }
      if (resp.status === 423) {
        setError("This account is locked.");
        return;
      }
      if (resp.status >= 500) {
        setError("Authentication service unavailable.");
        return;
      }
      if (!resp.ok) {
        const message = await resp.text();
        setError(message || "Sign in failed.");
        return;
      }

      const payload = (await resp.json()) as LoginSuccess;
      onLoginSuccess(payload);
      setPassword("");
    } catch {
      setError("Authentication service unavailable.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 20000,
        background: "radial-gradient(circle at 20% 20%, rgba(88, 116, 255, 0.25), transparent 45%), radial-gradient(circle at 80% 10%, rgba(26, 188, 156, 0.22), transparent 40%), linear-gradient(140deg, #0F111A, #1E2030)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        backdropFilter: "blur(14px)",
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          void submit();
        }
        if (event.key === "Escape" && switching && onCancel) {
          onCancel();
        }
      }}
    >
      <div
        style={{
          width: 380,
          borderRadius: 22,
          border: "1px solid rgba(255,255,255,0.2)",
          background: "rgba(26, 28, 40, 0.7)",
          boxShadow: "0 18px 56px rgba(0,0,0,0.45)",
          padding: 28,
          color: "#F4F6FF",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 18 }}>
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: "50%",
              display: "grid",
              placeItems: "center",
              background: "linear-gradient(135deg, #1ABC9C, #3498DB)",
              fontWeight: 700,
              fontSize: 18,
            }}
          >
            {username.trim() ? username.trim().slice(0, 2).toUpperCase() : "RU"}
          </div>
          <div>
            <div style={{ fontSize: 21, fontWeight: 600 }}>Sign In</div>
            <div style={{ fontSize: 12, color: "#B5BED3" }}>{switching ? "Switch user" : "Prady OS"}</div>
          </div>
        </div>

        <label style={{ display: "block", fontSize: 12, marginBottom: 6, color: "#B5BED3" }}>Username</label>
        <input
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          autoFocus
          style={{ width: "100%", marginBottom: 12, borderRadius: 10, border: "1px solid rgba(255,255,255,0.2)", background: "rgba(5,7,14,0.6)", color: "#fff", padding: "10px 12px", outline: "none" }}
        />

        <label style={{ display: "block", fontSize: 12, marginBottom: 6, color: "#B5BED3" }}>Password</label>
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          style={{ width: "100%", marginBottom: 14, borderRadius: 10, border: "1px solid rgba(255,255,255,0.2)", background: "rgba(5,7,14,0.6)", color: "#fff", padding: "10px 12px", outline: "none" }}
        />

        {error ? <div style={{ fontSize: 12, color: "#FF9A9A", marginBottom: 10 }}>{error}</div> : null}

        <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
          {switching && onCancel ? (
            <button
              type="button"
              onClick={onCancel}
              disabled={busy}
              style={{ flex: 1, borderRadius: 10, border: "1px solid rgba(255,255,255,0.25)", background: "rgba(255,255,255,0.06)", color: "#fff", padding: "10px 12px", cursor: "pointer" }}
            >
              Cancel
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => void submit()}
            disabled={!canSubmit}
            style={{ flex: 1, borderRadius: 10, border: "none", background: canSubmit ? "linear-gradient(135deg, #00C2A8, #2D8CFF)" : "#4B5563", color: "#fff", padding: "10px 12px", cursor: canSubmit ? "pointer" : "not-allowed", fontWeight: 600 }}
          >
            {busy ? "Signing in..." : "Sign In"}
          </button>
        </div>
      </div>
    </div>
  );
}
