import { useMemo, useState } from "react";
import type { UserProfile } from "./LoginScreen";

interface Props {
  authToken: string;
  currentUser: UserProfile;
  onSwitchUser: () => void;
  onLogout: () => void;
}

function colorFromUsername(username: string): string {
  let hash = 0;
  for (let i = 0; i < username.length; i += 1) {
    hash = username.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash % 360);
  return `hsl(${hue}, 68%, 50%)`;
}

export default function UserSwitcher({ authToken, currentUser, onSwitchUser, onLogout }: Readonly<Props>): JSX.Element {
  const [open, setOpen] = useState(false);
  const [users, setUsers] = useState<UserProfile[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [newUsername, setNewUsername] = useState("");
  const [newRole, setNewRole] = useState<"admin" | "operator" | "guest">("guest");

  const initials = useMemo(() => currentUser.username.slice(0, 2).toUpperCase(), [currentUser.username]);

  const loadUsers = async (): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch("/users", {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (!resp.ok) {
        setUsers([currentUser]);
        if (resp.status !== 403) {
          setError("Failed to fetch users");
        }
        return;
      }
      const data = (await resp.json()) as { users?: UserProfile[] };
      setUsers(data.users ?? [currentUser]);
    } catch {
      setError("Failed to fetch users");
    } finally {
      setBusy(false);
    }
  };

  const addUser = async (): Promise<void> => {
    const username = newUsername.trim();
    if (!username) return;
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch(`/users/${encodeURIComponent(username)}/role`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({ role: newRole }),
      });
      if (!resp.ok) {
        setError("Failed to add user");
        return;
      }
      setShowAdd(false);
      setNewUsername("");
      await loadUsers();
    } catch {
      setError("Failed to add user");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ position: "fixed", top: 10, right: 14, zIndex: 12000 }}>
      <button
        type="button"
        title="User switcher"
        onClick={() => {
          const next = !open;
          setOpen(next);
          if (next) {
            void loadUsers();
          }
        }}
        style={{
          width: 34,
          height: 34,
          borderRadius: "50%",
          border: "1px solid rgba(255,255,255,0.35)",
          background: colorFromUsername(currentUser.username),
          color: "white",
          fontWeight: 700,
          cursor: "pointer",
        }}
      >
        {initials}
      </button>

      {open ? (
        <div
          style={{
            marginTop: 8,
            width: 280,
            borderRadius: 12,
            border: "1px solid rgba(255,255,255,0.2)",
            background: "rgba(24,25,32,0.92)",
            color: "#F2F2F7",
            padding: 10,
            backdropFilter: "blur(14px)",
          }}
        >
          <div style={{ fontSize: 12, color: "#B3B9CF", marginBottom: 8 }}>Signed in as {currentUser.username} ({currentUser.role})</div>

          {busy ? <div style={{ fontSize: 12, color: "#B3B9CF" }}>Loading...</div> : null}
          {error ? <div style={{ fontSize: 12, color: "#FF9A9A", marginBottom: 6 }}>{error}</div> : null}

          {users.map((user) => (
            <div
              key={user.username}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "6px 8px",
                borderRadius: 8,
                background: user.username === currentUser.username ? "rgba(10,132,255,0.25)" : "transparent",
                marginBottom: 4,
              }}
            >
              <span style={{ fontSize: 13 }}>{user.username}</span>
              <span style={{ fontSize: 11, color: "#B3B9CF" }}>{user.role}</span>
            </div>
          ))}

          <div style={{ display: "grid", gap: 6, marginTop: 8 }}>
            <button type="button" onClick={onSwitchUser} style={{ borderRadius: 8, border: "none", padding: "8px 10px", background: "#2D8CFF", color: "white", cursor: "pointer" }}>
              Switch User
            </button>
            <button type="button" onClick={onLogout} style={{ borderRadius: 8, border: "1px solid rgba(255,255,255,0.3)", padding: "8px 10px", background: "transparent", color: "white", cursor: "pointer" }}>
              Log Out
            </button>
            {currentUser.role === "admin" ? (
              <button type="button" onClick={() => setShowAdd((prev) => !prev)} style={{ borderRadius: 8, border: "1px dashed rgba(255,255,255,0.35)", padding: "8px 10px", background: "transparent", color: "#B3E2FF", cursor: "pointer" }}>
                Add User
              </button>
            ) : null}
          </div>

          {showAdd ? (
            <div style={{ marginTop: 10, padding: 8, borderRadius: 8, border: "1px solid rgba(255,255,255,0.2)", display: "grid", gap: 6 }}>
              <input
                value={newUsername}
                onChange={(event) => setNewUsername(event.target.value)}
                placeholder="username"
                style={{ borderRadius: 6, border: "1px solid rgba(255,255,255,0.2)", background: "rgba(0,0,0,0.3)", color: "white", padding: "8px" }}
              />
              <select
                value={newRole}
                onChange={(event) => setNewRole(event.target.value as "admin" | "operator" | "guest")}
                style={{ borderRadius: 6, border: "1px solid rgba(255,255,255,0.2)", background: "rgba(0,0,0,0.3)", color: "white", padding: "8px" }}
              >
                <option value="guest">guest</option>
                <option value="operator">operator</option>
                <option value="admin">admin</option>
              </select>
              <button type="button" onClick={() => void addUser()} style={{ borderRadius: 6, border: "none", padding: "8px", background: "#16A085", color: "white", cursor: "pointer" }}>
                Save User
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
