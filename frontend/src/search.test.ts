import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchSearch, fetchSearchStatus, type SearchResponse, type SearchStatusResponse } from "./search";

// Mocks the raw fetch call, same boundary respx mocks on the backend.
// SearchPage.test.tsx mocks one layer up instead (the whole search.ts module).
describe("fetchSearch", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const okResponse: SearchResponse = {
    ticker: "AAPL",
    status: "success",
    providers: { edgar: "ok", finnhub: "ok" },
    grouping: "ok",
    sentiment: "ok",
    days: [],
  };

  it("requests /api/search with the URL-encoded ticker", async () => {
    // Stub the global fetch so no real network call happens.
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => okResponse,
    });
    vi.stubGlobal("fetch", mockFetch);

    await fetchSearch("AAPL");

    expect(mockFetch).toHaveBeenCalledWith("http://localhost:8000/api/search?ticker=AAPL");
  });

  it("returns the parsed JSON body on a successful response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => okResponse }),
    );

    const result = await fetchSearch("AAPL");

    expect(result).toEqual(okResponse);
  });

  it("throws with the response status when the response is not ok", async () => {
    // Stub a failing response.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({}) }),
    );

    await expect(fetchSearch("AAPL")).rejects.toThrow("/api/search responded 500");
  });
});

// Mirrors fetchSearch's own three tests exactly -- same boundary, same shape of checks.
describe("fetchSearchStatus", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const okResponse: SearchStatusResponse = {
    sentiment: "processing",
    days: [],
  };

  it("requests /api/search/status with the URL-encoded ticker", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => okResponse,
    });
    vi.stubGlobal("fetch", mockFetch);

    await fetchSearchStatus("AAPL");

    expect(mockFetch).toHaveBeenCalledWith("http://localhost:8000/api/search/status?ticker=AAPL");
  });

  it("returns the parsed JSON body on a successful response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => okResponse }),
    );

    const result = await fetchSearchStatus("AAPL");

    expect(result).toEqual(okResponse);
  });

  it("throws with the response status when the response is not ok", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({}) }),
    );

    await expect(fetchSearchStatus("AAPL")).rejects.toThrow("/api/search/status responded 500");
  });
});
