import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Text } from "../src";
import { FIXTURES } from "./fixtures";

describe("Text", () => {
  it("snapshot: plain", () => {
    const ucm = FIXTURES["text_plain"]!;
    if (ucm.type !== "text") throw new Error("fixture drift");
    const { container } = render(<Text ucm={ucm} />);
    expect(container.innerHTML).toMatchSnapshot();
  });

  it("snapshot: markdown body rendered as plain text", () => {
    const ucm = FIXTURES["text_markdown"]!;
    if (ucm.type !== "text") throw new Error("fixture drift");
    const { container, getByLabelText } = render(<Text ucm={ucm} />);
    expect(container.innerHTML).toMatchSnapshot();
    // Markdown is NOT parsed — the raw asterisks must be in the DOM.
    expect(getByLabelText("agent message").textContent).toContain("**Oferta**");
  });
});
