import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { SettingsApp } from "../apps/Settings";

describe("Settings", () => {
  it("renders sidebar navigation", () => {
    render(<SettingsApp />);
    expect(screen.getByText("General")).toBeTruthy();
    expect(screen.getByText("Appearance")).toBeTruthy();
    expect(screen.getByText("AI")).toBeTruthy();
    expect(screen.getByText("Privacy")).toBeTruthy();
    expect(screen.getByText("About")).toBeTruthy();
  });

  it("shows General panel by default", () => {
    render(<SettingsApp />);
    expect(screen.getByText(/Wallpaper/i)).toBeTruthy();
  });

  it("switches to Appearance panel", () => {
    render(<SettingsApp />);
    fireEvent.click(screen.getByText("Appearance"));
    expect(screen.getByText(/Dark/i)).toBeTruthy();
  });

  it("switches to AI panel and shows model selector", async () => {
    render(<SettingsApp />);
    fireEvent.click(screen.getByText("AI"));
    await waitFor(() => {
      expect(screen.getByText(/Temperature/i)).toBeTruthy();
    });
  });

  it("switches to Privacy panel and shows cloud toggle", () => {
    render(<SettingsApp />);
    fireEvent.click(screen.getByText("Privacy"));
    expect(screen.getByText(/Cloud Inference/i)).toBeTruthy();
  });

  it("switches to About panel and shows version info", () => {
    render(<SettingsApp />);
    fireEvent.click(screen.getByText("About"));
    expect(screen.getByText(/PradyOS/i)).toBeTruthy();
  });

  it("calls onWallpaperChange when Apply is clicked in General", async () => {
    const onChange = vi.fn();
    render(<SettingsApp onWallpaperChange={onChange} />);
    const input = screen.getByPlaceholderText(/https:\/\//i);
    fireEvent.change(input, { target: { value: "https://example.com/bg.jpg" } });
    fireEvent.click(screen.getByText(/Apply/i));
    expect(onChange).toHaveBeenCalledWith("https://example.com/bg.jpg", expect.any(Boolean));
  });
});
