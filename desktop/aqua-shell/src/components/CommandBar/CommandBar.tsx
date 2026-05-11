import { useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";

interface Props {
  onClose: () => void;
}

type Status = "idle" | "submitting" | "success" | "error";

// ── Pure helpers – exported for unit tests ──────────────────────────────────

/** Build the payload sent to the workflow-engine task queue. */
export function buildTaskGoal(raw: string): string {
  return raw.trim();
}

// ── Component ────────────────────────────────────────────────────────────────

export default function CommandBar({ onClose }: Readonly<Props>) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [message, setMessage] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const goal = buildTaskGoal(inputRef.current?.value ?? "");
    if (!goal) return;

    setStatus("submitting");
    setMessage("Sending to Kryos AI…");

    try {
      const taskId = await invoke<string>("submit_task_cmd", { goal });
      setStatus("success");
      setMessage(`Task queued → ${taskId}`);
      // Auto-close after showing the success message
      setTimeout(onClose, 2_000);
    } catch (err) {
      setStatus("error");
      setMessage(`Error: ${String(err)}`);
    }
  };

  const statusColor: Record<Status, string> = {
    idle:       "var(--text-secondary)",
    submitting: "var(--accent)",
    success:    "#34C759",
    error:      "#FF3B30",
  };

  return (
    <div className="cmdbar-wrapper glass">
      <form className="cmdbar__input-row" onSubmit={handleSubmit}>
        <span className="cmdbar__prefix">⌘R</span>
        <input
          ref={inputRef}
          className="cmdbar__input"
          type="text"
          placeholder='Try: "Open Firefox and go to github.com"'
          autoFocus
          disabled={status === "submitting"}
          spellCheck={false}
        />
      </form>
      {message && (
        <p className="cmdbar__status" style={{ color: statusColor[status] }}>
          {message}
        </p>
      )}
    </div>
  );
}
