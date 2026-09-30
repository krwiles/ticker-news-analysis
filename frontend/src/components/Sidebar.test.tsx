import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { Sidebar } from "./Sidebar";
import type { WatchlistEntry } from "../watchlist";

function renderSidebar(entries: WatchlistEntry[], onRemove = vi.fn()) {
  return {
    onRemove,
    ...render(
      <MemoryRouter>
        <Sidebar entries={entries} onRemove={onRemove} />
      </MemoryRouter>,
    ),
  };
}

describe("Sidebar", () => {
  it("renders nothing when the watchlist is empty", () => {
    const { container } = renderSidebar([]);

    expect(container).toBeEmptyDOMElement();
  });

  it("renders each entry's ticker and its current count", () => {
    renderSidebar([
      { ticker: "MSFT", added_at: "2026-09-30T00:00:00Z", new_headlines: 3 },
      { ticker: "AAPL", added_at: "2026-09-30T01:00:00Z", new_headlines: 0 },
    ]);

    expect(screen.getByText("MSFT")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
  });

  it("omits a count badge for an entry with zero new headlines", () => {
    renderSidebar([{ ticker: "AAPL", added_at: "2026-09-30T01:00:00Z", new_headlines: 0 }]);

    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("links each ticker to its own search page", () => {
    renderSidebar([{ ticker: "MSFT", added_at: "2026-09-30T00:00:00Z", new_headlines: 0 }]);

    expect(screen.getByRole("link", { name: /MSFT/ })).toHaveAttribute("href", "/search?ticker=MSFT");
  });

  it("calls onRemove with the ticker when its remove control is clicked", async () => {
    const user = userEvent.setup();
    const { onRemove } = renderSidebar([{ ticker: "MSFT", added_at: "2026-09-30T00:00:00Z", new_headlines: 0 }]);

    await user.click(screen.getByRole("button", { name: /remove msft/i }));

    expect(onRemove).toHaveBeenCalledWith("MSFT");
  });
});
