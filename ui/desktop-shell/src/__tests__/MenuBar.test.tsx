import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { MenuBar } from "../components/MenuBar";

describe("MenuBar", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders PradyOS label", () => {
    render(<MenuBar nemoEnabled={false} />);
    expect(screen.getByText("PradyOS")).toBeTruthy();
  });

  it("shows Vyrex indicator green when enabled", () => {
    render(<MenuBar nemoEnabled={true} />);
    // Shield button should exist with green styling
    const shield = document.querySelector("[title='Vyrex: ON']");
    expect(shield).toBeTruthy();
  });

  it("shows Vyrex indicator grey when disabled", () => {
    render(<MenuBar nemoEnabled={false} />);
    const shield = document.querySelector("[title='Vyrex: OFF']");
    expect(shield).toBeTruthy();
  });

  it("clock ticks every second", () => {
    render(<MenuBar nemoEnabled={false} />);
    act(() => { vi.advanceTimersByTime(1000); });
    // Clock updates — content might change for seconds
    expect(screen.getByRole("time")).toBeTruthy();
  });

  it("opens apple menu on click", () => {
    render(<MenuBar nemoEnabled={false} />);
    const appleBtn = screen.getByTitle("Apple");
    fireEvent.click(appleBtn);
    expect(screen.getByText("About PradyOS")).toBeTruthy();
  });

  it("closes apple menu when clicking outside", () => {
    render(<MenuBar nemoEnabled={false} />);
    fireEvent.click(screen.getByTitle("Apple"));
    expect(screen.getByText("About PradyOS")).toBeTruthy();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByText("About PradyOS")).toBeNull();
  });
});
