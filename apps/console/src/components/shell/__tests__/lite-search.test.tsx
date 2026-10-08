import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

const nav = vi.hoisted(() => ({ pathname: "/", push: vi.fn() }));
vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useRouter: () => ({ push: nav.push, replace: vi.fn(), refresh: vi.fn() }),
}));

const { LiteSearch } = await import("../lite-search");

function view(modules: ("panel" | "inbox" | "usage")[] = ["panel", "inbox", "usage"]) {
  return render(
    <LocaleProvider locale="es">
      <LiteSearch modules={modules} />
    </LocaleProvider>,
  );
}

/** Spec 030 (US12, R7.4, T088): searching from any screen of the client console. */
describe("LiteSearch", () => {
  it("⌘K / Ctrl+K focuses it and Enter opens the Inbox filtered", async () => {
    nav.pathname = "/";
    view();
    const box = screen.getByRole("searchbox", { name: "Buscar en la bandeja" });
    await userEvent.keyboard("{Meta>}k{/Meta}");
    expect(box).toHaveFocus();
    box.blur();
    await userEvent.keyboard("{Control>}k{/Control}");
    expect(box).toHaveFocus();
    await userEvent.type(box, "Ana Torres{Enter}");
    expect(nav.push).toHaveBeenCalledWith("/inbox?q=Ana%20Torres");
  });

  it("on the Inbox it steps aside and the shortcut focuses the list's own search", async () => {
    nav.pathname = "/inbox";
    view();
    render(<input id="inbox-search" aria-label="lista" />);
    expect(screen.queryByRole("searchbox", { name: "Buscar en la bandeja" })).toBeNull();
    await userEvent.keyboard("{Meta>}k{/Meta}");
    expect(screen.getByRole("textbox", { name: "lista" })).toHaveFocus();
  });

  it("without the Inbox module there is no search and no shortcut", async () => {
    nav.pathname = "/";
    view(["panel", "usage"]);
    expect(screen.queryByRole("search")).toBeNull();
    const before = document.activeElement;
    await userEvent.keyboard("{Meta>}k{/Meta}");
    expect(document.activeElement).toBe(before);
  });
});
