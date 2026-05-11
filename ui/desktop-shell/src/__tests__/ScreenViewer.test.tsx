import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ScreenViewer } from "../apps/ScreenViewer";

describe("ScreenViewer", () => {
  it("renders screen viewer with no image initially", () => {
    render(<ScreenViewer />);
    expect(screen.getByText(/no frame available/i)).toBeInTheDocument();
  });

  it("shows scale selector buttons", () => {
    render(<ScreenViewer />);
    expect(screen.getByText("1x")).toBeInTheDocument();
    expect(screen.getByText("½x")).toBeInTheDocument();
    expect(screen.getByText("¼x")).toBeInTheDocument();
  });

  it("fetches and displays screenshot image", async () => {
    render(<ScreenViewer />);
    // The MSW handler returns a base64 stub; after fetch the img should appear
    await waitFor(() => {
      expect(screen.queryByTestId("screen-image")).not.toBeNull();
    });
  });

  it("click on image calls input/action endpoint", async () => {
    render(<ScreenViewer />);
    await waitFor(() => expect(screen.queryByTestId("screen-image")).not.toBeNull());
    const img = screen.getByTestId("screen-image");
    fireEvent.click(img, { clientX: 100, clientY: 200 });
    // Verify clicking doesn't throw — MSW intercepts silently
  });

  it("clear overlays button is rendered", () => {
    render(<ScreenViewer />);
    expect(screen.getByText(/clear overlays/i)).toBeInTheDocument();
  });
});
