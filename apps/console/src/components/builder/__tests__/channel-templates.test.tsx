import { render, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({ usePathname: () => "/", useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/channels/actions", () => ({
  listTemplatesAction: vi.fn(async () => ({ ok: true, data: { items: [], approved: 0, rejected: 0, pending: 0 } })),
}));

const { ChannelTemplates } = await import("../channel-templates");

/**
 * QA de staging del 2026-11-08: la tabla de plantillas es más ancha que su hueco y la
 * tarjeta, hija de una rejilla sin `min-w-0`, crecía con ella y daba scroll horizontal a toda
 * la página del canal. jsdom no mide anchos: lo que se fija es que la tarjeta pueda
 * encogerse, en carga y cargada, para que la tabla se desplace dentro de su propia caja.
 */
describe("la tarjeta de plantillas del canal", () => {
  it("se encoge con su hueco, cargando y cargada", async () => {
    const { container } = render(
      <LocaleProvider locale="es">
        <ChannelTemplates refId="jemma-s-hair" manage />
      </LocaleProvider>,
    );
    const loading = container.querySelector('[aria-busy="true"]');
    expect(loading?.className).toContain("min-w-0");
    await waitFor(() => expect(container.querySelector('[data-slot="channel-templates"]')).not.toBeNull());
    expect(container.querySelector('[data-slot="channel-templates"]')?.className).toContain("min-w-0");
  });
});
