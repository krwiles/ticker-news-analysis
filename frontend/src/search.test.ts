import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchSearch, type SearchResponse } from "./search";

// Mocks at the same boundary respx mocks on the backend -- the raw fetch
// call itself, not a wrapper around it. This is search.ts's own test;
// SearchPage.test.tsx mocks one layer up (search.ts as a whole module)
// instead, mirroring the backend's dependency-override layer.
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
