import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchSearch, type SearchResponse } from "./search";

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
    today: [],
    recent: [],
  };

  it("requests /api/search with the URL-encoded ticker", async () => {
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
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({}) }),
    );

    await expect(fetchSearch("AAPL")).rejects.toThrow("/api/search responded 500");
  });
});
