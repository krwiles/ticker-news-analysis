import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SearchBar } from "./SearchBar";

describe("SearchBar", () => {
  it("renders an input and a submit button", () => {
    render(<SearchBar onSearch={vi.fn()} />);
    expect(screen.getByPlaceholderText(/ticker symbol/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /search/i })).toBeInTheDocument();
  });

  it("updates the input as the user types", async () => {
    const user = userEvent.setup();
    render(<SearchBar onSearch={vi.fn()} />);

    const input = screen.getByPlaceholderText(/ticker symbol/i);
    await user.type(input, "AAPL");

    expect(input).toHaveValue("AAPL");
  });

  it("calls onSearch with the trimmed ticker on submit", async () => {
    const user = userEvent.setup();
    const onSearch = vi.fn();
    render(<SearchBar onSearch={onSearch} />);

    await user.type(screen.getByPlaceholderText(/ticker symbol/i), "  AAPL  ");
    await user.click(screen.getByRole("button", { name: /search/i }));

    expect(onSearch).toHaveBeenCalledWith("AAPL");
  });

  it("does not call onSearch when the input is empty", async () => {
    const user = userEvent.setup();
    const onSearch = vi.fn();
    render(<SearchBar onSearch={onSearch} />);

    await user.click(screen.getByRole("button", { name: /search/i }));

    expect(onSearch).not.toHaveBeenCalled();
  });

  it("does not call onSearch when the input is only whitespace", async () => {
    const user = userEvent.setup();
    const onSearch = vi.fn();
    render(<SearchBar onSearch={onSearch} />);

    await user.type(screen.getByPlaceholderText(/ticker symbol/i), "   ");
    await user.click(screen.getByRole("button", { name: /search/i }));

    expect(onSearch).not.toHaveBeenCalled();
  });

  it("disables the input and button when disabled", () => {
    render(<SearchBar onSearch={vi.fn()} disabled />);

    expect(screen.getByPlaceholderText(/ticker symbol/i)).toBeDisabled();
    expect(screen.getByRole("button", { name: /search/i })).toBeDisabled();
  });

  it("seeds the input from initialValue", () => {
    render(<SearchBar onSearch={vi.fn()} initialValue="AAPL" />);
    expect(screen.getByPlaceholderText(/ticker symbol/i)).toHaveValue("AAPL");
  });

  it("does not pick up a changed initialValue on its own -- it's a one-time seed, not a continuous binding", () => {
    const { rerender } = render(<SearchBar onSearch={vi.fn()} initialValue="AAPL" />);
    rerender(<SearchBar onSearch={vi.fn()} initialValue="MSFT" />);

    // Same mounted instance -- useState's initial value only applies once,
    // unlike an Angular @Input(). Still shows the original value.
    expect(screen.getByPlaceholderText(/ticker symbol/i)).toHaveValue("AAPL");
  });

  it("remounts with the new initialValue when the key changes -- SearchPage's actual reset mechanism", () => {
    const { rerender } = render(<SearchBar key="AAPL" onSearch={vi.fn()} initialValue="AAPL" />);
    rerender(<SearchBar key="MSFT" onSearch={vi.fn()} initialValue="MSFT" />);

    expect(screen.getByPlaceholderText(/ticker symbol/i)).toHaveValue("MSFT");
  });
});
