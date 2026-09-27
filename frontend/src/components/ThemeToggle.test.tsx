import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeToggle } from "./ThemeToggle";

describe("ThemeToggle", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove("dark");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows a control to switch to dark mode when the initial theme is light", () => {
    // Arrange: no stored preference, OS prefers light.
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: false }));

    // Act.
    render(<ThemeToggle />);

    // Assert: labeled by the action it performs, not the icon.
    expect(screen.getByRole("button", { name: /switch to dark mode/i })).toBeInTheDocument();
  });

  it("shows a control to switch to light mode when the initial theme is dark", () => {
    // Arrange: a real stored dark preference.
    localStorage.setItem("theme", "dark");

    // Act.
    render(<ThemeToggle />);

    // Assert.
    expect(screen.getByRole("button", { name: /switch to light mode/i })).toBeInTheDocument();
  });

  it("toggles the document's dark class and its own label when clicked", async () => {
    // Arrange: starts light.
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: false }));
    const user = userEvent.setup();
    render(<ThemeToggle />);
    expect(document.documentElement.classList.contains("dark")).toBe(false);

    // Act: click to switch to dark.
    await user.click(screen.getByRole("button", { name: /switch to dark mode/i }));

    // Assert: the real DOM class flips, and the button now offers the opposite action.
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(screen.getByRole("button", { name: /switch to light mode/i })).toBeInTheDocument();

    // Act: click again to switch back.
    await user.click(screen.getByRole("button", { name: /switch to light mode/i }));

    // Assert: back to light.
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(screen.getByRole("button", { name: /switch to dark mode/i })).toBeInTheDocument();
  });

  it("persists the toggled choice to localStorage", async () => {
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: false }));
    const user = userEvent.setup();
    render(<ThemeToggle />);

    await user.click(screen.getByRole("button", { name: /switch to dark mode/i }));

    expect(localStorage.getItem("theme")).toBe("dark");
  });
});
