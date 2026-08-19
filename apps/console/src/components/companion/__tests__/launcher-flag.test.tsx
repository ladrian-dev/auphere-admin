import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { CompanionLauncher } from "../companion-launcher";

/**
 * The per-partner flag of §10 of CONTRACT-V2.
 *
 * The rule the contract states and this file enforces: **an off bubble is
 * ABSENCE, not a disabled button with a tooltip.** A disabled button is an
 * advert for something you cannot have, and it generates a support
 * conversation about a feature the partner was never sold.
 *
 * It is deliberately a different question from "your role cannot use the
 * Companion", which CO-03 answers with a disabled bubble that explains
 * itself. Both cases have a test here so neither can quietly become the
 * other.
 */
vi.mock("next/navigation", () => ({ usePathname: () => "/clients/boreal" }));

const fetchMock = vi.fn();

beforeEach(() => {
  window.localStorage.clear();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function mount(role: "owner" | "analyst" = "owner") {
  render(
    <LocaleProvider locale="es">
      <CompanionLauncher role={role} userId="user_a_ab12cd34" />
    </LocaleProvider>,
  );
}

describe("CompanionLauncher — the partner flag (v2 §10)", () => {
  it("IDEAL: the bubble is mounted when the flag is on", async () => {
    fetchMock.mockResolvedValue(json({ companion_enabled: true }));
    mount();
    await waitFor(() => expect(screen.getByRole("button", { name: /Companion/ })).toBeInTheDocument());
  });

  it("EMPTY: the flag off means no bubble at all — not a disabled one", async () => {
    fetchMock.mockResolvedValue(json({ companion_enabled: false }));
    mount();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    // Not "disabled": absent. Nothing to hover, nothing to explain away.
    expect(screen.queryByRole("button", { name: /Companion/ })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain("Companion");
  });

  it("LOADING: nothing is mounted before the answer, so nothing flashes and vanishes", () => {
    // A pending promise: the flag is unknown.
    fetchMock.mockReturnValue(new Promise(() => {}));
    mount();
    expect(screen.queryByRole("button", { name: /Companion/ })).not.toBeInTheDocument();
  });

  it("ERROR: a failed lookup stays closed — we do not advertise what we cannot prove", async () => {
    fetchMock.mockResolvedValue(json({ detail: "boom" }, 500));
    mount();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /Companion/ })).not.toBeInTheDocument();
  });

  it("treats a missing field as off — the contract's own default is false", async () => {
    // What the API looks like before E ships the column.
    fetchMock.mockResolvedValue(json({ user_id: "u1", role: "owner" }));
    mount();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /Companion/ })).not.toBeInTheDocument();
  });

  it("PARTIAL: flag on but the role cannot use it — the bubble stays and explains itself", async () => {
    fetchMock.mockResolvedValue(json({ companion_enabled: true }));
    mount("analyst");
    // The other question, answered the other way (CO-03's decision,
    // intact): a builder-less analyst must not wonder where it went.
    await waitFor(() => expect(screen.getByRole("button", { name: /Tu rol no puede usar el Companion/ })).toBeDisabled());
  });

  it("asks the flag route and nothing else before it knows", async () => {
    fetchMock.mockResolvedValue(json({ companion_enabled: false }));
    mount();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const urls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(urls).toEqual(["/api/companion/enabled"]);
  });
});
