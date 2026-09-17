import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusTile } from "./StatusTile";

describe("StatusTile", () => {
  it("renders a single-line detail as one line", () => {
    // Arrange + act: render with a plain, single-line detail.
    render(<StatusTile name="UI" status="ok" detail="You're looking at it" />);
    // Assert: the detail text appears.
    expect(screen.getByText("You're looking at it")).toBeInTheDocument();
  });

  it("splits a \\n-separated detail into one line each", () => {
    // Arrange + act: render with a multi-part detail, e.g. Database's per-table counts.
    render(<StatusTile name="Database" status="ok" detail={"3 companies\n428 headlines\n210 stories"} />);
    // Assert: each part renders as its own line, not one wrapped line.
    expect(screen.getByText("3 companies")).toBeInTheDocument();
    expect(screen.getByText("428 headlines")).toBeInTheDocument();
    expect(screen.getByText("210 stories")).toBeInTheDocument();
  });

  it("renders no detail lines at all when detail is omitted", () => {
    // Arrange + act: render with no detail.
    const { container } = render(<StatusTile name="API" status="ok" />);
    // Assert: only the tile name paragraph exists, nothing else.
    expect(container.querySelectorAll("p")).toHaveLength(1);
  });
});
