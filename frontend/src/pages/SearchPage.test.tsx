import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as searchModule from "../search";
import { SearchPage } from "./SearchPage";

// Module-mocked one layer up from search.test.ts -- SearchPage just consumes fetchSearch/fetchSearchStatus.
// hasPendingSentiment is a pure function, kept real (via importOriginal) rather than mocked -- it's
// exactly the logic the polling tests below need to exercise for real, not stub out.
// Frontend analogue of the backend's dependency_overrides (test_search_endpoint.py).
vi.mock("../search", async (importOriginal) => {
  const actual = await importOriginal<typeof searchModule>();
  return {
    ...actual,
    fetchSearch: vi.fn(),
    fetchSearchStatus: vi.fn(),
  };
});

const fetchSearch = vi.mocked(searchModule.fetchSearch);
const fetchSearchStatus = vi.mocked(searchModule.fetchSearchStatus);

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
    sentiment_score: null,
    sentiment_gloss: null,
    sentiment_rationale: null,
    sentiment_status: null,
    sentiment_enum: null,
    ...overrides,
  };
}

function story(overrides: Partial<searchModule.Story> = {}): searchModule.Story {
  return {
    story_id: "11111111-1111-1111-1111-111111111111",
    primary: headline(),
    other_members: [],
    sentiment_average: null,
    sentiment_enum: null,
    ...overrides,
  };
}

function response(overrides: Partial<searchModule.SearchResponse> = {}): searchModule.SearchResponse {
  return {
    ticker: "AAPL",
    status: "success",
    providers: { edgar: "ok", finnhub: "ok" },
    grouping: "ok",
    sentiment: "ok",
    days: [],
    ...overrides,
  };
}

describe("SearchPage", () => {
  beforeEach(() => {
    fetchSearch.mockReset();
    fetchSearchStatus.mockReset();
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

  // First frontend tests in this codebase exercising a timer-driven effect.
  // shouldAdvanceTime keeps real-time-based utilities (RTL's own waitFor)
  // working normally, while vi.advanceTimersByTime still lets the poll
  // interval itself be fast-forwarded instantly instead of waiting 5 real
  // seconds per tick.
  // A day/story wrapping a single headline, for building minimal `days` fixtures below.
  function dayWith(h: searchModule.Headline): searchModule.DayGroup[] {
    return [{ date: "2026-09-17", is_today: true, stories: [story({ primary: h })] }];
  }

  describe("sentiment polling", () => {
    afterEach(() => {
      vi.useRealTimers();
    });

    it("never polls when every headline already has a real sentiment attempt", async () => {
      // Arrange: the one headline on the page already resolved -- nothing left to poll for.
      fetchSearch.mockResolvedValue(
        response({ sentiment: "ok", days: dayWith(headline({ sentiment_status: "ok", sentiment_enum: "positive", sentiment_score: 80 })) }),
      );

      // Act: load via the URL.
      renderSearchPage(["/search?ticker=AAPL"]);
      await waitFor(() => {
        expect(screen.getByText(/analysis complete/i)).toBeInTheDocument();
      });

      // Assert: the status endpoint was never touched.
      expect(fetchSearchStatus).not.toHaveBeenCalled();
    });

    it("polls /api/search/status while a headline still has no sentiment attempt, and merges the resolved update", async () => {
      // Arrange: fake timers so the poll interval can be fast-forwarded; the initial search still has a pending headline.
      vi.useFakeTimers({ shouldAdvanceTime: true });
      fetchSearch.mockResolvedValue(
        response({ sentiment: "processing", days: dayWith(headline({ title: "Resolved via poll", url: "https://example.com/resolved" })) }),
      );
      fetchSearchStatus.mockResolvedValue({
        sentiment: "ok",
        days: dayWith(
          headline({
            title: "Resolved via poll",
            url: "https://example.com/resolved",
            sentiment_status: "ok",
            sentiment_enum: "positive",
            sentiment_score: 82,
          }),
        ),
      });

      // Act: load via the URL, wait for the initial "processing" render.
      renderSearchPage(["/search?ticker=AAPL"]);
      await waitFor(() => {
        expect(screen.getByText(/in progress/i)).toBeInTheDocument();
      });
      expect(fetchSearchStatus).not.toHaveBeenCalled();

      // Fast-forward past one poll interval.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000);
      });

      // Assert: the poll fired for the same ticker, and its result (sentiment + days) merged into the page --
      // note days came only from the poll, proving providers/status/grouping from the original fetch survived the merge.
      expect(fetchSearchStatus).toHaveBeenCalledWith("AAPL");
      await waitFor(() => {
        expect(screen.getByText(/analysis complete/i)).toBeInTheDocument();
      });
      expect(screen.getByRole("link", { name: "Resolved via poll" })).toBeInTheDocument();
    });

    it("stops polling once every headline reaches a terminal status -- no further calls after the tick that resolved it", async () => {
      // Arrange: same pending -> resolved setup as above.
      vi.useFakeTimers({ shouldAdvanceTime: true });
      fetchSearch.mockResolvedValue(response({ sentiment: "processing", days: dayWith(headline()) }));
      fetchSearchStatus.mockResolvedValue({
        sentiment: "ok",
        days: dayWith(headline({ sentiment_status: "ok", sentiment_enum: "positive", sentiment_score: 80 })),
      });

      renderSearchPage(["/search?ticker=AAPL"]);
      await waitFor(() => {
        expect(screen.getByText(/in progress/i)).toBeInTheDocument();
      });

      // Act: advance past the tick that resolves it, then several more intervals' worth of time.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000);
      });
      await waitFor(() => {
        expect(fetchSearchStatus).toHaveBeenCalledTimes(1);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(20000);
      });

      // Assert: no further polling happened once every headline had a terminal status.
      expect(fetchSearchStatus).toHaveBeenCalledTimes(1);
    });

    it("keeps polling even when the page-level status reads error, as long as another headline is still pending", async () => {
      // Arrange: a real, deliberate mixed case -- one headline already permanently failed (masking the
      // page-level status to "error", lesson 26's own priority order), but a second headline in the same
      // batch hasn't been attempted yet. A poll driven off the coarse `sentiment` field alone would never
      // start here, silently stranding that second headline's eventual result.
      vi.useFakeTimers({ shouldAdvanceTime: true });
      fetchSearch.mockResolvedValue(
        response({
          sentiment: "error",
          days: [
            {
              date: "2026-09-17",
              is_today: true,
              stories: [
                story({ primary: headline({ url: "https://example.com/already-failed", sentiment_status: "error" }) }),
                story({ primary: headline({ url: "https://example.com/still-pending", title: "Still pending" }) }),
              ],
            },
          ],
        }),
      );
      fetchSearchStatus.mockResolvedValue({
        sentiment: "error",
        days: [
          {
            date: "2026-09-17",
            is_today: true,
            stories: [
              story({ primary: headline({ url: "https://example.com/already-failed", sentiment_status: "error" }) }),
              story({
                primary: headline({
                  url: "https://example.com/still-pending",
                  title: "Still pending",
                  sentiment_status: "ok",
                  sentiment_enum: "neutral",
                  sentiment_score: 55,
                }),
              }),
            ],
          },
        ],
      });

      renderSearchPage(["/search?ticker=AAPL"]);
      await waitFor(() => {
        expect(screen.getByText(/analysis failed/i)).toBeInTheDocument();
      });

      // Act: fast-forward one poll interval.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000);
      });

      // Assert: the poll fired despite the page reading "error" the whole time, and the second
      // headline's result made it onto the page.
      expect(fetchSearchStatus).toHaveBeenCalledWith("AAPL");
      await waitFor(() => {
        expect(screen.getByText("neutral · 55")).toBeInTheDocument();
      });
    });

    it("restarts polling on a manual Refresh even when the overall status is the same before and after", async () => {
      // Arrange: Refresh always re-enqueues a retry server-side (search.py), but if the frontend only
      // watched the coarse `sentiment` value it would see "error" both before and after and never notice.
      vi.useFakeTimers({ shouldAdvanceTime: true });
      fetchSearch.mockResolvedValueOnce(
        response({ sentiment: "error", days: dayWith(headline({ sentiment_status: "error" })) }),
      );
      renderSearchPage(["/search?ticker=AAPL"]);
      await waitFor(() => {
        expect(screen.getByText(/analysis failed/i)).toBeInTheDocument();
      });
      expect(fetchSearchStatus).not.toHaveBeenCalled();

      // Act: click Refresh -- the retried headline is now genuinely pending again (status reset to null
      // server-side, same as _seed_headline_for_sentiment's own "error" -> retry path). fireEvent, not
      // userEvent, to avoid userEvent's own real-timer-based internals fighting the fake timers here.
      fetchSearch.mockResolvedValueOnce(response({ sentiment: "error", days: dayWith(headline()) }));
      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: /refresh/i }));
      });
      await waitFor(() => {
        expect(fetchSearch).toHaveBeenCalledTimes(2);
      });

      // Assert: polling starts even though sentiment read "error" both times.
      fetchSearchStatus.mockResolvedValue({
        sentiment: "ok",
        days: dayWith(headline({ sentiment_status: "ok", sentiment_enum: "positive", sentiment_score: 80 })),
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000);
      });
      expect(fetchSearchStatus).toHaveBeenCalledWith("AAPL");
    });
  });
});
