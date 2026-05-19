import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { UCMRenderer } from "../src";
import { FIXTURES } from "./fixtures";

describe("UCMRenderer dispatch", () => {
  for (const [key, ucm] of Object.entries(FIXTURES)) {
    it(`renders ${key} (${ucm.type}) without throwing`, () => {
      const { container } = render(<UCMRenderer ucm={ucm} />);
      expect(container.firstChild).toBeTruthy();
      // The component must stamp the type for debugging / QA Inspector.
      // composite has its own container with data-ucm-type set; everything
      // else has a single root with the attribute.
      const root = container.querySelector("[data-ucm-type]");
      expect(root?.getAttribute("data-ucm-type")).toBe(ucm.type);
    });
  }

  it("falls back gracefully on unknown type", () => {
    const bogus = {
      ...FIXTURES["text_plain"]!,
      type: "future_type" as never,
    };
    const { getByRole } = render(<UCMRenderer ucm={bogus} />);
    expect(getByRole("alert")).toHaveTextContent(
      /Unrecognised UCM type. Fallback:/,
    );
  });
});
