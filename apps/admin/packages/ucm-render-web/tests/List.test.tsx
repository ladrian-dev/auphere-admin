import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { List } from "../src";
import { FIXTURES } from "./fixtures";

const fx = FIXTURES["list_small"]!;
if (fx.type !== "list") throw new Error("fixture drift");

describe("List", () => {
  it("snapshot", () => {
    const { container } = render(<List ucm={fx} />);
    expect(container.innerHTML).toMatchSnapshot();
  });

  it("fires onInteractive when a row is selected", async () => {
    const onInteractive = vi.fn();
    render(<List ucm={fx} onInteractive={onInteractive} />);
    await userEvent.click(screen.getByRole("option", { name: /Martes/ }));
    expect(onInteractive).toHaveBeenCalledWith({
      id: "tue",
      title: "Martes",
      source: "list",
    });
  });

  it("each row exposes title+description to a screen reader", () => {
    render(<List ucm={fx} />);
    const opt = screen.getByRole("option", { name: "Martes. Tarde 16:00" });
    expect(opt).toBeInTheDocument();
  });
});
