/**
 * Accessibility smoke tests — run axe-core against each fixture and
 * fail on serious or critical violations. Minor (e.g. colour contrast)
 * is allowed at the component level because the QA host owns the
 * theme; the components only commit to structure.
 *
 * The aim is to catch missing aria-label, mislabelled roles, broken
 * focus order — bugs that a snapshot wouldn't detect.
 */
import axe from "axe-core";
import { render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { UCMRenderer } from "../src";
import { FIXTURES } from "./fixtures";

const SEVERITIES = new Set(["serious", "critical"]);

afterEach(() => {
  document.body.innerHTML = "";
});

describe("a11y: every UCM type passes axe (serious/critical)", () => {
  for (const [key, ucm] of Object.entries(FIXTURES)) {
    it(`${key} (${ucm.type})`, async () => {
      const { container } = render(<UCMRenderer ucm={ucm} />);
      // Mount into body so axe walks the live DOM.
      document.body.appendChild(container.cloneNode(true));
      const results = await axe.run(document.body, {
        runOnly: {
          type: "tag",
          values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
        },
      });
      const blocking = results.violations.filter((v) =>
        SEVERITIES.has(v.impact ?? "minor"),
      );
      if (blocking.length > 0) {
        // Include the rule + element snippet in the failure message so
        // the operator running tests can copy it straight into the fix.
        const msg = blocking
          .map(
            (v) =>
              `${v.id} (${v.impact}): ${v.description}\n` +
              v.nodes
                .map((n) => `  → ${n.html}`)
                .join("\n"),
          )
          .join("\n\n");
        throw new Error(`a11y violations:\n${msg}`);
      }
      expect(blocking).toEqual([]);
    });
  }
});
