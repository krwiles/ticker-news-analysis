import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as searchModule from "../search";
import { SearchPage } from "./SearchPage";

// Module-mocked one layer up from search.test.ts's fetch-boundary mock --
// SearchPage consumes fetchSearch, it doesn't implement it. This is this
// project's frontend analogue of the backend's dependency_overrides layer
// (test_search_endpoint.py): swap an imported module rather than an
// injected parameter. See NOTES.md / [[di-mechanism-follows-two-independent-questions]].
vi.mock("../search", () => ({
  fetchSearch: vi.fn(),
}));

const fetchSearch = vi.mocked(searchModule.fetchSearch);

async function searchFor(ticker: string) {
  const user = userEvent.setup();
  await user.type(screen.getByPlaceholderText(/ticker symbol/i), ticker);
  await user.click(screen.getByRole("button", { name: /search/i }));
}

describe("SearchPage", () => {
  beforeEach(() => {
    fetchSearch.mockReset();
  });

  it("renders no results before any search happens", () => {
    render(<SearchPage />);
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
    expect(screen.queryByText(/searching/i)).not.toBeInTheDocument();
  });

  it("shows a loading state while the search is in flight, then renders results", async () => {
    let resolveFetch!: (value: searchModule.SearchResponse) => void;
    fetchSearch.mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve;
      }),
    );

    render(<SearchPage />);
    await searchFor("AAPL");

    expect(screen.getByText(/searching/i)).toBeInTheDocument();

    resolveFetch({
      ticker: "AAPL",
      status: "success",
      providers: { edgar: "ok", finnhub: "ok" },
      today: [
        {
          title: "A real headline",
          url: "https://example.com/1",
          category: "news",
          provider: "finnhub",
          outlet: "Yahoo",
          summary: null,
          published_at: "2026-09-11T12:00:00Z",
        },
      ],
      recent: [],
    });

    await waitFor(() => {
      expect(screen.getByRole("link", { name: "A real headline" })).toBeInTheDocument();
    });
    expect(screen.queryByText(/searching/i)).not.toBeInTheDocument();
  });

  it("combines today and recent into one rendered list", async () => {
    fetchSearch.mockResolvedValue({
      ticker: "AAPL",
      status: "success",
      providers: { edgar: "ok", finnhub: "ok" },
      today: [
        {
          title: "Today's headline",
          url: "https://example.com/today",
          category: "news",
          provider: "finnhub",
          outlet: null,
          summary: null,
          published_at: "2026-09-11T12:00:00Z",
        },
      ],
      recent: [
        {
          title: "Recent headline",
          url: "https://example.com/recent",
          category: "filing",
          provider: "sec_edgar",
          outlet: null,
          summary: null,
          published_at: "2026-09-08T12:00:00Z",
        },
      ],
    });

    render(<SearchPage />);
    await searchFor("AAPL");

    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Today's headline" })).toBeInTheDocument();
    });
    expect(screen.getByRole("link", { name: "Recent headline" })).toBeInTheDocument();
  });

  it("shows an error message when fetchSearch rejects, not a crash", async () => {
    fetchSearch.mockRejectedValue(new Error("/api/search responded 500"));

    render(<SearchPage />);
    await searchFor("AAPL");

    await waitFor(() => {
      expect(screen.getByText(/couldn't reach the api/i)).toBeInTheDocument();
    });
  });
});
