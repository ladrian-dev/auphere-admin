import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import type { ReservasTemplate, ReservasTemplates } from "@/lib/backend/reservas-templates";

import { ViewRef, a, renderView, resetMocks } from "../../__tests__/harness";
import type { ReservasData } from "../../context";
import { capacitySettings, service, servicesSettings, staff } from "../../model/__tests__/fixtures";

vi.mock("@/app/(console)/reservas/actions", async () => (await import("../../__tests__/harness")).a);
vi.mock("@/app/(console)/reservas/templates-actions", async () => (await import("../../__tests__/harness")).a);
vi.mock("next/navigation", async () => (await import("../../__tests__/harness")).navigation);
vi.mock("sonner", async () => (await import("../../__tests__/toasts")).sonner);
ViewRef.current = (await import("../../reservas-view")).ReservasView;

const load = a.reservasTemplatesAction;

function item(name: string, o: Partial<ReservasTemplate> = {}): ReservasTemplate {
  return { name, state: "approved", rejection: null, why_not_created: null, since: null, ...o };
}

const ALL_APPROVED: ReservasTemplates = {
  whatsapp: true,
  approved: 6,
  items: [
    item("reserva_confirmada"),
    item("reserva_pide_confirmacion"),
    item("reserva_recordatorio"),
    item("reserva_cambiada"),
    item("reserva_cancelada"),
    item("reserva_hueco_libre"),
  ],
};

const PARTIAL: ReservasTemplates = {
  whatsapp: true,
  approved: 2,
  items: [
    item("reserva_confirmada"),
    item("reserva_pide_confirmacion"),
    item("reserva_recordatorio", { state: "in_review", since: "2026-10-22T13:00:00Z" }),
    item("reserva_cambiada", { state: "rejected", rejection: "invalid_format" }),
    item("reserva_cancelada", { state: "paused" }),
    item("reserva_hueco_libre", { state: "not_created", why_not_created: "on_its_way" }),
  ],
};

function data(o: Partial<ReservasData> = {}): ReservasData {
  return {
    settings: servicesSettings(),
    staff: [staff()],
    services: [service()],
    bookings: null,
    occupancy: null,
    blocks: null,
    waitlist: null,
    offers: null,
    ...o,
  };
}

function open(o: Partial<ReservasData> = {}, locale: "es" | "en" = "es") {
  return renderView(data(o), { url: { tab: "settings" }, locale });
}

const section = (name: string | RegExp = "Plantillas de WhatsApp") => screen.getByRole("region", { name });
const row = (box: HTMLElement, name: string) => within(box).getByRole("listitem", { name });

beforeEach(() => {
  resetMocks();
  load.mockReset();
});

describe("Plantillas de WhatsApp de Reservas", () => {
  it("ideal: las seis aprobadas lo dicen una vez, con su nombre en Meta, y pasa axe", async () => {
    load.mockResolvedValue({ ok: true, data: ALL_APPROVED });
    open();
    const box = section();
    expect(await within(box).findByText("Las seis están aprobadas. Los avisos salen aunque la persona no te haya escrito.")).toBeInTheDocument();
    expect(within(box).getAllByRole("listitem")).toHaveLength(6);
    const confirm = row(box, "Reserva confirmada");
    expect(within(confirm).getByText("Aprobada")).toBeInTheDocument();
    expect(within(confirm).getByText("reserva_confirmada")).toBeInTheDocument();
    expect(await axeViolations(box)).toEqual([]);
  });

  it("parcial: cuántas van aprobadas y, en cada una que no, qué pasa y por qué", async () => {
    load.mockResolvedValue({ ok: true, data: PARTIAL });
    open();
    const box = section();
    expect(await within(box).findByText(/^2 de 6 aprobadas\./)).toBeInTheDocument();

    const review = row(box, "Recordatorio");
    expect(within(review).getByText("En revisión")).toBeInTheDocument();
    expect(within(review).getByText(/^En revisión desde: .+\. Meta suele revisarla en minutos/)).toBeInTheDocument();

    const rejected = row(box, "Reserva cambiada");
    expect(within(rejected).getByText("Rechazada")).toBeInTheDocument();
    expect(within(rejected).getByText("Meta dice que el formato no es válido.")).toBeInTheDocument();
    expect(within(rejected).getByText(/No la volvemos a pedir sola/)).toBeInTheDocument();

    expect(within(row(box, "Reserva cancelada")).getByText("En pausa")).toBeInTheDocument();
    const missing = row(box, "Hueco libre de la lista de espera");
    expect(within(missing).getByText("Sin crear")).toBeInTheDocument();
    expect(within(missing).getByText("La pediremos a Meta en unos minutos.")).toBeInTheDocument();
    expect(await axeViolations(box)).toEqual([]);
  });

  it("vacío: sin número de WhatsApp no puede haber ninguna, y lo dice", async () => {
    load.mockResolvedValue({
      ok: true,
      data: {
        whatsapp: false,
        approved: 0,
        items: ALL_APPROVED.items.map((i) => ({ ...i, state: "not_created", why_not_created: "no_whatsapp" })),
      },
    });
    open();
    const box = section();
    expect(await within(box).findByText(/no tiene un número de WhatsApp conectado/)).toBeInTheDocument();
    expect(within(box).getAllByText("Sin crear")).toHaveLength(6);
    expect(within(box).getAllByText("Falta un número de WhatsApp conectado.")).toHaveLength(6);
    expect(within(box).queryByText(/aprobadas/)).toBeNull();
  });

  it("cargando: un esqueleto por plantilla, anunciado", () => {
    load.mockReturnValue(new Promise(() => undefined));
    open();
    const status = within(section()).getByRole("status", { name: "Cargando plantillas" });
    expect(status.children).toHaveLength(6);
    expect(within(section()).queryByRole("list")).toBeNull();
  });

  it("error: lo dice y se puede reintentar con el teclado", async () => {
    load.mockResolvedValueOnce({ ok: false, status: 500, message: "" });
    load.mockResolvedValueOnce({ ok: true, data: ALL_APPROVED });
    open();
    const box = section();
    expect(await within(box).findByText("No pudimos cargar las plantillas.")).toBeInTheDocument();
    const retry = within(box).getByRole("button", { name: "Reintentar" });
    retry.focus();
    await userEvent.keyboard("{Enter}");
    expect(await within(box).findByText(/Las seis están aprobadas/)).toBeInTheDocument();
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("también está en los Ajustes de Aforo", async () => {
    load.mockResolvedValue({ ok: true, data: PARTIAL });
    open({ settings: capacitySettings(), staff: null, services: null });
    expect(await within(section()).findByText(/^2 de 6 aprobadas\./)).toBeInTheDocument();
  });

  it("en inglés", async () => {
    load.mockResolvedValue({ ok: true, data: PARTIAL });
    open({}, "en");
    const box = section("WhatsApp templates");
    expect(await within(box).findByText(/^2 of 6 approved\./)).toBeInTheDocument();
    expect(within(row(box, "Booking changed")).getByText("Meta says the format isn't valid.")).toBeInTheDocument();
  });
});
