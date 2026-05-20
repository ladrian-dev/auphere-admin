import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { QuickReplies } from "../src";
import { FIXTURES } from "./fixtures";

describe("QuickReplies (WhatsApp preview)", () => {
  it("renders up to 3 buttons inline", () => {
    const fx = FIXTURES["quick_replies_3"]!;
    if (fx.type !== "quick_replies") throw new Error("fixture drift");
    render(<QuickReplies ucm={fx} />);
    expect(screen.getByLabelText("Reply button: Sí")).toBeInTheDocument();
    expect(screen.getByLabelText("Reply button: No")).toBeInTheDocument();
    expect(screen.getByLabelText("Reply button: Más info")).toBeInTheDocument();
  });

  it("clamps to 3 buttons and shows a truncation notice when more are sent", () => {
    const fx = FIXTURES["quick_replies_5"]!;
    if (fx.type !== "quick_replies") throw new Error("fixture drift");
    render(<QuickReplies ucm={fx} />);
    // Only first 3 visible as buttons
    expect(screen.getByLabelText("Reply button: Corte")).toBeInTheDocument();
    expect(screen.getByLabelText("Reply button: Color")).toBeInTheDocument();
    expect(screen.getByLabelText("Reply button: Peinado")).toBeInTheDocument();
    // 4 and 5 NOT rendered as buttons
    expect(screen.queryByLabelText("Reply button: Barba")).toBeNull();
    expect(screen.queryByLabelText("Reply button: Manicure")).toBeNull();
    // Truncation notice instead
    expect(
      screen.getByLabelText("Truncation notice"),
    ).toHaveTextContent(/2 more/);
  });
});
