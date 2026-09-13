// Registers @testing-library/jest-dom's matchers (toBeInTheDocument(),
// toHaveValue(), toBeDisabled(), etc.) on Vitest's own `expect`.
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// React Testing Library's automatic per-test cleanup only self-registers
// when it detects a global `afterEach` -- this project deliberately keeps
// `test.globals` off (see vitest.config.mts), so without this, elements
// from one test leak into the next render. Found live: a "via Yahoo" from
// an earlier test bled into a later one asserting outlet was absent.
afterEach(() => {
  cleanup();
});
