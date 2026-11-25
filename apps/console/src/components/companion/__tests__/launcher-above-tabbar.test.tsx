import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { CompanionLauncher } from "../companion-launcher";

/**
 * Spec 074, T009 (staging at 375 px, 2026-11-25): below the shell breakpoint
 * the tab bar is the only navigation, and the bubble — fixed bottom right —
 * sat on top of its last tab («Auditoría»). In the new frame the bubble rises
 * above the bar on the phone; elsewhere it stays where it was.
 */
vi.mock("next/navigation", () => ({ usePathname: () => "/clients/boreal" }));

const fetchMock = vi.fn();

beforeEach(() => {
  window.localStorage.clear();
  fetchMock.mockReset();
  fetchMock.mockResolvedValue(
    new Response(JSON.stringify({ companion_enabled: true }), {
      status: 200,
      headers: { "content-type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

async function anchorOf(aboveTabbar?: boolean): Promise<HTMLElement> {
  render(
    <LocaleProvider locale="es">
      <CompanionLauncher role="owner" userId="user_a_ab12cd34" aboveTabbar={aboveTabbar} />
    </LocaleProvider>,
  );
  const button = await waitFor(() => screen.getByRole("button", { name: /Companion/ }));
  const anchor = button.closest<HTMLElement>(".fixed");
  if (!anchor) throw new Error("the bubble has no fixed anchor");
  return anchor;
}

describe("CompanionLauncher — the phone's tab bar (spec 074, T009)", () => {
  it("with the tab bar, rises above it below the shell breakpoint, safe area included", async () => {
    const anchor = await anchorOf(true);
    expect(anchor.className).toContain("max-shell:bottom-[calc(5rem+env(safe-area-inset-bottom))]");
    expect(anchor.className).toContain("bottom-4");
  });

  it("without a tab bar (the old frame), stays at the bottom corner", async () => {
    const anchor = await anchorOf();
    expect(anchor.className).not.toContain("max-shell:");
  });
});
