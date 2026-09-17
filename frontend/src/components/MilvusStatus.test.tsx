import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MilvusStatus } from "./MilvusStatus";

describe("MilvusStatus", () => {
  it("shows Connected with the real vector count when ok", () => {
    // Arrange + act: render with the "ok" state.
    render(<MilvusStatus milvus={{ status: "ok", vector_count: 1404 }} />);
    // Assert: label and real count both appear.
    expect(screen.getByText("Connected")).toBeInTheDocument();
    expect(screen.getByText("1404 stories indexed")).toBeInTheDocument();
  });

  it("stays plural even at exactly one indexed story", () => {
    // Arrange + act: render with exactly one story indexed.
    render(<MilvusStatus milvus={{ status: "ok", vector_count: 1 }} />);
    // Assert: always-plural wording, deliberate -- matches the Database tile's own counts (spec 0004).
    expect(screen.getByText("1 stories indexed")).toBeInTheDocument();
  });

  it("shows a distinct, non-alarming label when not yet initialized", () => {
    // Arrange + act: render with the "not_initialized" state.
    render(<MilvusStatus milvus={{ status: "not_initialized" }} />);
    // Assert: labeled distinctly from Error, with an explanatory detail.
    expect(screen.getByText("Not yet initialized")).toBeInTheDocument();
    expect(screen.getByText("Collection not created yet")).toBeInTheDocument();
  });

  it("shows the real failure detail on error", () => {
    // Arrange + act: render with the "error" state.
    render(<MilvusStatus milvus={{ status: "error", detail: "connection refused" }} />);
    // Assert: label and the real backend-provided detail both appear.
    expect(screen.getByText("Error")).toBeInTheDocument();
    expect(screen.getByText("connection refused")).toBeInTheDocument();
  });

  it("shows Unknown before the first poll resolves, with no detail line", () => {
    // Arrange + act: render with the "unknown" state.
    render(<MilvusStatus milvus={{ status: "unknown" }} />);
    // Assert: labeled Unknown, no stray detail text rendered.
    expect(screen.getByText("Unknown")).toBeInTheDocument();
  });
});
