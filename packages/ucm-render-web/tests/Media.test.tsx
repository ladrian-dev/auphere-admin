import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Media } from "../src";
import { FIXTURES } from "./fixtures";

const fxImage = FIXTURES["media_image"]!;
if (fxImage.type !== "media") throw new Error("fixture drift");

describe("Media", () => {
  it("snapshot: image", () => {
    const { container } = render(<Media ucm={fxImage} />);
    expect(container.innerHTML).toMatchSnapshot();
  });

  it("image uses caption as alt", () => {
    render(<Media ucm={fxImage} />);
    const img = screen.getByRole("img");
    expect(img).toHaveAttribute("alt", fxImage.content.caption);
  });

  it("falls back to fallback_text when no caption", () => {
    const noCaption = {
      ...fxImage,
      content: { ...fxImage.content, caption: undefined },
    } as typeof fxImage;
    render(<Media ucm={noCaption} />);
    expect(screen.getByRole("img")).toHaveAttribute(
      "alt",
      fxImage.fallback_text,
    );
  });

  it("video kind renders <video controls>", () => {
    const ucm = {
      ...fxImage,
      content: {
        kind: "video" as const,
        url: "https://example.com/v.mp4",
        caption: "demo",
      },
    };
    const { container } = render(<Media ucm={ucm} />);
    expect(container.querySelector("video")).toBeTruthy();
    expect(container.querySelector("video")).toHaveAttribute("controls");
  });

  it("document kind renders a labelled link with filename", () => {
    const ucm = {
      ...fxImage,
      content: {
        kind: "document" as const,
        url: "https://example.com/menu.pdf",
        filename: "menu.pdf",
      },
    };
    render(<Media ucm={ucm} />);
    expect(
      screen.getByRole("link", { name: /Open document: menu.pdf/ }),
    ).toBeInTheDocument();
  });
});
