import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { AdsReport } from "@/lib/backend/ads";

import { AdsReportView } from "../ads-report";

/**
 * Spec 076 (R3): the ads report of a client — one row per ad, with
 * conversations, the agent's bookings and their amount; 7, 30 or 90 days;
 * empty explained; an error with «Reintentar».
 */

const REPORT: AdsReport = {
  days: 30,
  rows: [
    {
      ad_id: "A",
      ad_kind: "ad",
      ad_headline: "Corte + barba",
      ad_url: "https://fb.me/A",
      conversations: 41,
      bookings: 9,
      amounts: [{ currency: "CLP", amount_minor: 135000 }],
    },
    { ad_id: null, ad_kind: "post", ad_headline: null, ad_url: null, conversations: 2, bookings: 0, amounts: [] },
  ],
};

function view(initial: AdsReport | null, load = vi.fn(async () => ({ ok: true as const, data: REPORT }))) {
  render(
    <LocaleProvider locale="es">
      <AdsReportView refId="barberia" initial={initial} load={load} />
    </LocaleProvider>,
  );
  return load;
}

describe("AdsReportView", () => {
  it("one row per ad, with its numbers and a link", () => {
    view(REPORT);
    const table = screen.getByRole("table");
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(3);
    const link = within(rows[1]!).getByRole("link", { name: /Corte \+ barba/ });
    expect(link).toHaveAttribute("href", "https://fb.me/A");
    expect(link.getAttribute("rel")).toContain("noopener");
    expect(rows[1]!).toHaveTextContent("41");
    expect(rows[1]!).toHaveTextContent("9");
    expect(rows[1]!).toHaveTextContent("135.000");
    // Una publicación sin titular ni identificador se dice con palabras.
    expect(rows[2]!).toHaveTextContent("Publicación sin titular");
    expect(rows[2]!).toHaveTextContent("—");
  });

  it("says what each column measures", () => {
    view(REPORT);
    expect(screen.getByText(/conversaciones que empezaron desde el anuncio en el periodo/i)).toBeInTheDocument();
    expect(screen.getByText(/^Reservas: reservas que hizo el agente/)).toBeInTheDocument();
  });

  it("changes the period", async () => {
    const load = view(REPORT);
    await userEvent.click(screen.getByRole("tab", { name: "7 días" }));
    await waitFor(() => expect(load).toHaveBeenCalledWith({ ref: "barberia", days: 7 }));
    expect(screen.getByRole("tab", { name: "7 días" })).toHaveAttribute("aria-selected", "true");
  });

  it("empty: explains that it fills when someone writes from an ad", () => {
    view({ days: 30, rows: [] });
    expect(screen.getByText("Ninguna conversación ha llegado de un anuncio en estos días")).toBeInTheDocument();
    expect(screen.getByText(/se llena solo cuando alguien escribe desde un anuncio/i)).toBeInTheDocument();
  });

  it("error: says it and retries", async () => {
    const load = view(null, vi.fn(async () => ({ ok: true as const, data: { days: 30, rows: [] } })));
    expect(screen.getByText("No se pudo cargar el informe de anuncios")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    await waitFor(() => expect(load).toHaveBeenCalledWith({ ref: "barberia", days: 30 }));
  });
});
