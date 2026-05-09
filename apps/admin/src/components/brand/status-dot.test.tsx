import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusDot } from "./status-dot";

describe("StatusDot", () => {
  it("renders a hidden span by default", () => {
    const { container } = render(<StatusDot />);
    const span = container.querySelector("span");
    expect(span).toBeInTheDocument();
    expect(span).toHaveAttribute("aria-hidden", "true");
  });

  it("applies the requested tone class", () => {
    const { container } = render(<StatusDot tone="danger" />);
    const span = container.querySelector("span");
    expect(span?.className).toMatch(/status-danger/);
  });

  it("respects the pulse flag", () => {
    const { container } = render(<StatusDot pulse />);
    const span = container.querySelector("span");
    expect(span?.className).toMatch(/animate-pulse/);
  });
});
