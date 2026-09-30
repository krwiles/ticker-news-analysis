import { afterEach, describe, expect, it, vi } from "vitest";
import { addToWatchlist, fetchWatchlist, removeFromWatchlist, type WatchlistResponse } from "./watchlist";

// Mocks the raw fetch call, same boundary search.test.ts uses for fetchSearch.
describe("fetchWatchlist", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const okResponse: WatchlistResponse = {
    entries: [{ ticker: "MSFT", added_at: "2026-09-30T00:00:00Z", new_headlines: 2 }],
  };

  it("requests /api/watchlist with credentials included", async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => okResponse });
    vi.stubGlobal("fetch", mockFetch);

    await fetchWatchlist();

    expect(mockFetch).toHaveBeenCalledWith("http://localhost:8000/api/watchlist", { credentials: "include" });
  });

  it("returns the parsed JSON body on a successful response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => okResponse }));

    const result = await fetchWatchlist();

    expect(result).toEqual(okResponse);
  });

  it("throws with the response status when the response is not ok", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({}) }));

    await expect(fetchWatchlist()).rejects.toThrow("/api/watchlist responded 401");
  });
});

describe("addToWatchlist", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("POSTs the ticker as JSON with credentials included", async () => {
    const entry = { ticker: "MSFT", added_at: "2026-09-30T00:00:00Z", new_headlines: 0 };
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => entry });
    vi.stubGlobal("fetch", mockFetch);

    await addToWatchlist("MSFT");

    expect(mockFetch).toHaveBeenCalledWith("http://localhost:8000/api/watchlist", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticker: "MSFT" }),
    });
  });

  it("throws with the response status when the response is not ok", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404, json: async () => ({}) }));

    await expect(addToWatchlist("NVDA")).rejects.toThrow("/api/watchlist responded 404");
  });
});

describe("removeFromWatchlist", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("DELETEs the URL-encoded ticker with credentials included", async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
    vi.stubGlobal("fetch", mockFetch);

    await removeFromWatchlist("MSFT");

    expect(mockFetch).toHaveBeenCalledWith("http://localhost:8000/api/watchlist/MSFT", {
      method: "DELETE",
      credentials: "include",
    });
  });

  it("throws with the response status when the response is not ok", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({}) }));

    await expect(removeFromWatchlist("MSFT")).rejects.toThrow("/api/watchlist/MSFT responded 500");
  });
});
