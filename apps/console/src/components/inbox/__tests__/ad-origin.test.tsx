import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { InboxDetail } from "@/lib/backend/inbox";

import { ContactPanel } from "../contact-panel";
import { ThreadHeader } from "../thread-header";
import { NOW, detail } from "./fixtures";

/**
 * Spec 076 (R2.1–2.3): the conversation says which ad or post the person came
 * from — in the header, with a link, and in the contact panel. Without an
 * origin, nothing about ads is painted (constitution §V).
 */

function header(d: InboxDetail) {
  render(
    <LocaleProvider locale="es">
      <ThreadHeader
        detail={d}
        initials="AT"
        busy={false}
        panelOpen={false}
        onBack={vi.fn()}
        onUnread={vi.fn()}
        onResolve={vi.fn()}
        onReopen={vi.fn()}
        onTogglePanel={vi.fn()}
        onClearChat={vi.fn()}
        onDeleteChat={vi.fn()}
      />
    </LocaleProvider>,
  );
}

function panel(d: InboxDetail) {
  render(
    <LocaleProvider locale="es">
      <ContactPanel
        detail={d}
        initials="AT"
        suggested={[]}
        now={NOW}
        onClose={vi.fn()}
        onTags={vi.fn(async () => true)}
        onNote={vi.fn(async () => true)}
      />
    </LocaleProvider>,
  );
}

const AD = { kind: "ad" as const, headline: "Corte + barba", url: "https://fb.me/ad" };

describe("ad origin", () => {
  it("the header names the ad and links to it, in a new tab", () => {
    header(detail({ ad_origin: AD }));
    const link = screen.getByRole("link", { name: /Desde un anuncio: Corte \+ barba/ });
    expect(link).toHaveAttribute("href", "https://fb.me/ad");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
    expect(link.getAttribute("rel")).toContain("noreferrer");
  });

  it("without a headline it still says it came from an ad", () => {
    header(detail({ ad_origin: { kind: "ad", headline: null, url: null } }));
    expect(screen.getByText("Desde un anuncio")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Desde un anuncio/ })).toBeNull();
  });

  it("a post is called a post", () => {
    header(detail({ ad_origin: { kind: "post", headline: null, url: "https://fb.me/p" } }));
    expect(screen.getByRole("link", { name: /Desde una publicación/ })).toBeInTheDocument();
  });

  it("without an origin, nothing about ads", () => {
    header(detail({ ad_origin: null }));
    expect(screen.queryByText(/Desde un anuncio|Desde una publicación/)).toBeNull();
  });

  it("the contact panel says how the person came", () => {
    panel(detail({ ad_origin: AD }));
    expect(screen.getByText("Llegó por")).toBeInTheDocument();
    expect(screen.getByText("Un anuncio: Corte + barba")).toBeInTheDocument();
  });

  it("the contact panel has no such row without an origin", () => {
    panel(detail());
    expect(screen.queryByText("Llegó por")).toBeNull();
  });
});
