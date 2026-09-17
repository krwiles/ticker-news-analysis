import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as searchModule from "../search";
import { SearchPage } from "./SearchPage";

// Module-mocked one layer up from search.test.ts -- SearchPage just consumes fetchSearch.
// Frontend analogue of the backend's dependency_overrides (test_search_endpoint.py).
vi.mock("../search", () => ({
  fetchSearch: vi.fn(),
}));

const fetchSearch = vi.mocked(searchModule.fetchSearch);

function renderSearchPage(initialEntries: string[] = ["/search"]) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <SearchPage />
    </MemoryRouter>,
  );
}

async function searchFor(ticker: string) {
  const user = userEvent.setup();
  await user.type(screen.getByPlaceholderText(/ticker symbol/i), ticker);
  await user.click(screen.getByRole("button", { name: /search/i }));
}

function headline(overrides: Partial<searchModule.Headline> = {}): searchModule.Headline {
  return {
    title: "A real headline",
    url: "https://example.com/a",
    category: "news",
    provider: "finnhub",
    outlet: null,
    summary: null,
    published_at: "2026-09-11T12:00:00Z",
    ...overrides,
  };
}

function story(overrides: Partial<searchModule.Story> = {}): searchModule.Story {
  return {
    story_id: "11111111-1111-1111-1111-111111111111",
    primary: headline(),
    other_members: [],
    ...overrides,
  };
}

function response(overrides: Partial<searchModule.SearchResponse> = {}): searchModule.SearchResponse {
  return {
    ticker: "AAPL",
    status: "success",
    providers: { edgar: "ok", finnhub: "ok" },
    grouping: "ok",
    days: [],
    ...overrides,
  };
}

describe("SearchPage", () => {
  beforeEach(() => {
    fetchSearch.mockReset();
  });

  it("renders no results, no status, and no Refresh button before any search happens", () => {
    renderSearchPage();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
    expect(screen.queryByText(/searching/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /refresh/i })).not.toBeInTheDocument();
  });

  it("shows a loading state while the search is in flight, then renders results", async () => {
    // A promise we control, so the fetch can be left pending on purpose.
    let resolveFetch!: (value: searchModule.SearchResponse) => void;
    fetchSearch.mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve;
      }),
    );

    renderSearchPage();
    await searchFor("AAPL");

    expect(screen.getByText(/searching/i)).toBeInTheDocument();

    // Now let the fetch actually complete.
    resolveFetch(
      response({
        days: [{ date: "2026-09-11", is_today: true, stories: [story({ primary: headline({ title: "A real headline" }) })] }],
      }),
    );

    await waitFor(() => {
      expect(screen.getByRole("link", { name: "A real headline" })).toBeInTheDocument();
    });
    expect(screen.queryByText(/searching/i)).not.toBeInTheDocument();
  });

  it("renders each day as its own section, never merged", async () => {
    fetchSearch.mockResolvedValue(
      response({
        days: [
          {
            date: "2026-09-17",
            is_today: true,
            stories: [story({ primary: headline({ title: "Today's headline", url: "https://example.com/today" }) })],
          },
          {
            date: "2026-09-16",
            is_today: false,
            stories: [
              story({
                primary: headline({
                  title: "Earlier headline",
                  url: "https://example.com/earlier",
                  category: "filing",
                  provider: "sec_edgar",
                }),
              }),
            ],
          },
        ],
      }),
    );

    renderSearchPage();
    await searchFor("AAPL");

    const todaySection = (await screen.findByRole("heading", { name: "Today" })).closest("section")!;
    expect(within(todaySection).getByRole("link", { name: "Today's headline" })).toBeInTheDocument();
    expect(within(todaySection).queryByRole("link", { name: "Earlier headline" })).not.toBeInTheDocument();

    const earlierSection = screen.getByRole("heading", { name: "September 16" }).closest("section")!;
    expect(within(earlierSection).getByRole("link", { name: "Earlier headline" })).toBeInTheDocument();
    expect(within(earlierSection).queryByRole("link", { name: "Today's headline" })).not.toBeInTheDocument();
  });

  it("shows Today's own empty message when Today is empty but an earlier day has entries", async () => {
    fetchSearch.mockResolvedValue(
      response({
        days: [
          { date: "2026-09-17", is_today: true, stories: [] },
          {
            date: "2026-09-16",
            is_today: false,
            stories: [story({ primary: headline({ title: "Earlier headline", url: "https://example.com/earlier" }) })],
          },
        ],
      }),
    );

    renderSearchPage();
    await searchFor("AAPL");

    const todaySection = (await screen.findByRole("heading", { name: "Today" })).closest("section")!;
    expect(within(todaySection).getByText("No headlines today.")).toBeInTheDocument();

    const earlierSection = screen.getByRole("heading", { name: "September 16" }).closest("section")!;
    expect(within(earlierSection).getByRole("link", { name: "Earlier headline" })).toBeInTheDocument();
  });

  it("shows the human-readable status message, not the raw status value", async () => {
    fetchSearch.mockResolvedValue(response({ status: "partial_failure", providers: { edgar: "ok", finnhub: "error" } }));

    renderSearchPage();
    await searchFor("AAPL");

    await waitFor(() => {
      expect(screen.getByText(/some results may be missing/i)).toBeInTheDocument();
    });
    expect(screen.queryByText("partial_failure")).not.toBeInTheDocument();
  });

  it("shows the grouping status underneath the response status", async () => {
    fetchSearch.mockResolvedValue(response({ grouping: "skipped" }));

    renderSearchPage();
    await searchFor("AAPL");

    await waitFor(() => {
      expect(screen.getByText(/isn't configured/i)).toBeInTheDocument();
    });
  });

  it("shows a Refresh button once results exist, and clicking it re-fetches the same ticker", async () => {
    fetchSearch.mockResolvedValue(response());

    renderSearchPage();
    await searchFor("AAPL");

    const refreshButton = await screen.findByRole("button", { name: /refresh/i });

    // Clear the initial search's call so the assertion below is about the Refresh click alone.
    fetchSearch.mockClear();
    const user = userEvent.setup();
    await user.click(refreshButton);

    expect(fetchSearch).toHaveBeenCalledWith("AAPL");
  });

  it("shows an error message when fetchSearch rejects, not a crash", async () => {
    fetchSearch.mockRejectedValue(new Error("/api/search responded 500"));

    renderSearchPage();
    await searchFor("AAPL");

    await waitFor(() => {
      expect(screen.getByText(/couldn't reach the api/i)).toBeInTheDocument();
    });
  });

  it("loads automatically when the URL already has a ticker param -- the data-loading pattern", async () => {
    fetchSearch.mockResolvedValue(
      response({
        days: [
          {
            date: "2026-09-17",
            is_today: true,
            stories: [story({ primary: headline({ title: "Loaded from the URL", url: "https://example.com/url-driven" }) })],
          },
        ],
      }),
    );

    // No searchFor() call -- nothing is typed or clicked. The URL alone
    // should be enough to trigger a fetch.
    renderSearchPage(["/search?ticker=AAPL"]);

    await waitFor(() => {
      expect(fetchSearch).toHaveBeenCalledWith("AAPL");
    });
    expect(screen.getByRole("link", { name: "Loaded from the URL" })).toBeInTheDocument();
    // The search bar itself should reflect the URL-seeded ticker too.
    expect(screen.getByPlaceholderText(/ticker symbol/i)).toHaveValue("AAPL");
  });

  it("still functions when the URL's ticker is lowercase -- case is not enforced on the read path", async () => {
    fetchSearch.mockResolvedValue(response());

    renderSearchPage(["/search?ticker=aapl"]);

    // Passed straight through, unmodified -- the backend (search.py's
    // ticker.upper()) is what actually normalizes it, not this component.
    await waitFor(() => {
      expect(fetchSearch).toHaveBeenCalledWith("aapl");
    });
  });
});
