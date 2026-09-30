import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SearchStatus } from "./SearchStatus";

describe("SearchStatus", () => {
  it("shows a distinct, human-readable message for success -- not just the failure states", () => {
    render(<SearchStatus status="success" />);
    expect(screen.getByText(/all sources responded/i)).toBeInTheDocument();
  });

  it("shows a distinct message for partial_failure", () => {
    render(<SearchStatus status="partial_failure" />);
    expect(screen.getByText(/some results may be missing/i)).toBeInTheDocument();
  });

  it("shows a distinct message for complete_failure", () => {
    render(<SearchStatus status="complete_failure" />);
    expect(screen.getByText(/showing previously saved data/i)).toBeInTheDocument();
  });

  it("shows a distinct, non-error message for deferred -- a postponement, not a failure", () => {
    render(<SearchStatus status="deferred" />);
    expect(screen.getByText(/waiting for the next scheduled check/i)).toBeInTheDocument();
    expect(screen.queryByText(/couldn't fetch/i)).not.toBeInTheDocument();
  });

  it("never renders the raw status value itself", () => {
    render(<SearchStatus status="partial_failure" />);
    expect(screen.queryByText("partial_failure")).not.toBeInTheDocument();
  });
});
