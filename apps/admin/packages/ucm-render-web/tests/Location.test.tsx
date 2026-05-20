import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Location } from "../src";
import { FIXTURES } from "./fixtures";

const fx = FIXTURES["location"]!;
if (fx.type !== "location") throw new Error("fixture drift");

describe("Location", () => {
  it("snapshot", () => {
    const { container } = render(<Location ucm={fx} />);
    expect(container.innerHTML).toMatchSnapshot();
  });

  it("renders coordinates with fixed precision", () => {
    render(<Location ucm={fx} />);
    expect(
      screen.getByText(/4\.609700,\s*-74\.081700/),
    ).toBeInTheDocument();
  });

  it("'Open in maps' link uses geo: scheme", () => {
    render(<Location ucm={fx} />);
    const link = screen.getByRole("link", { name: /Open .* in maps/ });
    expect(link).toHaveAttribute(
      "href",
      `geo:${fx.content.latitude},${fx.content.longitude}`,
    );
  });
});
