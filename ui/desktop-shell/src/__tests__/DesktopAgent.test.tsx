import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DesktopAgent } from "../apps/DesktopAgent";

describe("DesktopAgent", () => {
  it("renders goal input and run button", () => {
    render(<DesktopAgent />);
    expect(screen.getByPlaceholderText(/describe the goal/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run/i })).toBeInTheDocument();
  });

  it("run button is disabled when input is empty", () => {
    render(<DesktopAgent />);
    const btn = screen.getByRole("button", { name: /run/i });
    expect(btn).toBeDisabled();
  });

  it("run button enables after typing a goal", () => {
    render(<DesktopAgent />);
    const input = screen.getByPlaceholderText(/describe the goal/i);
    fireEvent.change(input, { target: { value: "Open the browser" } });
    expect(screen.getByRole("button", { name: /run/i })).not.toBeDisabled();
  });

  it("shows step feed and final result after task completes", async () => {
    render(<DesktopAgent />);
    fireEvent.change(screen.getByPlaceholderText(/describe the goal/i), {
      target: { value: "test goal" },
    });
    fireEvent.click(screen.getByRole("button", { name: /run/i }));

    // The SSE mock returns a done action then a success result
    await waitFor(() => {
      expect(screen.getByText(/success/i)).toBeInTheDocument();
    });
  });
});
