import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ModelManager } from "../apps/ModelManager";

describe("ModelManager", () => {
  it("calls pull API and shows progress", async () => {
    render(<ModelManager />);

    fireEvent.change(screen.getByPlaceholderText("HuggingFace ID or GitHub URL"), {
      target: { value: "hf://Qwen/Qwen3-30B-A3B" },
    });
    fireEvent.click(screen.getByText("Pull"));

    await waitFor(() => {
      expect(screen.getByText(/Pull status:/)).toHaveTextContent("ready");
    });

    expect(screen.getByText("lumyn-agent.gguf")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Set as Default"));

    fireEvent.click(screen.getByText("Delete"));
    fireEvent.click(screen.getByText("Confirm Delete"));
  });
});
