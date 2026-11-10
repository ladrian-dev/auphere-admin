import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { Locations } from "@/lib/backend/business-sections";

vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/business/actions", () => ({
  createLocationAction: vi.fn(),
  updateLocationAction: vi.fn(),
  archiveLocationAction: vi.fn(),
}));

const { LocationsSection } = await import("../locations-section");

/**
 * Spec 056 (requisito 12.1): archivar una sede desde la ficha pide confirmación,
 * como archivar en Reservas. Restaurar no la pide: se deshace solo.
 */
const NORTE = { id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", name: "Cultor Norte", address: "Calle Mayor 1", phone_e164: null, own_hours: false, label: null, archived: false };
const LOCATIONS: Locations = { allowed: ["edit"], revision: 4, state: "complete", items: [NORTE], created_id: null };

function section(archive = vi.fn(async () => ({ ok: true as const, data: LOCATIONS }))) {
  render(
    <LocaleProvider locale="es">
      <LocationsSection refId="cultor" locations={LOCATIONS} canWrite actions={{ create: vi.fn(), update: vi.fn(), archive }} />
    </LocaleProvider>,
  );
  return archive;
}

describe("LocationsSection", () => {
  it("archiving asks first and says what it means", async () => {
    const user = userEvent.setup();
    const archive = section();
    await user.click(screen.getByRole("button", { name: "Archivar Cultor Norte" }));
    const ask = await screen.findByRole("dialog", { name: "¿Archivar «Cultor Norte»?" });
    expect(within(ask).getByText(/Puedes restaurarla después/)).toBeVisible();
    expect(archive).not.toHaveBeenCalled();
    await user.click(within(ask).getByRole("button", { name: "Archivar" }));
    await waitFor(() => expect(archive).toHaveBeenCalledWith({ ref: "cultor", revision: 4, id: NORTE.id, restore: false }));
  });

  it("cancelling keeps it", async () => {
    const user = userEvent.setup();
    const archive = section();
    await user.click(screen.getByRole("button", { name: "Archivar Cultor Norte" }));
    await user.click(within(await screen.findByRole("dialog", { name: "¿Archivar «Cultor Norte»?" })).getByRole("button", { name: "Cancelar" }));
    expect(archive).not.toHaveBeenCalled();
  });
});
