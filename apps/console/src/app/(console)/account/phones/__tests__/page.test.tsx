import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { UiCopyProvider } from "@nexus/ui";

import { LocaleProvider } from "@/i18n/client";
import { t } from "@/i18n/messages";
import type { ActionResult } from "@/lib/actions";
import type { LitePhone } from "@/lib/backend/lite";

const h = vi.hoisted(() => ({ refresh: vi.fn(), success: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: h.refresh, push: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { success: h.success, error: vi.fn() } }));

const { LitePhonesView } = await import("@/components/lite/lite-phones-view");

const NOW = "2026-10-19T12:00:00Z";
const phone = (o: Partial<LitePhone> = {}): LitePhone => ({
  id: "6f1c1b7e-2a2b-4c4d-8e8f-000000000001",
  display_name: "iPhone de Valeria",
  platform: "ios",
  app_version: "1.0.0",
  last_seen_at: "2026-10-19T10:00:00Z",
  enrolled_at: "2026-10-02T09:00:00Z",
  current: false,
  ...o,
});
const pixel = phone({ id: "6f1c1b7e-2a2b-4c4d-8e8f-000000000002", display_name: "Pixel 9", platform: "android" });

type Close = (raw: { id: string }) => Promise<ActionResult<null>>;

function view(phones: LitePhone[] | null, closePhone = vi.fn<Close>(async () => ({ ok: true, data: null }))) {
  render(
    <LocaleProvider locale="es">
      <UiCopyProvider copy={{ cancel: t("es", "ui.cancel"), retry: t("es", "ui.retry") }}>
        <LitePhonesView phones={phones} now={NOW} closePhone={closePhone} />
      </UiCopyProvider>
    </LocaleProvider>,
  );
  return closePhone;
}

async function close(name: string) {
  fireEvent.click(screen.getByRole("button", { name: `Cerrar la sesión de ${name}` }));
  const dialog = await screen.findByRole("dialog");
  expect(within(dialog).getByText(`¿Cerrar la sesión de ${name}?`)).toBeTruthy();
  await act(async () => {
    fireEvent.click(within(dialog).getByRole("button", { name: "Cerrar sesión" }));
  });
}

/** Spec 031 (R7.3, R7.5): «Tus teléfonos», in each of its states. */
describe("Tus teléfonos", () => {
  beforeEach(() => {
    h.refresh.mockClear();
    h.success.mockClear();
  });

  it("ideal: each phone with its platform, version, last use and when it signed in", () => {
    view([phone(), pixel]);
    const list = screen.getByRole("list", { name: "Teléfonos con la sesión abierta" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText("iPhone de Valeria")).toBeTruthy();
    expect(screen.getByText(/iPhone · versión 1\.0\.0 · Último uso/)).toBeTruthy();
    expect(screen.getByText(/Android · versión 1\.0\.0/)).toBeTruthy();
    expect(screen.getAllByText(/^Entró el /)).toHaveLength(2);
  });

  it("empty: says how to get a phone in, and is not an error", () => {
    view([]);
    expect(screen.getByRole("status").textContent).toContain("Todavía no has entrado desde un teléfono");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("error: a failed read is never an empty list, and offers a retry", () => {
    view(null);
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("No se pudieron cargar tus teléfonos");
    expect(screen.queryByText("Todavía no has entrado desde un teléfono")).toBeNull();
    fireEvent.click(within(alert).getByRole("button", { name: "Reintentar" }));
    expect(h.refresh).toHaveBeenCalled();
  });

  it("asks before signing out, and nothing happens on cancel", async () => {
    const closePhone = view([phone()]);
    fireEvent.click(screen.getByRole("button", { name: "Cerrar la sesión de iPhone de Valeria" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    expect(closePhone).not.toHaveBeenCalled();
    expect(screen.getByText("iPhone de Valeria")).toBeTruthy();
  });

  it("signs out the phone it was asked about, and only that one", async () => {
    const closePhone = view([phone(), pixel]);
    await close("Pixel 9");
    expect(closePhone).toHaveBeenCalledWith({ id: pixel.id });
    await waitFor(() => expect(h.success).toHaveBeenCalledWith("Sesión cerrada en Pixel 9"));
  });

  it("partial: a sign-out that fails puts the phone back and says why", async () => {
    view([phone(), pixel], vi.fn<Close>(async () => ({ ok: false, status: 503, message: "x" })));
    await close("Pixel 9");
    expect((await screen.findByRole("alert")).textContent).toContain("No se pudo cerrar la sesión de Pixel 9");
    expect(screen.getByText("Pixel 9")).toBeTruthy();
    expect(h.success).not.toHaveBeenCalled();
  });

  it("a long German-length name wraps inside its row instead of pushing the button out", () => {
    view([phone({ display_name: "Geschäftstelefon der Rezeption Hauptfiliale Nord" })]);
    const name = screen.getByText("Geschäftstelefon der Rezeption Hauptfiliale Nord");
    expect(name.className).toContain("truncate");
    expect(name.parentElement?.className).toContain("min-w-0");
  });
});
