import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { DOCK_APPS, Dock } from "../components/Dock";

describe("Dock", () => {
  it("renders all apps and handles clicks", () => {
    const onOpenApp = vi.fn();
    render(<Dock runningApps={[]} onOpenApp={onOpenApp} />);

    DOCK_APPS.forEach((app) => {
      expect(screen.getByTestId(`dock-app-${app.appId}`)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("dock-app-terminal"));
    expect(onOpenApp).toHaveBeenCalledWith("terminal");
  });
});
