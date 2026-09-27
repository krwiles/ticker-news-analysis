import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getInitialTheme, setTheme } from "./theme";

// Stubs matchMedia's boolean result -- jsdom provides no real implementation of it at all.
function stubPrefersDark(prefersDark: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({ matches: prefersDark }),
  );
}

describe("getInitialTheme", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("returns a validly-stored value without touching matchMedia", () => {
    // Arrange: a real stored preference, plus a matchMedia spy to prove it's never called.
    localStorage.setItem("theme", "dark");
    const matchMedia = vi.fn();
    vi.stubGlobal("matchMedia", matchMedia);

    // Act.
    const theme = getInitialTheme();

    // Assert: the stored value wins, and the OS preference is never even checked.
    expect(theme).toBe("dark");
    expect(matchMedia).not.toHaveBeenCalled();
  });

  it("falls back to the OS preference when nothing is stored", () => {
    // Arrange: no stored value, OS prefers dark.
    stubPrefersDark(true);

    // Act / Assert.
    expect(getInitialTheme()).toBe("dark");
  });

  it("falls back to the OS preference (light) when nothing is stored", () => {
    stubPrefersDark(false);
    expect(getInitialTheme()).toBe("light");
  });

  it("falls back to the OS preference when localStorage.getItem throws", () => {
    // Arrange: a private-browsing-style storage failure, OS prefers dark.
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage disabled");
    });
    stubPrefersDark(true);

    // Act / Assert: the throw doesn't propagate, and the OS preference is used instead.
    expect(getInitialTheme()).toBe("dark");
  });
});

describe("setTheme", () => {
  afterEach(() => {
    document.documentElement.classList.remove("dark");
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("adds the dark class to the document root for dark", () => {
    setTheme("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("removes the dark class from the document root for light", () => {
    document.documentElement.classList.add("dark");
    setTheme("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("persists the choice to localStorage", () => {
    setTheme("dark");
    expect(localStorage.getItem("theme")).toBe("dark");
  });

  it("does not throw when localStorage.setItem throws", () => {
    // Arrange: a storage failure shouldn't stop the theme from applying to this page view.
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage disabled");
    });

    // Act / Assert.
    expect(() => setTheme("dark")).not.toThrow();
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });
});
