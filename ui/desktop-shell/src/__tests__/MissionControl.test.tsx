import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MissionControl } from "../components/MissionControl";
import type { WindowItem } from "../types";

const WINDOWS: WindowItem[] = [
  { id: "w1", appId: "assistant", title: "AI Assistant", x: 0, y: 0, width: 800, height: 600, minimized: false, maximized: false, zIndex: 1, icon: "🤖" },
  { id: "w2", appId: "terminal",  title: "Terminal",     x: 0, y: 0, width: 800, height: 600, minimized: false, maximized: false, zIndex: 2, icon: "💻" },
];

describe("MissionControl", () => {
  it("renders all window cards", () => {
    render(<MissionControl windows={WINDOWS} onBringToFront={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByText("AI Assistant")).toBeTruthy();
    expect(screen.getByText("Terminal")).toBeTruthy();
  });

  it("calls onBringToFront when a card is clicked", () => {
    const onBringToFront = vi.fn();
    render(<MissionControl windows={WINDOWS} onBringToFront={onBringToFront} onClose={vi.fn()} />);
    fireEvent.click(screen.getByText("AI Assistant"));
    expect(onBringToFront).toHaveBeenCalledWith("w1");
  });

  it("calls onClose after bringing window to front", () => {
    const onClose = vi.fn();
    render(<MissionControl windows={WINDOWS} onBringToFront={vi.fn()} onClose={onClose} />);
    fireEvent.click(screen.getByText("Terminal"));
    expect(onClose).toHaveBeenCalled();
  });

  it("calls onClose when background is clicked", () => {
    const onClose = vi.fn();
    const { container } = render(
      <MissionControl windows={WINDOWS} onBringToFront={vi.fn()} onClose={onClose} />
    );
    fireEvent.click(container.firstElementChild as HTMLElement);
    expect(onClose).toHaveBeenCalled();
  });

  it("renders empty state without crashing", () => {
    render(<MissionControl windows={[]} onBringToFront={vi.fn()} onClose={vi.fn()} />);
  });
});
