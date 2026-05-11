import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Bell, CheckCheck, X, CheckCircle, AlertTriangle, AlertCircle, Info } from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Notification {
  id: string;
  type: string;
  title: string;
  body: string;
  source: string;
  severity: string;
  read: boolean;
  created_at: string;
}

interface Toast {
  id: string;
  notification: Notification;
  dismissAt: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function relativeTime(isoStr: string): string {
  const ms = Date.now() - new Date(isoStr).getTime();
  const sec = Math.floor(ms / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  return `${Math.floor(hr / 24)}d ago`;
}

function severityColor(severity: string): string {
  switch (severity) {
    case 'success': return '#30D158';
    case 'error': return '#FF453A';
    case 'warning': return '#FFD60A';
    default: return '#0A84FF';
  }
}

function SeverityIcon({ severity }: Readonly<{ severity: string }>): React.ReactElement {
  const size = 14;
  const color = severityColor(severity);
  switch (severity) {
    case 'success': return <CheckCircle size={size} color={color} />;
    case 'error': return <AlertCircle size={size} color={color} />;
    case 'warning': return <AlertTriangle size={size} color={color} />;
    default: return <Info size={size} color={color} />;
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const FONT = "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif";
const API_BASE = 'http://localhost:8100/api/notifications';
const TOAST_MAX = 3;
const TOAST_TTL = 3000;

interface NotificationCenterProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  layerZIndex?: number;
}

export default function NotificationCenter({
  open,
  onOpenChange,
  layerZIndex,
}: Readonly<NotificationCenterProps>): React.ReactElement {
  const [internalOpen, setInternalOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const esRef = useRef<EventSource | null>(null);
  const toastTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const isControlled = open !== undefined;
  const isOpen = isControlled ? open : internalOpen;
  const baseZIndex = layerZIndex ?? 9000;

  const setOpenState = useCallback((next: boolean): void => {
    if (!isControlled) {
      setInternalOpen(next);
    }
    onOpenChange?.(next);
  }, [isControlled, onOpenChange]);

  const removeToast = useCallback((toastId: string): void => {
    setToasts((prev) => prev.filter((toast) => toast.id !== toastId));
  }, []);

  // -----------------------------------------------------------------------
  // Fetch initial notifications
  // -----------------------------------------------------------------------

  const fetchNotifications = useCallback(async (): Promise<void> => {
    try {
      const res = await fetch(`${API_BASE}/notification?limit=100`);
      if (!res.ok) return;
      const data = (await res.json()) as { notifications: Notification[]; total: number };
      setNotifications(data.notifications);
      setUnreadCount(data.notifications.filter((n) => !n.read).length);
    } catch {
      // ignore fetch errors silently
    }
  }, []);

  // -----------------------------------------------------------------------
  // SSE subscription
  // -----------------------------------------------------------------------

  useEffect(() => {
    void fetchNotifications();

    const es = new EventSource(`${API_BASE}/stream`);
    esRef.current = es;

    es.onmessage = (evt): void => {
      try {
        const notif = JSON.parse(evt.data as string) as Notification;
        setNotifications((prev) => [notif, ...prev]);
        setUnreadCount((c) => c + 1);
        addToast(notif);
      } catch {
        // ignore malformed events
      }
    };

    return (): void => {
      es.close();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // -----------------------------------------------------------------------
  // Toast helpers
  // -----------------------------------------------------------------------

  const addToast = useCallback((notif: Notification): void => {
    const toast: Toast = { id: notif.id, notification: notif, dismissAt: Date.now() + TOAST_TTL };
    setToasts((prev) => {
      const next = [toast, ...prev].slice(0, TOAST_MAX);
      return next;
    });
    const timer = globalThis.setTimeout(() => {
      removeToast(toast.id);
      toastTimers.current.delete(toast.id);
    }, TOAST_TTL);
    toastTimers.current.set(toast.id, timer);
  }, [removeToast]);

  const dismissToast = useCallback((toastId: string): void => {
    const timer = toastTimers.current.get(toastId);
    if (timer !== undefined) {
      globalThis.clearTimeout(timer);
      toastTimers.current.delete(toastId);
    }
    removeToast(toastId);
  }, [removeToast]);

  // -----------------------------------------------------------------------
  // Actions
  // -----------------------------------------------------------------------

  const markAllRead = useCallback(async (): Promise<void> => {
    try {
      await fetch(`${API_BASE}/notification/read-all`, { method: 'POST' });
      setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
      setUnreadCount(0);
    } catch {
      // ignore
    }
  }, []);

  const markOneRead = useCallback(async (id: string): Promise<void> => {
    try {
      await fetch(`${API_BASE}/notification/${id}/read`, { method: 'PATCH' });
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, read: true } : n)),
      );
      setUnreadCount((c) => Math.max(0, c - 1));
    } catch {
      // ignore
    }
  }, []);

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  return (
    <>
      {/* Bell button */}
      <button
        type="button"
        onClick={() => setOpenState(!isOpen)}
        style={{
          position: 'fixed',
          top: 12,
          right: 16,
          zIndex: baseZIndex + 2,
          background: 'rgba(28,28,30,0.85)',
          backdropFilter: 'blur(12px)',
          WebkitBackdropFilter: 'blur(12px)',
          border: '1px solid rgba(58,58,60,0.7)',
          borderRadius: 10,
          padding: '6px 10px',
          color: '#F2F2F7',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          fontFamily: FONT,
          fontSize: 11,
        }}
      >
        <Bell size={14} />
        {unreadCount > 0 && (
          <span
            style={{
              background: '#FF453A',
              color: '#fff',
              borderRadius: '50%',
              width: 16,
              height: 16,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 10,
              fontWeight: 700,
            }}
          >
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {/* Slide-in panel */}
      {isOpen && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            right: 0,
            width: 360,
            height: '100vh',
            zIndex: baseZIndex + 1,
            background: 'rgba(18,18,20,0.95)',
            backdropFilter: 'blur(20px)',
            WebkitBackdropFilter: 'blur(20px)',
            borderLeft: '1px solid rgba(58,58,60,0.7)',
            display: 'flex',
            flexDirection: 'column',
            fontFamily: FONT,
            color: '#F2F2F7',
          }}
        >
          {/* Header */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '16px 16px 12px',
              borderBottom: '1px solid rgba(58,58,60,0.5)',
            }}
          >
            <span style={{ fontWeight: 600, fontSize: 15 }}>Notifications</span>
            <div style={{ display: 'flex', gap: 8 }}>
              {unreadCount > 0 && (
                <button
                  type="button"
                  onClick={() => void markAllRead()}
                  title="Mark all read"
                  style={{
                    background: 'none',
                    border: 'none',
                    color: '#0A84FF',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 4,
                    fontSize: 12,
                  }}
                >
                  <CheckCheck size={14} /> Mark all read
                </button>
              )}
              <button
                type="button"
                onClick={() => setOpenState(false)}
                style={{ background: 'none', border: 'none', color: '#8E8E93', cursor: 'pointer', padding: 4 }}
              >
                <X size={16} />
              </button>
            </div>
          </div>

          {/* List */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
            {notifications.length === 0 ? (
              <div
                style={{
                  textAlign: 'center',
                  color: '#636366',
                  fontSize: 13,
                  marginTop: 48,
                }}
              >
                No notifications
              </div>
            ) : (
              notifications.map((n) => (
                <button
                  type="button"
                  key={n.id}
                  onClick={() => { if (!n.read) void markOneRead(n.id); }}
                  style={{
                    padding: '10px 16px',
                    borderBottom: '1px solid rgba(58,58,60,0.3)',
                    cursor: n.read ? 'default' : 'pointer',
                    background: n.read ? 'transparent' : 'rgba(10,132,255,0.06)',
                    display: 'flex',
                    gap: 10,
                    alignItems: 'flex-start',
                    width: '100%',
                    textAlign: 'left',
                    border: 'none',
                  }}
                >
                  <div style={{ paddingTop: 2 }}>
                    <SeverityIcon severity={n.severity} />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 }}>
                      <span style={{ fontWeight: 600, fontSize: 13, color: n.read ? '#8E8E93' : '#F2F2F7' }}>
                        {n.title}
                      </span>
                      <span style={{ fontSize: 11, color: '#636366', whiteSpace: 'nowrap', marginLeft: 8 }}>
                        {relativeTime(n.created_at)}
                      </span>
                    </div>
                    {n.body && (
                      <div style={{ fontSize: 12, color: '#8E8E93', marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {n.body.slice(0, 100)}
                      </div>
                    )}
                    <span
                      style={{
                        fontSize: 10,
                        background: 'rgba(58,58,60,0.5)',
                        borderRadius: 4,
                        padding: '1px 6px',
                        color: '#8E8E93',
                      }}
                    >
                      {n.source}
                    </span>
                  </div>
                  {!n.read && (
                    <div
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background: '#0A84FF',
                        marginTop: 4,
                        flexShrink: 0,
                      }}
                    />
                  )}
                </button>
              ))
            )}
          </div>
        </div>
      )}

      {/* Click-outside overlay */}
      {isOpen && (
        <button
          type="button"
          aria-label="Close notifications"
          onClick={() => setOpenState(false)}
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: baseZIndex,
            border: 'none',
            background: 'transparent',
            cursor: 'default',
          }}
        />
      )}

      {/* Toast stack */}
      <div
        style={{
          position: 'fixed',
          bottom: 80,
          right: 16,
          zIndex: 300,
          display: 'flex',
          flexDirection: 'column-reverse',
          gap: 8,
          pointerEvents: 'none',
        }}
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            style={{
              background: 'rgba(28,28,30,0.95)',
              backdropFilter: 'blur(12px)',
              WebkitBackdropFilter: 'blur(12px)',
              border: '1px solid rgba(58,58,60,0.7)',
              borderLeft: `3px solid ${severityColor(toast.notification.severity)}`,
              borderRadius: 10,
              padding: '10px 14px',
              width: 300,
              fontFamily: FONT,
              color: '#F2F2F7',
              pointerEvents: 'all',
              display: 'flex',
              alignItems: 'flex-start',
              gap: 8,
            }}
          >
            <SeverityIcon severity={toast.notification.severity} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 2 }}>{toast.notification.title}</div>
              {toast.notification.body && (
                <div style={{ fontSize: 12, color: '#8E8E93', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {toast.notification.body.slice(0, 100)}
                </div>
              )}
            </div>
            <button
              type="button"
              onClick={() => dismissToast(toast.id)}
              style={{ background: 'none', border: 'none', color: '#636366', cursor: 'pointer', padding: 0, flexShrink: 0 }}
            >
              <X size={12} />
            </button>
          </div>
        ))}
      </div>
    </>
  );
}
