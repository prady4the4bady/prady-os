import { describe, it, expect } from "vitest";
import { DOCK_APPS } from "../src/components/Dock/Dock";

describe("DOCK_APPS configuration", () => {
  it("contains exactly 5 default apps", () => {
    expect(DOCK_APPS).toHaveLength(5);
  });

  it("every entry has a non-empty id, label, and icon", () => {
    for (const app of DOCK_APPS) {
      expect(app.id, `${app.id} missing id`).toBeTruthy();
      expect(app.label, `${app.id} missing label`).toBeTruthy();
      expect(app.icon, `${app.id} missing icon`).toBeTruthy();
    }
  });

  it("includes Terminal, Files, Browser, Kryos Tasks, and Settings", () => {
    const ids = DOCK_APPS.map((a) => a.id);
    expect(ids).toContain("terminal");
    expect(ids).toContain("files");
    expect(ids).toContain("browser");
    expect(ids).toContain("kryos_tasks");
    expect(ids).toContain("settings");
  });

  it("all ids are unique", () => {
    const ids = DOCK_APPS.map((a) => a.id);
    const unique = new Set(ids);
    expect(unique.size).toBe(ids.length);
  });

  it("all labels are unique", () => {
    const labels = DOCK_APPS.map((a) => a.label);
    const unique = new Set(labels);
    expect(unique.size).toBe(labels.length);
  });
});
