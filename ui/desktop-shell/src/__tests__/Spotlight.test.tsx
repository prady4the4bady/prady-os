import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { Spotlight } from "../components/Spotlight";

describe("Spotlight", () => {
  it("submits task to swarm API", async () => {
    const onSwarmStarted = vi.fn();
    render(
      <Spotlight
        open
        onClose={() => void 0}
        onSwarmStarted={onSwarmStarted}
        swarms={[]}
      />
    );

    fireEvent.change(screen.getByPlaceholderText("What do you want me to do?"), {
      target: { value: "Plan my day" },
    });
    const form = screen.getByPlaceholderText("What do you want me to do?").closest("form");
    if (!form) {
      throw new Error("Expected spotlight form to exist");
    }
    fireEvent.submit(form);

    await waitFor(() => {
      expect(onSwarmStarted).toHaveBeenCalledWith("swarm-test-1");
    });
  });
});
