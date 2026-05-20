import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// vitest config sets `globals: false`, so testing-library's auto-cleanup
// (which fires on the global `afterEach`) does not run. Wire it manually
// — otherwise the DOM accumulates across tests and `getByLabelText`
// queries return multiple matches.
afterEach(() => {
  cleanup();
});
