import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { WatchlistOutletContext } from "../components/Layout";
import * as searchModule from "../search";
import { SearchPage } from "./SearchPage";

// Module-mocked one layer up from search.test.ts -- SearchPage just consumes fetchSearch/fetchSearchStatus.
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

// Stands in for Layout as a real parent route, exercising the actual Outlet-context wiring
// (ADR 0019). Defaults to signed-out; watchlist-button tests override it.
function renderSearchPage(initialEntries: string[] = ["/search"], context: Partial<WatchlistOutletContext> = {}) {
  const fullContext: WatchlistOutletContext = {
    isSignedIn: false,
    entries: [],
    add: vi.fn(),
    remove: vi.fn(),
    ...context,
  };
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <Routes>
        <Route element={<Outlet context={fullContext} />}>
          <Route path="/search" element={<SearchPage />} />
        </Route>
      </Routes>
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

// Same defaults as response() minus ticker -- a poll now refreshes status/providers/grouping
// too, not just sentiment/days, so every fetchSearchStatus mock needs a full shape.
function statusResponse(overrides: Partial<searchModule.SearchStatusResponse> = {}): searchModule.SearchStatusResponse {
  return {
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
    // Arrange/Act: render with no search performed yet.
    renderSearchPage();

    // Assert: nothing from a completed search is showing.
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

    // Act: kick off a search that won't resolve yet.
    renderSearchPage();
    await searchFor("AAPL");

    // Assert: the loading state shows while the fetch is still pending.
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
    // Arrange: two days, each with one distinctly-named headline.
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

    // Act
    renderSearchPage();
    await searchFor("AAPL");

    // Assert: each section holds only its own day's headline, not the other day's.
    const todaySection = (await screen.findByRole("heading", { name: "Today" })).closest("section")!;
    expect(within(todaySection).getByRole("link", { name: "Today's headline" })).toBeInTheDocument();
    expect(within(todaySection).queryByRole("link", { name: "Earlier headline" })).not.toBeInTheDocument();

    const earlierSection = screen.getByRole("heading", { name: "September 16" }).closest("section")!;
    expect(within(earlierSection).getByRole("link", { name: "Earlier headline" })).toBeInTheDocument();
    expect(within(earlierSection).queryByRole("link", { name: "Today's headline" })).not.toBeInTheDocument();
  });

  it("shows Today's own empty message when Today is empty but an earlier day has entries", async () => {
    // Arrange: Today has no Stories, but an earlier day does.
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

    // Act
    renderSearchPage();
    await searchFor("AAPL");

    // Assert: Today shows the empty message; the earlier day still shows its own headline.
    const todaySection = (await screen.findByRole("heading", { name: "Today" })).closest("section")!;
    expect(within(todaySection).getByText("No headlines today.")).toBeInTheDocument();

    const earlierSection = screen.getByRole("heading", { name: "September 16" }).closest("section")!;
    expect(within(earlierSection).getByRole("link", { name: "Earlier headline" })).toBeInTheDocument();
  });

  it("shows the human-readable status message, not the raw status value", async () => {
    // Arrange
    fetchSearch.mockResolvedValue(response({ status: "partial_failure", providers: { edgar: "ok", finnhub: "error" } }));

    // Act
    renderSearchPage();
    await searchFor("AAPL");

    // Assert: the friendly message shows, the raw enum value never does.
    await waitFor(() => {
      expect(screen.getByText(/some results may be missing/i)).toBeInTheDocument();
    });
    expect(screen.queryByText("partial_failure")).not.toBeInTheDocument();
  });

  it("shows the grouping status underneath the response status", async () => {
    // Arrange
    fetchSearch.mockResolvedValue(response({ grouping: "skipped" }));

    // Act
    renderSearchPage();
    await searchFor("AAPL");

    // Assert
    await waitFor(() => {
      expect(screen.getByText(/isn't configured/i)).toBeInTheDocument();
    });
  });

  it("never shows a manual refresh control, even once results exist -- spec 0007 replaces it with live refresh", async () => {
    // Arrange
    fetchSearch.mockResolvedValue(response());

    // Act: run the initial search.
    renderSearchPage();
    await searchFor("AAPL");
    await screen.findByText("All sources responded.");

    // Assert: no button of any kind exists for triggering a fetch manually.
    expect(screen.queryByRole("button", { name: /refresh/i })).not.toBeInTheDocument();
  });

  it("shows an error message when fetchSearch rejects, not a crash", async () => {
    // Arrange
    fetchSearch.mockRejectedValue(new Error("/api/search responded 500"));

    // Act
    renderSearchPage();
    await searchFor("AAPL");

    // Assert
    await waitFor(() => {
      expect(screen.getByText(/couldn't reach the api/i)).toBeInTheDocument();
    });
  });

  it("loads automatically when the URL already has a ticker param -- the data-loading pattern", async () => {
    // Arrange
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

    // Act: no searchFor() call -- nothing is typed or clicked. The URL alone
    // should be enough to trigger a fetch.
    renderSearchPage(["/search?ticker=AAPL"]);

    // Assert
    await waitFor(() => {
      expect(fetchSearch).toHaveBeenCalledWith("AAPL");
    });
    expect(screen.getByRole("link", { name: "Loaded from the URL" })).toBeInTheDocument();
    // The search bar itself should reflect the URL-seeded ticker too.
    expect(screen.getByPlaceholderText(/ticker symbol/i)).toHaveValue("AAPL");
  });

  it("still functions when the URL's ticker is lowercase -- case is not enforced on the read path", async () => {
    // Arrange
    fetchSearch.mockResolvedValue(response());

    // Act
    renderSearchPage(["/search?ticker=aapl"]);

    // Assert: passed straight through, unmodified -- the backend (search.py's
    // ticker.upper()) is what actually normalizes it, not this component.
    await waitFor(() => {
      expect(fetchSearch).toHaveBeenCalledWith("aapl");
    });
  });

  // A day/story wrapping a single headline, for building minimal `days` fixtures below.
  function dayWith(h: searchModule.Headline): searchModule.DayGroup[] {
    return [{ date: "2026-09-17", is_today: true, stories: [story({ primary: h })] }];
  }

  // Toggles jsdom's document.visibilityState and fires the event SearchPage listens for --
  // spec 0007's own pause/resume behavior is keyed on this, not on window focus/blur.
  function setVisibility(state: "visible" | "hidden") {
    Object.defineProperty(document, "visibilityState", { value: state, configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
  }

  // Live-refresh (spec 0007) replaces the old manual Refresh button and the "only poll while
  // sentiment is pending" gate: unconditional polling, pause/resume, and a "last refresh" counter.
  describe("live refresh", () => {
    afterEach(() => {
      vi.useRealTimers();
      setVisibility("visible");
    });

    it("clears a stuck 'deferred' state once a poll reports the fetch actually succeeded", async () => {
      // Regression: a page that first loaded mid-cooldown ("deferred") used to stay stuck
      // forever, since polling only merged sentiment/days, never status/providers/grouping.
      vi.useFakeTimers({ shouldAdvanceTime: true });
      fetchSearch.mockResolvedValue(response({ status: "deferred", providers: {}, grouping: "unknown" }));
      fetchSearchStatus.mockResolvedValue(statusResponse({ status: "success", grouping: "ok" }));

      renderSearchPage(["/search?ticker=AAPL"]);
      await waitFor(() => {
        expect(screen.getByText(/waiting for the next scheduled check/i)).toBeInTheDocument();
      });
      expect(screen.getByText(/status unknown/i)).toBeInTheDocument();

      // Act: the deferred fetch settles by the next poll tick.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10000);
      });

      // Assert: the page reflects the real, current outcome -- not stuck on the initial load's.
      await waitFor(() => {
        expect(screen.getByText(/all sources responded/i)).toBeInTheDocument();
      });
      expect(screen.getByText(/stories grouped normally/i)).toBeInTheDocument();
      expect(screen.queryByText(/waiting for the next scheduled check/i)).not.toBeInTheDocument();
    });

    it("polls /api/search/status once results exist, even when every headline is already fully resolved", async () => {
      // Arrange: nothing left to resolve -- the old behavior would never have polled here at all.
      vi.useFakeTimers({ shouldAdvanceTime: true });
      fetchSearch.mockResolvedValue(
        response({ sentiment: "ok", days: dayWith(headline({ sentiment_status: "ok", sentiment_enum: "positive", sentiment_score: 80 })) }),
      );
      fetchSearchStatus.mockResolvedValue(
        statusResponse({
          sentiment: "ok",
          days: dayWith(headline({ sentiment_status: "ok", sentiment_enum: "positive", sentiment_score: 80 })),
        }),
      );

      // Act: load via the URL, then fast-forward one poll interval.
      renderSearchPage(["/search?ticker=AAPL"]);
      await waitFor(() => {
        expect(screen.getByText(/analysis complete/i)).toBeInTheDocument();
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10000);
      });

      // Assert: it polled anyway -- live refresh has no "nothing left to check" stop condition.
      expect(fetchSearchStatus).toHaveBeenCalledWith("AAPL");
    });

    it("polls /api/search/status while a headline still has no sentiment attempt, and merges the resolved update", async () => {
      // Arrange: fake timers so the poll interval can be fast-forwarded; the initial search still has a pending headline.
      vi.useFakeTimers({ shouldAdvanceTime: true });
      fetchSearch.mockResolvedValue(
        response({ sentiment: "processing", days: dayWith(headline({ title: "Resolved via poll", url: "https://example.com/resolved" })) }),
      );
      fetchSearchStatus.mockResolvedValue(
        statusResponse({
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
        }),
      );

      // Act: load via the URL, wait for the initial "processing" render.
      renderSearchPage(["/search?ticker=AAPL"]);
      await waitFor(() => {
        expect(screen.getByText(/in progress/i)).toBeInTheDocument();
      });
      expect(fetchSearchStatus).not.toHaveBeenCalled();

      // Fast-forward past one poll interval.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10000);
      });

      // Assert: the poll fired for the same ticker, and its result (sentiment + days) merged into the page --
      // note days came only from the poll, proving providers/status/grouping from the original fetch survived the merge.
      expect(fetchSearchStatus).toHaveBeenCalledWith("AAPL");
      await waitFor(() => {
        expect(screen.getByText(/analysis complete/i)).toBeInTheDocument();
      });
      expect(screen.getByRole("link", { name: "Resolved via poll" })).toBeInTheDocument();
    });

    it("keeps polling indefinitely -- reaching a terminal status on every headline never stops it", async () => {
      // Arrange: same pending -> resolved setup as above.
      vi.useFakeTimers({ shouldAdvanceTime: true });
      fetchSearch.mockResolvedValue(response({ sentiment: "processing", days: dayWith(headline()) }));
      fetchSearchStatus.mockResolvedValue(
        statusResponse({
          sentiment: "ok",
          days: dayWith(headline({ sentiment_status: "ok", sentiment_enum: "positive", sentiment_score: 80 })),
        }),
      );

      renderSearchPage(["/search?ticker=AAPL"]);
      await waitFor(() => {
        expect(screen.getByText(/in progress/i)).toBeInTheDocument();
      });

      // Act: advance past the tick that resolves it, then several more intervals' worth of time.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10000);
      });
      await waitFor(() => {
        expect(fetchSearchStatus).toHaveBeenCalledTimes(1);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(40000);
      });

      // Assert: polling never stops on its own -- four more intervals means four more calls.
      expect(fetchSearchStatus).toHaveBeenCalledTimes(5);
    });

    it("keeps polling even when the page-level status reads error, as long as another headline is still pending", async () => {
      // Arrange: one headline already permanently failed (masking page-level status to "error"), but a
      // second in the same batch hasn't been attempted yet -- polling off the coarse field alone would strand it.
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
      fetchSearchStatus.mockResolvedValue(
        statusResponse({
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
        }),
      );

      renderSearchPage(["/search?ticker=AAPL"]);
      await waitFor(() => {
        expect(screen.getByText(/analysis failed/i)).toBeInTheDocument();
      });

      // Act: fast-forward one poll interval.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10000);
      });

      // Assert: the poll fired despite the page reading "error" the whole time, and the second
      // headline's result made it onto the page.
      expect(fetchSearchStatus).toHaveBeenCalledWith("AAPL");
      await waitFor(() => {
        expect(screen.getByText("neutral · 55")).toBeInTheDocument();
      });
    });

    it("pauses polling while the page is hidden, and checks immediately on becoming visible again", async () => {
      // Arrange
      vi.useFakeTimers({ shouldAdvanceTime: true });
      fetchSearch.mockResolvedValue(response({ days: dayWith(headline()) }));
      fetchSearchStatus.mockResolvedValue(statusResponse({ sentiment: "ok", days: dayWith(headline()) }));

      renderSearchPage(["/search?ticker=AAPL"]);
      await waitFor(() => {
        expect(screen.getByText(/analysis complete/i)).toBeInTheDocument();
      });

      // Act: background the tab, then let two full poll intervals' worth of time pass.
      setVisibility("hidden");
      await act(async () => {
        await vi.advanceTimersByTimeAsync(20000);
      });

      // Assert: nothing happened while hidden.
      expect(fetchSearchStatus).not.toHaveBeenCalled();

      // Act: switch back.
      await act(async () => {
        setVisibility("visible");
      });

      // Assert: a check fires immediately on refocus, without waiting for the next interval tick.
      await waitFor(() => {
        expect(fetchSearchStatus).toHaveBeenCalledTimes(1);
      });
    });

    it("shows a live 'last refresh Ns ago' indicator that counts up and resets on every successful check", async () => {
      // Arrange
      vi.useFakeTimers({ shouldAdvanceTime: true });
      fetchSearch.mockResolvedValue(response({ days: dayWith(headline()) }));
      fetchSearchStatus.mockResolvedValue(statusResponse({ sentiment: "ok", days: dayWith(headline()) }));

      renderSearchPage(["/search?ticker=AAPL"]);
      await waitFor(() => {
        expect(screen.getByText(/analysis complete/i)).toBeInTheDocument();
      });

      // Assert: starts at 0 right after the initial load counts as a refresh.
      expect(screen.getByText("last refresh 0s ago")).toBeInTheDocument();

      // Act: three seconds pass, no poll due yet (interval is 10s).
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });
      expect(screen.getByText("last refresh 3s ago")).toBeInTheDocument();

      // Act: cross the 10s poll interval -- a successful check resets the counter, even though
      // nothing in the response actually changed.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(7000);
      });
      expect(screen.getByText("last refresh 0s ago")).toBeInTheDocument();
    });

    it("leaves the displayed results and the refresh counter untouched when a background check fails", async () => {
      // Arrange
      vi.useFakeTimers({ shouldAdvanceTime: true });
      fetchSearch.mockResolvedValue(
        response({ days: dayWith(headline({ title: "Still here", url: "https://example.com/still-here" })) }),
      );
      fetchSearchStatus.mockRejectedValue(new Error("network hiccup"));

      renderSearchPage(["/search?ticker=AAPL"]);
      await waitFor(() => {
        expect(screen.getByText(/analysis complete/i)).toBeInTheDocument();
      });

      // Act: cross a poll interval where the check fails.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10000);
      });
      await waitFor(() => {
        expect(fetchSearchStatus).toHaveBeenCalledTimes(1);
      });

      // Assert: results are unaffected, and the counter kept counting up from the last real
      // success -- 10s since load, none of it reset by the failed check.
      expect(screen.getByRole("link", { name: "Still here" })).toBeInTheDocument();
      expect(screen.getByText("last refresh 10s ago")).toBeInTheDocument();
    });

    it("discards a stale poll response that resolves after a newer one -- refocus racing an in-flight check", async () => {
      // Arrange: two controlled promises, so the test decides which one resolves first.
      vi.useFakeTimers({ shouldAdvanceTime: true });
      fetchSearch.mockResolvedValue(response({ days: dayWith(headline()) }));
      let resolveFirst!: (v: searchModule.SearchStatusResponse) => void;
      let resolveSecond!: (v: searchModule.SearchStatusResponse) => void;
      fetchSearchStatus
        .mockImplementationOnce(() => new Promise((resolve) => (resolveFirst = resolve)))
        .mockImplementationOnce(() => new Promise((resolve) => (resolveSecond = resolve)));

      renderSearchPage(["/search?ticker=AAPL"]);
      await waitFor(() => {
        expect(screen.getByText(/analysis complete/i)).toBeInTheDocument();
      });

      // Act: the regular 10s poll starts (call #1, left in flight), then a background+refocus
      // cycle fires an immediate second check (call #2) before call #1 has resolved.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10000);
      });
      expect(fetchSearchStatus).toHaveBeenCalledTimes(1);
      setVisibility("hidden");
      await act(async () => {
        setVisibility("visible");
      });
      expect(fetchSearchStatus).toHaveBeenCalledTimes(2);

      // Act: the newer call (#2) resolves first, the older one (#1) resolves after it.
      await act(async () => {
        resolveSecond(statusResponse({ sentiment: "ok", days: dayWith(headline({ title: "Newer", url: "https://example.com/newer" })) }));
      });
      await act(async () => {
        resolveFirst(statusResponse({ sentiment: "ok", days: dayWith(headline({ title: "Stale", url: "https://example.com/stale" })) }));
      });

      // Assert: the stale, later-resolving response never overwrites the newer one already applied.
      expect(screen.getByRole("link", { name: "Newer" })).toBeInTheDocument();
      expect(screen.queryByRole("link", { name: "Stale" })).not.toBeInTheDocument();
    });
  });

  // The add/remove button (spec 0008): sourced from Layout's shared watchlist state via
  // useOutletContext(), not a separate fetch -- see renderSearchPage's own context param.
  describe("watchlist button", () => {
    it("is absent while signed out, even once results are showing", async () => {
      fetchSearch.mockResolvedValue(response({ days: dayWith(headline()) }));

      renderSearchPage(["/search?ticker=AAPL"], { isSignedIn: false });
      await waitFor(() => expect(screen.getByText(/analysis complete/i)).toBeInTheDocument());

      expect(screen.queryByRole("button", { name: /watchlist/i })).not.toBeInTheDocument();
    });

    it("shows \"Add AAPL to watchlist\" when signed in and the ticker isn't already watchlisted", async () => {
      fetchSearch.mockResolvedValue(response({ days: dayWith(headline()) }));

      renderSearchPage(["/search?ticker=AAPL"], { isSignedIn: true, entries: [] });
      await waitFor(() => expect(screen.getByText(/analysis complete/i)).toBeInTheDocument());

      expect(screen.getByRole("button", { name: "Add AAPL to watchlist" })).toBeInTheDocument();
    });

    it("shows \"Remove AAPL from watchlist\" when the current ticker is already on the watchlist", async () => {
      fetchSearch.mockResolvedValue(response({ days: dayWith(headline()) }));

      renderSearchPage(["/search?ticker=AAPL"], {
        isSignedIn: true,
        entries: [{ ticker: "AAPL", added_at: "2026-09-30T00:00:00Z", new_headlines: 0 }],
      });
      await waitFor(() => expect(screen.getByText(/analysis complete/i)).toBeInTheDocument());

      expect(screen.getByRole("button", { name: "Remove AAPL from watchlist" })).toBeInTheDocument();
    });

    it("calls the context's add() with the current ticker when clicked", async () => {
      fetchSearch.mockResolvedValue(response({ days: dayWith(headline()) }));
      const add = vi.fn().mockResolvedValue(undefined);
      const user = userEvent.setup();

      renderSearchPage(["/search?ticker=AAPL"], { isSignedIn: true, entries: [], add });
      await waitFor(() => expect(screen.getByText(/analysis complete/i)).toBeInTheDocument());
      await user.click(screen.getByRole("button", { name: "Add AAPL to watchlist" }));

      expect(add).toHaveBeenCalledWith("AAPL");
    });

    it("calls the context's remove() with the current ticker when clicked", async () => {
      fetchSearch.mockResolvedValue(response({ days: dayWith(headline()) }));
      const remove = vi.fn().mockResolvedValue(undefined);
      const user = userEvent.setup();

      renderSearchPage(["/search?ticker=AAPL"], {
        isSignedIn: true,
        entries: [{ ticker: "AAPL", added_at: "2026-09-30T00:00:00Z", new_headlines: 0 }],
        remove,
      });
      await waitFor(() => expect(screen.getByText(/analysis complete/i)).toBeInTheDocument());
      await user.click(screen.getByRole("button", { name: "Remove AAPL from watchlist" }));

      expect(remove).toHaveBeenCalledWith("AAPL");
    });
  });
});
