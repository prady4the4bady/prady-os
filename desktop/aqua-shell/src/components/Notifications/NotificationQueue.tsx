import type { Notification } from "../../types";
import NotificationToast from "./NotificationToast";

interface Props {
  notifications: Notification[];
  onDismiss: (id: string) => void;
}

export default function NotificationQueue({ notifications, onDismiss }: Readonly<Props>) {
  if (notifications.length === 0) return null;

  return (
    <div className="notif-queue" aria-live="polite" aria-label="Notifications">
      {notifications.map((n) => (
        <NotificationToast key={n.id} notif={n} onDismiss={onDismiss} />
      ))}
    </div>
  );
}
