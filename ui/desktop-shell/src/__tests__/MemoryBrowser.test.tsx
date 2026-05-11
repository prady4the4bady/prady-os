import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MemoryBrowser } from "../apps/MemoryBrowser";

describe("MemoryBrowser", () => {
  it("renders search input and button", () => {
    render(<MemoryBrowser />);
    expect(screen.getByPlaceholderText(/search memories/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /search/i })).toBeInTheDocument();
  });

  it("search button is disabled when query is empty", () => {
    render(<MemoryBrowser />);
    expect(screen.getByRole("button", { name: /search/i })).toBeDisabled();
  });

  it("renders stats bar after loading", async () => {
    render(<MemoryBrowser />);
    await waitFor(() => {
      // The mock returns total_entries: 5
      expect(screen.getByText(/5/)).toBeInTheDocument();
    });
  });

  it("shows add button in stats bar", async () => {
    render(<MemoryBrowser />);
    await waitFor(() => expect(screen.getByText(/\+ add/i)).toBeInTheDocument());
  });

  it("opens add memory form on add button click", async () => {
    render(<MemoryBrowser />);
    await waitFor(() => screen.getByText(/\+ add/i));
    fireEvent.click(screen.getByText(/\+ add/i));
    expect(screen.getByPlaceholderText(/memory content/i)).toBeInTheDocument();
  });

  it("search returns results from API", async () => {
    render(<MemoryBrowser />);
    const input = screen.getByPlaceholderText(/search memories/i);
    fireEvent.change(input, { target: { value: "test" } });
    fireEvent.click(screen.getByRole("button", { name: /search/i }));
    await waitFor(() => {
      expect(screen.getByText("test memory")).toBeInTheDocument();
    });
  });

  it("delete button appears on result cards", async () => {
    render(<MemoryBrowser />);
    const input = screen.getByPlaceholderText(/search memories/i);
    fireEvent.change(input, { target: { value: "test" } });
    fireEvent.click(screen.getByRole("button", { name: /search/i }));
    await waitFor(() => expect(screen.getByText("test memory")).toBeInTheDocument());
    expect(screen.getByTitle(/delete/i)).toBeInTheDocument();
  });
});
