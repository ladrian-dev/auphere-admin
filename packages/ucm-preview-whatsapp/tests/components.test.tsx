/** Per-component snapshots so a copy in one component doesn't reflow others. */
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  CtaUrl,
  Flow,
  List,
  Location,
  Media,
  Text,
} from "../src";
import { FIXTURES } from "./fixtures";

describe("WhatsApp components — snapshots", () => {
  it("Text", () => {
    const fx = FIXTURES["text_plain"]!;
    if (fx.type !== "text") throw new Error("drift");
    const { container } = render(<Text ucm={fx} />);
    expect(container.innerHTML).toMatchSnapshot();
  });

  it("List", () => {
    const fx = FIXTURES["list_small"]!;
    if (fx.type !== "list") throw new Error("drift");
    const { container } = render(<List ucm={fx} />);
    expect(container.innerHTML).toMatchSnapshot();
  });

  it("CtaUrl", () => {
    const fx = FIXTURES["cta_url"]!;
    if (fx.type !== "cta_url") throw new Error("drift");
    const { container } = render(<CtaUrl ucm={fx} />);
    expect(container.innerHTML).toMatchSnapshot();
  });

  it("Media (image)", () => {
    const fx = FIXTURES["media_image"]!;
    if (fx.type !== "media") throw new Error("drift");
    const { container } = render(<Media ucm={fx} />);
    expect(container.innerHTML).toMatchSnapshot();
  });

  it("Location", () => {
    const fx = FIXTURES["location"]!;
    if (fx.type !== "location") throw new Error("drift");
    const { container } = render(<Location ucm={fx} />);
    expect(container.innerHTML).toMatchSnapshot();
  });

  it("Flow", () => {
    const fx = FIXTURES["flow"]!;
    if (fx.type !== "flow") throw new Error("drift");
    const { container } = render(<Flow ucm={fx} />);
    expect(container.innerHTML).toMatchSnapshot();
  });
});

describe("Media — variant rendering", () => {
  const base = FIXTURES["media_image"]!;
  if (base.type !== "media") throw new Error("drift");

  it("video kind shows the play overlay", () => {
    const ucm = {
      ...base,
      content: { kind: "video" as const, url: "https://x/v.mp4", caption: "demo" },
    };
    const { getByLabelText } = render(<Media ucm={ucm} />);
    expect(getByLabelText(/Video: demo/)).toBeInTheDocument();
  });

  it("audio kind shows the audio strip", () => {
    const ucm = {
      ...base,
      content: { kind: "audio" as const, url: "https://x/a.mp3" },
    };
    const { getByLabelText } = render(<Media ucm={ucm} />);
    expect(getByLabelText(/Audio:/)).toBeInTheDocument();
  });

  it("document kind shows the filename row", () => {
    const ucm = {
      ...base,
      content: {
        kind: "document" as const,
        url: "https://x/menu.pdf",
        filename: "menu.pdf",
      },
    };
    const { getByLabelText } = render(<Media ucm={ucm} />);
    expect(getByLabelText("Document: menu.pdf")).toBeInTheDocument();
  });
});
