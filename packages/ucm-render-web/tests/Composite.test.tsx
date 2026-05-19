import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { UCMRenderer } from "../src";
import { FIXTURES } from "./fixtures";

const fx = FIXTURES["composite"]!;
if (fx.type !== "composite") throw new Error("fixture drift");

describe("Composite (via UCMRenderer)", () => {
  it("snapshot", () => {
    const { container } = render(<UCMRenderer ucm={fx} />);
    expect(container.innerHTML).toMatchSnapshot();
  });

  it("renders each child", () => {
    render(<UCMRenderer ucm={fx} />);
    // child 1: text "Hola"
    expect(screen.getByText(/Hola/)).toBeInTheDocument();
    // child 2: quick_replies buttons
    expect(screen.getByRole("button", { name: "Sí" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "No" })).toBeInTheDocument();
  });

  it("propagates onInteractive from a nested child", async () => {
    const onInteractive = vi.fn();
    render(<UCMRenderer ucm={fx} onInteractive={onInteractive} />);
    await userEvent.click(screen.getByRole("button", { name: "Sí" }));
    expect(onInteractive).toHaveBeenCalledWith({
      id: "yes",
      title: "Sí",
      source: "quick_reply",
    });
  });
});
