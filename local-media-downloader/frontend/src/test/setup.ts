import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Testing Library doesn't auto-unmount between tests unless this runs -
// without it, DOM from a previous test's render() stays mounted and text
// queries in later tests start matching multiple elements.
afterEach(() => {
  cleanup();
});
