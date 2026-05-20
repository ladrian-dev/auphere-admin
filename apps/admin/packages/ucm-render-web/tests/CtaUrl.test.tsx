import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CtaUrl } from "../src";
import { FIXTURES } from "./fixtures";

const fx = FIXTURES["cta_url"]!;
if (fx.type !== "cta_url") throw new Error("fixture drift");

describe("CtaUrl", () => {
  it("snapshot", () => {
    const { container } = render(<CtaUrl ucm={fx} />);
    expect(container.innerHTML).toMatchSnapshot();
  });

  it("renders a real <a> with target=_blank and rel=noopener", () => {
    render(<CtaUrl ucm={fx} />);
    const link = screen.getByRole("button", { name: /Reservar/ });
    expect(link.tagName).toBe("A");
    expect(link).toHaveAttribute("href", fx.content.url);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("also fires onInteractive on click (for QA audit)", async () => {
    const onInteractive = vi.fn();
    render(<CtaUrl ucm={fx} onInteractive={onInteractive} />);
    await userEvent.click(screen.getByRole("button", { name: /Reservar/ }));
    expect(onInteractive).toHaveBeenCalledWith({
      id: fx.message_id,
      title: fx.content.button_title,
      source: "cta_url",
    });
  });
});
