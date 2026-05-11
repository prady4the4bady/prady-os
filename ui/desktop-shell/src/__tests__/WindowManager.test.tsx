import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { WindowManager } from "../components/WindowManager";
import type { WindowItem } from "../types";

describe("WindowManager", () => {
  it("opens, focuses, and closes windows", () => {
    const onFocus = vi.fn();
    const onClose = vi.fn();
    const onMinimize = vi.fn();
    const onMaximize = vi.fn();
    const onMoveResize = vi.fn();

    const windows: WindowItem[] = [
      {
        id: "w1",
        appId: "assistant",
        title: "AI Assistant",
        icon: "🤖",
        x: 100,
        y: 100,
        width: 500,
        height: 400,
        zIndex: 100,
        minimized: false,
        maximized: false,
      },
    ];

    render(
      <WindowManager
        windows={windows}
        activeWindowId={"w1"}
        onFocus={onFocus}
        onClose={onClose}
        onMinimize={onMinimize}
        onMaximize={onMaximize}
        onMoveResize={onMoveResize}
        renderWindow={() => <div>content</div>}
      />
    );

    fireEvent.mouseDown(screen.getByText("AI Assistant"));
    expect(onFocus).toHaveBeenCalledWith("w1");

    fireEvent.click(screen.getByLabelText("close"));
    expect(onClose).toHaveBeenCalledWith("w1");
  });
});
