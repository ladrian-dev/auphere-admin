import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Flow } from "../src";
import { FIXTURES } from "./fixtures";

const fx = FIXTURES["flow"]!;
if (fx.type !== "flow") throw new Error("fixture drift");

describe("Flow", () => {
  it("snapshot", () => {
    const { container } = render(<Flow ucm={fx} />);
    expect(container.innerHTML).toMatchSnapshot();
  });

  it("fires onInteractive with the flow_id as id on click", async () => {
    const onInteractive = vi.fn();
    render(<Flow ucm={fx} onInteractive={onInteractive} />);
    await userEvent.click(
      screen.getByRole("button", { name: /Iniciar|flow/i }),
    );
    expect(onInteractive).toHaveBeenCalledWith({
      id: fx.content.flow_id,
      title: fx.content.button_text,
      source: "flow",
    });
  });

  it("exposes flow_id in a data attribute for the QA Inspector", () => {
    const { container } = render(<Flow ucm={fx} />);
    const root = container.querySelector("[data-ucm-flow-id]");
    expect(root?.getAttribute("data-ucm-flow-id")).toBe(fx.content.flow_id);
  });
});
