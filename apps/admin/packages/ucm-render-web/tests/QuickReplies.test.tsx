import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { QuickReplies } from "../src";
import { FIXTURES } from "./fixtures";

const fx3 = FIXTURES["quick_replies_3"]!;
if (fx3.type !== "quick_replies") throw new Error("fixture drift");

describe("QuickReplies", () => {
  it("snapshot", () => {
    const { container } = render(<QuickReplies ucm={fx3} />);
    expect(container.innerHTML).toMatchSnapshot();
  });

  it("fires onInteractive with the right (id, title) on click", async () => {
    const onInteractive = vi.fn();
    render(<QuickReplies ucm={fx3} onInteractive={onInteractive} />);
    await userEvent.click(screen.getByRole("button", { name: "Sí" }));
    expect(onInteractive).toHaveBeenCalledWith({
      id: "yes",
      title: "Sí",
      source: "quick_reply",
    });
  });

  it("arrow keys cycle focus between buttons", () => {
    render(<QuickReplies ucm={fx3} />);
    const yes = screen.getByRole("button", { name: "Sí" });
    const no = screen.getByRole("button", { name: "No" });
    const more = screen.getByRole("button", { name: "Más info" });
    yes.focus();
    expect(document.activeElement).toBe(yes);
    fireEvent.keyDown(yes, { key: "ArrowRight" });
    expect(document.activeElement).toBe(no);
    fireEvent.keyDown(no, { key: "ArrowRight" });
    expect(document.activeElement).toBe(more);
    // Wrap-around
    fireEvent.keyDown(more, { key: "ArrowRight" });
    expect(document.activeElement).toBe(yes);
    fireEvent.keyDown(yes, { key: "ArrowLeft" });
    expect(document.activeElement).toBe(more);
  });

  it("non-arrow keys are ignored", () => {
    render(<QuickReplies ucm={fx3} />);
    const yes = screen.getByRole("button", { name: "Sí" });
    yes.focus();
    fireEvent.keyDown(yes, { key: "Enter" });
    // Focus unchanged
    expect(document.activeElement).toBe(yes);
  });

  it("groups buttons under aria-labelledby for screen readers", () => {
    render(<QuickReplies ucm={fx3} />);
    const group = screen.getByRole("group");
    expect(group).toHaveAttribute("aria-labelledby");
  });
});
