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
});
