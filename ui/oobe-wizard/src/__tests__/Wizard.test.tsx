import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "../App";

describe("OOBE Wizard", () => {
  it("renders welcome step", () => {
    render(<App />);
    expect(screen.getByText("Hello.")).toBeInTheDocument();
    expect(screen.getByText("Let's get your AI desktop ready.")).toBeInTheDocument();
  });

  it("click Get Started advances to step 2", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /Get Started/i }));
    return waitFor(() => {
      expect(screen.getByText("Region & Language")).toBeInTheDocument();
    });
  });

  it("auto-generates username from full name", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /Get Started/i }));
    await waitFor(() => expect(screen.getByText("Region & Language")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Continue/i }));
    await waitFor(() => expect(screen.getByText("User Account")).toBeInTheDocument());
    const fullName = screen.getByLabelText("Full Name");
    fireEvent.change(fullName, { target: { value: "Jane Doe" } });
    expect((screen.getByLabelText("Username") as HTMLInputElement).value).toBe("jane_doe");
  });

  it("shows error for password mismatch", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /Get Started/i }));
    await waitFor(() => expect(screen.getByText("Region & Language")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Continue/i }));
    await waitFor(() => expect(screen.getByText("User Account")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Full Name"), { target: { value: "Kryos User" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "abc123" } });
    fireEvent.change(screen.getByLabelText("Confirm Password"), { target: { value: "mismatch" } });

    fireEvent.click(screen.getByRole("button", { name: /Continue/i }));
    expect(screen.getByText(/Passwords do not match/i)).toBeInTheDocument();
  });

  it("renders model list from API mock", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /Get Started/i }));
    await waitFor(() => expect(screen.getByText("Region & Language")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Continue/i }));
    await waitFor(() => expect(screen.getByText("User Account")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Full Name"), { target: { value: "Kryos User" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "abc123" } });
    fireEvent.change(screen.getByLabelText("Confirm Password"), { target: { value: "abc123" } });
    fireEvent.click(screen.getByRole("button", { name: /Continue/i }));

    await waitFor(() => expect(screen.getByText("Set up your AI brain")).toBeInTheDocument());
    expect(screen.getByLabelText("Default Model")).toBeInTheDocument();
    expect(screen.getByText("llama3-8b")).toBeInTheDocument();
  });

  it("step 5 summary shows username timezone and model", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /Get Started/i }));
    await waitFor(() => expect(screen.getByText("Region & Language")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Continue/i }));
    await waitFor(() => expect(screen.getByText("User Account")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Full Name"), { target: { value: "Kryos User" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "abc123" } });
    fireEvent.change(screen.getByLabelText("Confirm Password"), { target: { value: "abc123" } });
    fireEvent.click(screen.getByRole("button", { name: /Continue/i }));

    await waitFor(() => expect(screen.getByText("Set up your AI brain")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Continue/i }));

    await waitFor(() => expect(screen.getByText("You're all set.")).toBeInTheDocument());
    expect(screen.getByText(/Username:/)).toBeInTheDocument();
    expect(screen.getByText(/Timezone:/)).toBeInTheDocument();
    expect(screen.getByText(/Default model:/)).toBeInTheDocument();
  });
});
