import { describe, expect, it, vi } from "vitest";

import { t } from "@/i18n/messages";

// `getT` reads the locale from cookies and headers; here it takes the account's
// one when given, so the test sees which language the page asked for.
vi.mock("@/i18n/server", () => ({
  getT: async (accountLocale?: string | null) => {
    const locale = accountLocale === "en" ? "en" : "es";
    return { locale, t: (key: Parameters<typeof t>[1]) => t(locale, key) };
  },
}));
const principal = vi.hoisted(() => ({ current: null as null | { locale: string } }));
vi.mock("@/lib/principal", () => ({
  resolvePrincipal: async () =>
    principal.current ? { kind: "ok", principal: principal.current } : { kind: "anonymous" },
}));

const { generateMetadata } = await import("../page");

const meta = (estado?: string) => generateMetadata({ searchParams: Promise.resolve(estado ? { estado } : {}) });

describe("«Pago recibido»: the tab title (spec 077, 7.9)", () => {
  it("says the payment was received when Stripe sends it back paid", async () => {
    expect((await meta()).title).toBe("Pago recibido");
  });

  it("does not say «Pago recibido» when the payment was cancelled", async () => {
    expect((await meta("cancelado")).title).toBe("No se completó el pago");
  });

  it("stays out of search engines either way", async () => {
    expect((await meta("cancelado")).robots).toEqual({ index: false, follow: false });
  });
});

describe("«Pago recibido»: its language", () => {
  it("is the signed-in account's, the same as the layout's <html lang>", async () => {
    principal.current = { locale: "en" };
    try {
      expect((await meta()).title).not.toBe("Pago recibido");
    } finally {
      principal.current = null;
    }
  });
});
