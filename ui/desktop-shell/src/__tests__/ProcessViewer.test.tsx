import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProcessViewer } from "../apps/ProcessViewer";

describe("ProcessViewer", () => {
  it("renders launch form and app name input", () => {
    render(<ProcessViewer />);
    expect(screen.getByPlaceholderText(/app name/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /launch/i })).toBeInTheDocument();
  });

  it("launch button is disabled when input is empty", () => {
    render(<ProcessViewer />);
    expect(screen.getByRole("button", { name: /launch/i })).toBeDisabled();
  });

  it("renders process list from API", async () => {
    render(<ProcessViewer />);
    await waitFor(() => {
      expect(screen.getByText("firefox")).toBeInTheDocument();
    });
  });

  it("shows PID column header", () => {
    render(<ProcessViewer />);
    expect(screen.getByText("PID")).toBeInTheDocument();
  });

  it("kill button appears for each process", async () => {
    render(<ProcessViewer />);
    await waitFor(() => expect(screen.getByText("firefox")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /kill/i })).toBeInTheDocument();
  });

  it("clicking kill once shows confirm prompt", async () => {
    render(<ProcessViewer />);
    await waitFor(() => expect(screen.getByText("firefox")).toBeInTheDocument());
    const killBtn = screen.getByRole("button", { name: /kill/i });
    fireEvent.click(killBtn);
    await waitFor(() => {
      expect(screen.getByText(/confirm\?/i)).toBeInTheDocument();
    });
  });

  it("renders cpu% and memory columns", async () => {
    render(<ProcessViewer />);
    await waitFor(() => expect(screen.getByText("firefox")).toBeInTheDocument());
    expect(screen.getByText("CPU%")).toBeInTheDocument();
    expect(screen.getByText("Mem MB")).toBeInTheDocument();
  });
});
