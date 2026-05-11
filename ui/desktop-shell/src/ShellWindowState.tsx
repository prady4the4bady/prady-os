import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

export interface ShellWindowRecord {
  id: string;
  title: string;
  open: boolean;
  focused: boolean;
  zIndex: number;
  minimizable: boolean;
}

interface RegisterWindowInput {
  id: string;
  title: string;
  minimizable?: boolean;
}

interface ShellWindowStateContextValue {
  windows: ShellWindowRecord[];
  registerWindow: (input: RegisterWindowInput) => void;
  openWindow: (id: string) => void;
  closeWindow: (id: string) => void;
  focusWindow: (id: string) => void;
  toggleWindow: (id: string) => void;
  setWindowOpen: (id: string, open: boolean) => void;
  listOpenWindows: () => ShellWindowRecord[];
}

const ShellWindowStateContext = createContext<ShellWindowStateContextValue | null>(null);

export function ShellWindowStateProvider({ children }: Readonly<{ children: ReactNode }>): JSX.Element {
  const [windowsById, setWindowsById] = useState<Record<string, ShellWindowRecord>>({});
  const zCounterRef = useRef(9000);

  const registerWindow = useCallback((input: RegisterWindowInput): void => {
    setWindowsById((prev) => {
      const existing = prev[input.id];
      if (existing) {
        if (existing.title === input.title && existing.minimizable === (input.minimizable ?? true)) {
          return prev;
        }
        return {
          ...prev,
          [input.id]: {
            ...existing,
            title: input.title,
            minimizable: input.minimizable ?? true,
          },
        };
      }
      return {
        ...prev,
        [input.id]: {
          id: input.id,
          title: input.title,
          open: false,
          focused: false,
          zIndex: 0,
          minimizable: input.minimizable ?? true,
        },
      };
    });
  }, []);

  const focusWindow = useCallback((id: string): void => {
    zCounterRef.current += 1;
    setWindowsById((prev) => {
      if (!prev[id]) {
        return prev;
      }
      const next: Record<string, ShellWindowRecord> = {};
      for (const [key, value] of Object.entries(prev)) {
        if (key === id) {
          next[key] = { ...value, open: true, focused: true, zIndex: zCounterRef.current };
        } else {
          next[key] = value.focused ? { ...value, focused: false } : value;
        }
      }
      return next;
    });
  }, []);

  const openWindow = useCallback((id: string): void => {
    setWindowsById((prev) => {
      const existing = prev[id];
      if (!existing) {
        return prev;
      }
      if (existing.open && existing.focused) {
        return prev;
      }
      zCounterRef.current += 1;
      const next: Record<string, ShellWindowRecord> = {};
      for (const [key, value] of Object.entries(prev)) {
        if (key === id) {
          next[key] = { ...value, open: true, focused: true, zIndex: zCounterRef.current };
        } else {
          next[key] = value.focused ? { ...value, focused: false } : value;
        }
      }
      return next;
    });
  }, []);

  const closeWindow = useCallback((id: string): void => {
    setWindowsById((prev) => {
      const existing = prev[id];
      if (!existing || (!existing.open && !existing.focused)) {
        return prev;
      }
      return {
        ...prev,
        [id]: {
          ...existing,
          open: false,
          focused: false,
        },
      };
    });
  }, []);

  const setWindowOpen = useCallback((id: string, open: boolean): void => {
    if (open) {
      openWindow(id);
      return;
    }
    closeWindow(id);
  }, [closeWindow, openWindow]);

  const toggleWindow = useCallback((id: string): void => {
    setWindowsById((prev) => {
      const existing = prev[id];
      if (!existing) {
        return prev;
      }
      if (existing.open) {
        return {
          ...prev,
          [id]: {
            ...existing,
            open: false,
            focused: false,
          },
        };
      }
      zCounterRef.current += 1;
      const next: Record<string, ShellWindowRecord> = {};
      for (const [key, value] of Object.entries(prev)) {
        if (key === id) {
          next[key] = {
            ...value,
            open: true,
            focused: true,
            zIndex: zCounterRef.current,
          };
        } else {
          next[key] = value.focused ? { ...value, focused: false } : value;
        }
      }
      return next;
    });
  }, []);

  const windows = useMemo(
    () => Object.values(windowsById).sort((a, b) => b.zIndex - a.zIndex),
    [windowsById]
  );

  const listOpenWindows = useCallback((): ShellWindowRecord[] => {
    return Object.values(windowsById)
      .filter((windowRecord) => windowRecord.open)
      .sort((a, b) => b.zIndex - a.zIndex);
  }, [windowsById]);

  const value = useMemo<ShellWindowStateContextValue>(
    () => ({
      windows,
      registerWindow,
      openWindow,
      closeWindow,
      focusWindow,
      toggleWindow,
      setWindowOpen,
      listOpenWindows,
    }),
    [windows, registerWindow, openWindow, closeWindow, focusWindow, toggleWindow, setWindowOpen, listOpenWindows]
  );

  return <ShellWindowStateContext.Provider value={value}>{children}</ShellWindowStateContext.Provider>;
}

export function useShellWindowState(): ShellWindowStateContextValue {
  const context = useContext(ShellWindowStateContext);
  if (!context) {
    throw new Error("useShellWindowState must be used within ShellWindowStateProvider");
  }
  return context;
}
