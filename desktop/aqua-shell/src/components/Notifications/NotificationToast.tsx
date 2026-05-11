import { useEffect, useState } from "react";
import type { Notification } from "../../types";

interface Props {
  notif: Notification;
  onDismiss: (id: string) => void;
}

export default function NotificationToast({ notif, onDismiss }: Readonly<Props>) {
  const [exiting, setExiting] = useState(false);

  // Auto-dismiss after duration_ms
  useEffect(() => {
    const timeout = setTimeout(() => {
      setExiting(true);
      // Wait for exit animation then remove
      setTimeout(() => onDismiss(notif.id), 250);
    }, notif.duration_ms);
    return () => clearTimeout(timeout);
  }, [notif.id, notif.duration_ms, onDismiss]);

  const handleDismiss = () => {
    setExiting(true);
    setTimeout(() => onDismiss(notif.id), 250);
  };

  return (
    <div
      role="alert"
      className={`notif-toast glass${exiting ? " notif-toast--exiting" : ""}`}
    >
      <div className="notif-toast__header">
        <span className="notif-toast__title">
          {notif.icon && <span style={{ marginRight: 6 }}>{notif.icon}</span>}
          {notif.title}
        </span>
        <button
          className="notif-toast__close"
          onClick={(e) => { e.stopPropagation(); handleDismiss(); }}
          aria-label="Dismiss notification"
        >
          ✕
        </button>
      </div>
      <p className="notif-toast__body">{notif.body}</p>
    </div>
  );
}
