import { fireEvent, render, screen } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import type { WaitEntry } from "@/api/reservas";
import { t as translate, type T } from "@/i18n/t";

import { capacityConfig, servicesConfig, TODAY } from "../test/reservas-fixtures";

const { WaitlistView } = require("@/features/reservas/waitlist") as typeof import("@/features/reservas/waitlist");
const { ReservasSettings } = require("@/features/reservas/settings") as typeof import("@/features/reservas/settings");
const { BlockForm } = require("@/features/reservas/block") as typeof import("@/features/reservas/block");

/** Spec 044, Historia 9, Requisitos 7 y 8. */
const t: T = (k, v) => translate("es", k, v);
const noop = () => undefined;
const NOW = Date.parse("2026-10-22T13:20:00-03:00");

const entry = (over: Partial<WaitEntry>): WaitEntry => ({
  id: "w",
  name: "Josefa Castillo",
  phone: null,
  wants: { date: TODAY, time: 14 * 60, partySize: 2, service: null, pro: null, text: null },
  state: "waiting",
  fits: true,
  offeredUntil: null,
  joinedBy: "agent",
  by: null,
  joinedAt: "2026-10-21T21:02:00-03:00",
  ...over,
});

describe("the waitlist (R7)", () => {
  it("explains itself per mode and says what each person asks for, with who put them there", async () => {
    await render(<WaitlistView config={capacityConfig} items={[entry({})]} now={NOW} today={TODAY} online onOffer={noop} onRemove={noop} t={t} locale="es" />);
    expect(screen.getByText(/Cuando una hora se llena, el agente ofrece apuntarse/)).toBeTruthy();
    expect(screen.getByText("2 comensales · Hoy · 14:00")).toBeTruthy();
    expect(screen.getByText("Cabe")).toBeTruthy();
    expect(screen.getByText(/Se lo preguntó el agente/)).toBeTruthy();
  });

  it("an offer counts down its 15 minutes", async () => {
    const offered = entry({ id: "o", state: "offered", offeredUntil: new Date(NOW + 9 * 60_000).toISOString() });
    await render(<WaitlistView config={capacityConfig} items={[offered]} now={NOW} today={TODAY} online onOffer={noop} onRemove={noop} t={t} locale="es" />);
    expect(screen.getByText("Ofrecida · 9 min para responder")).toBeTruthy();
    expect(screen.queryByText("Ofrecer ahora")).toBeNull();
  });

  it("the name has the whole width, with where they stand below it (first iOS pass: a long status squeezed it)", async () => {
    const offered = entry({ id: "o", state: "offered", offeredUntil: new Date(NOW + 9 * 60_000).toISOString() });
    await render(<WaitlistView config={capacityConfig} items={[offered]} now={NOW} today={TODAY} online onOffer={noop} onRemove={noop} t={t} locale="es" />);
    const head = screen.getByTestId("wait-o-head");
    expect(StyleSheet.flatten(head.props.style).flexDirection ?? "column").toBe("column");
  });

  it("says «yesterday» in the phone's language (gate review: it was Spanish in English)", async () => {
    const en: T = (k, v) => translate("en", k, v);
    await render(<WaitlistView config={capacityConfig} items={[entry({})]} now={NOW} today={TODAY} online onOffer={noop} onRemove={noop} t={en} locale="en" />);
    expect(screen.getByText(/yesterday/)).toBeTruthy();
    expect(screen.queryByText(/ayer/)).toBeNull();
  });

  it("«Ofrecer ahora» only if they fit; «Quitar» always", async () => {
    const onOffer = jest.fn();
    await render(
      <WaitlistView config={capacityConfig} items={[entry({ id: "no", fits: false })]} now={NOW} today={TODAY} online onOffer={onOffer} onRemove={noop} t={t} locale="es" />,
    );
    expect(screen.queryByText("Ofrecer ahora")).toBeNull();
    expect(screen.getByText("Quitar")).toBeTruthy();
    expect(screen.getByText("No cabe")).toBeTruthy();
  });

  it("while an offer or a removal is on its way, both buttons wait — no second tap (gate review)", async () => {
    await render(<WaitlistView config={capacityConfig} items={[entry({})]} now={NOW} today={TODAY} online busy onOffer={noop} onRemove={noop} t={t} locale="es" />);
    expect(screen.getByRole("button", { name: "Quitar" }).props.accessibilityState).toMatchObject({ disabled: true });
  });

  it("offers when they fit", async () => {
    const onOffer = jest.fn();
    await render(<WaitlistView config={capacityConfig} items={[entry({})]} now={NOW} today={TODAY} online onOffer={onOffer} onRemove={noop} t={t} locale="es" />);
    await fireEvent.press(screen.getByText("Ofrecer ahora"));
    expect(onOffer).toHaveBeenCalledWith(expect.objectContaining({ id: "w" }));
  });

  it("empty says so", async () => {
    await render(<WaitlistView config={servicesConfig} items={[]} now={NOW} today={TODAY} online onOffer={noop} onRemove={noop} t={t} locale="es" />);
    expect(screen.getByText("Nadie en la lista todavía.")).toBeTruthy();
  });
});

describe("the settings of Reservas (R8)", () => {
  it("say the mode comes from the admin, the hours from the web, and in Aforo show its four numbers", async () => {
    await render(<ReservasSettings config={capacityConfig} online saving={false} onPatch={noop} onUnblock={noop} onBlock={noop} t={t} locale="es" />);
    expect(screen.getByText("Lo define Auphere desde el admin.")).toBeTruthy();
    expect(screen.getByText("Viene del perfil del negocio. Se edita en la web.")).toBeTruthy();
    expect(screen.getByText("Aforo máximo a la vez")).toBeTruthy();
    expect(screen.getByText("Guardadas para llegadas sin reserva")).toBeTruthy();
  });

  it("say the hours by runs of days, and Aforo's shifts under the days, not squeezed beside them (first iOS pass)", async () => {
    await render(<ReservasSettings config={capacityConfig} online saving={false} onPatch={noop} onUnblock={noop} onBlock={noop} t={t} locale="es" />);
    expect(screen.getByLabelText("Lunes a sábado. Comida: 13:00–15:00 · Cena: 20:00–22:00")).toBeTruthy();
    expect(screen.getByLabelText("Domingo. Comida: 13:00–15:00")).toBeTruthy();
  });

  it("in Servicios, the same runs with the hours beside them", async () => {
    await render(<ReservasSettings config={servicesConfig} online saving={false} onPatch={noop} onUnblock={noop} onBlock={noop} t={t} locale="es" />);
    expect(screen.getByLabelText("Lunes a viernes: 09:00–19:00")).toBeTruthy();
    expect(screen.getByLabelText("Sábado: 09:00–14:00")).toBeTruthy();
    expect(screen.getByLabelText("Domingo: Cerrado")).toBeTruthy();
  });

  it("while saving, the controls stay where they are, only disabled — the screen reader keeps its place (gate review)", async () => {
    await render(<ReservasSettings config={capacityConfig} online saving onPatch={noop} onUnblock={noop} onBlock={noop} t={t} locale="es" />);
    const plus = screen.getByLabelText("Aforo máximo a la vez: uno más");
    expect(plus.props.accessibilityState).toMatchObject({ disabled: true });
    expect(screen.getByLabelText("Lista de espera").props.disabled).toBe(true);
  });

  it("change what the API lets change, and read the rest without a dead control", async () => {
    const onPatch = jest.fn();
    await render(<ReservasSettings config={capacityConfig} online saving={false} onPatch={onPatch} onUnblock={noop} onBlock={noop} t={t} locale="es" />);
    await fireEvent.press(screen.getByLabelText("Aforo máximo a la vez: uno más"));
    expect(onPatch).toHaveBeenCalledWith({ capacity: { capacity: 66 } });
    // `confirmation.editable` is false in the fixture: read-only, saying where it changes.
    expect(screen.queryByLabelText("Pedir confirmación por WhatsApp")).toBeNull();
    expect(screen.getAllByText("Se cambia desde la web.").length).toBeGreaterThan(0);
  });

  it("in Servicios, the team with its calendar and the services, read only", async () => {
    await render(<ReservasSettings config={servicesConfig} online saving={false} onPatch={noop} onUnblock={noop} onBlock={noop} t={t} locale="es" />);
    expect(screen.getAllByText("Google Calendar conectado").length).toBe(2);
    expect(screen.getByLabelText("Corte: 30 min · $12.000")).toBeTruthy();
    expect(screen.queryByText("Bloqueos y eventos privados")).toBeNull();
  });

  it("in Aforo, the blocks with «Quitar» and «Bloquear horas»", async () => {
    const onBlock = jest.fn();
    const withBlock = { ...capacityConfig, capacity: { ...capacityConfig.capacity!, blocks: [{ id: "b1", date: "2026-10-24", from: 1200, until: 1320, shift: "Cena", reason: "Evento privado" }] } };
    await render(<ReservasSettings config={withBlock} online saving={false} onPatch={noop} onUnblock={noop} onBlock={onBlock} t={t} locale="es" />);
    expect(screen.getByText(/Evento privado/)).toBeTruthy();
    await fireEvent.press(screen.getByText("Bloquear horas"));
    expect(onBlock).toHaveBeenCalled();
  });
});

describe("blocking hours (R8.7)", () => {
  it("needs a reason, and keeps what is already booked", async () => {
    const onSave = jest.fn();
    await render(<BlockForm config={capacityConfig} today={TODAY} saving={false} error={null} online onSave={onSave} t={t} locale="es" />);
    expect(screen.getByText("El agente no acepta reservas en esas horas. Las que ya hay se mantienen.")).toBeTruthy();
    await fireEvent.press(screen.getByText("Bloquear"));
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText("Escribe el motivo.")).toBeTruthy();
    await fireEvent.changeText(screen.getByLabelText("Motivo"), "Evento privado");
    await fireEvent.press(screen.getByText("Bloquear"));
    // The lunch shift's arrivals, 13:00 to 15:00 included (043 §6).
    expect(onSave).toHaveBeenCalledWith({ date: TODAY, from: 780, until: 900, reason: "Evento privado" });
  });
});
