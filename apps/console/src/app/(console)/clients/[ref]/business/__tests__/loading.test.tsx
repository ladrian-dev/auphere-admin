import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BUSINESS_GRID, BUSINESS_INDEX_LIST, BUSINESS_SECTIONS_COLUMN } from "@/components/business/sections/layout";
import { type MessageKey, t as translate } from "@/i18n/messages";

vi.mock("@/i18n/server", () => ({
  getT: async () => ({ locale: "es", t: (key: MessageKey, vars?: Record<string, string | number>) => translate("es", key, vars) }),
}));

const BusinessLoading = (await import("../loading")).default;

/**
 * T218 (puertas de UI, 2026-10-29) — Negocio carga con la forma de la página:
 * la misma rejilla que `BusinessSectionsView` (índice de 12,5 rem), el índice
 * con sus ocho secciones también en el móvil (una fila que se desplaza), y las
 * tarjetas con su radio. Nada salta cuando llegan los datos, y se anuncia.
 */
describe("Negocio · cargando", () => {
  it("tiene la forma de la página y se anuncia", async () => {
    const { container } = render(await BusinessLoading());
    const root = screen.getByRole("status", { name: "Cargando Negocio" });
    expect(root.className).toBe(BUSINESS_GRID);
    const index = container.querySelector('[data-slot="business-index-skeleton"]') as HTMLElement;
    expect(index.className).toContain(BUSINESS_INDEX_LIST);
    expect(index.className).not.toMatch(/(^|\s)hidden(\s|$)/);
    expect(index.children).toHaveLength(8);
    const column = container.querySelector('[data-slot="business-sections-skeleton"]') as HTMLElement;
    expect(column.className).toBe(BUSINESS_SECTIONS_COLUMN);
    for (const card of Array.from(column.children)) expect(card.className).toMatch(/rounded-lg/);
  });
});
