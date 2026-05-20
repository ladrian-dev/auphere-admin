import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { WhatsAppPreview } from "../src";
import { FIXTURES } from "./fixtures";

describe("WhatsAppPreview dispatch", () => {
  for (const [key, ucm] of Object.entries(FIXTURES)) {
    it(`renders ${key} (${ucm.type}) inside a phone frame`, () => {
      const { container } = render(<WhatsAppPreview ucm={ucm} />);
      // Always wrapped in a phone frame
      expect(container.querySelector("[data-wa-preview-root]")).toBeTruthy();
      // The bubble (or composite root) stamps the type
      const typed = container.querySelector("[data-wa-type]");
      expect(typed?.getAttribute("data-wa-type")).toBe(ucm.type);
    });
  }

  it("snapshot for each top-level type", () => {
    for (const [key, ucm] of Object.entries(FIXTURES)) {
      const { container, unmount } = render(<WhatsAppPreview ucm={ucm} />);
      expect(container.innerHTML).toMatchSnapshot(`${key}-${ucm.type}`);
      unmount();
    }
  });

  it("unknown type falls back gracefully", () => {
    const bogus = {
      ...FIXTURES["text_plain"]!,
      type: "carousel" as never,
    };
    render(<WhatsAppPreview ucm={bogus} />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      /Unrecognised UCM type/,
    );
  });
});
