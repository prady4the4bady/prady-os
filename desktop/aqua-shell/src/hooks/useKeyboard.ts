import { useEffect } from "react";

type Modifier = "ctrl" | "meta" | "alt" | "shift";

interface Shortcut {
  key: string;          // e.g. "r", " ", "Space"
  modifiers: Modifier[];
  handler: () => void;
}

export function useKeyboard(shortcuts: Shortcut[]) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      for (const s of shortcuts) {
        const keyMatch =
          e.key.toLowerCase() === s.key.toLowerCase() ||
          e.code.toLowerCase() === `key${s.key.toLowerCase()}`;
        const modMatch = s.modifiers.every((mod) => {
          switch (mod) {
            case "ctrl":  return e.ctrlKey;
            case "meta":  return e.metaKey;
            case "alt":   return e.altKey;
            case "shift": return e.shiftKey;
          }
        });
        if (keyMatch && modMatch) {
          e.preventDefault();
          s.handler();
          break;
        }
      }
    };
    globalThis.addEventListener("keydown", handleKeyDown);
    return () => globalThis.removeEventListener("keydown", handleKeyDown);
  }, [shortcuts]);
}
