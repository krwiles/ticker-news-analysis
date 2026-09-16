// Registers @testing-library/jest-dom's matchers (toBeInTheDocument(),
// toHaveValue(), toBeDisabled(), etc.) on Vitest's own `expect`.
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// RTL's auto-cleanup needs a global afterEach, and this project keeps test.globals off --
// without this, elements leak between tests (found live: a stray "via Yahoo" from an earlier test).
afterEach(() => {
  cleanup();
});
