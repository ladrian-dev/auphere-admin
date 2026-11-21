import { fireEvent, render, screen } from "@testing-library/react-native";

import type { Offer, WaitEntry } from "@/api/reservas";
import { t as translate, type T } from "@/i18n/t";

import { capacityConfig, servicesConfig, TODAY } from "../test/reservas-fixtures";

const { WaitlistView } = require("@/features/reservas/waitlist") as typeof import("@/features/reservas/waitlist");
const { WaitlistAddForm } = require("@/features/reservas/waitlist-add") as typeof import("@/features/reservas/waitlist-add");
const { ReservasSettings } = require("@/features/reservas/settings") as typeof import("@/features/reservas/settings");

/**
 * Spec 069, Requisitos 16 y 17: the waitlist as the web has it — the offers
 * running and «Parar», «Reservarle ahora», someone put on it by hand with a
 * phone — and the settings the web already changed (the agent's notice, the
 * reminders), with what only the web edits said as such.
 */
const t: T = (k, v) => translate("es", k, v);
const noop = () => undefined;
const NOW = Date.parse("2026-10-22T13:20:00-03:00");

const entry = (over: Partial<WaitEntry>): WaitEntry => ({
  id: "w",
  name: "Florencia Araya",
  phone: "+56 9 7788 1122",
  wants: { date: null, time: null, partySize: null, service: "Corte", pro: "Javiera Muñoz", text: null },
  state: "waiting",
  fits: null,
  offeredUntil: null,
  joinedBy: "agent",
  by: null,
  joinedAt: "2026-10-21T21:02:00-03:00",
  ...over,
});

const offer: Offer = {
  id: "o1",
  status: "running",
  createdAt: "2026-10-22T16:14:00Z",
  windowMin: 5,
  slot: { date: TODAY, start: 16 * 60, end: 16 * 60 + 30, service: "Corte", pro: "Javiera Muñoz", seats: null },
  candidates: [
    { name: "Florencia Araya", position: 1, status: "waiting", deadlineAt: new Date(NOW + 4 * 60_000).toISOString() },
    { name: "Cristóbal Reyes", position: 2, status: "queued", deadlineAt: null },
  ],
  cancelledBy: "Valentina Rojas",
};

describe("the offers running now (R16.2)", () => {
  it("say the slot, whose turn it is and how long they have, and «Parar» stops it", async () => {
    const onStopOffer = jest.fn();
    await render(<WaitlistView config={servicesConfig} items={[]} offers={[offer]} onStopOffer={onStopOffer} now={NOW} today={TODAY} online onOffer={noop} onRemove={noop} t={t} locale="es" />);
    expect(screen.getByText("Huecos ofrecidos")).toBeTruthy();
    expect(screen.getByText("Hoy · 16:00 · Corte · Javiera")).toBeTruthy();
    expect(screen.getByText("Avisando · 1 de 2")).toBeTruthy();
    expect(screen.getByText("Florencia Araya tiene 4 min para responder. Si no responde, se escribe a la siguiente persona.")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Parar el aviso del hueco de las 16:00" }));
    expect(onStopOffer).toHaveBeenCalledWith(expect.objectContaining({ id: "o1" }));
  });

  it("offline, nothing to stop", async () => {
    await render(<WaitlistView config={servicesConfig} items={[]} offers={[offer]} onStopOffer={noop} now={NOW} today={TODAY} online={false} onOffer={noop} onRemove={noop} t={t} locale="es" />);
    expect(screen.queryByText("Parar")).toBeNull();
  });
});

describe("the people on the list (R16.1, R16.3)", () => {
  it("«Reservarle ahora» and «Quitar» for each, «Apuntar a alguien» for a new one", async () => {
    const onBook = jest.fn();
    const onRemove = jest.fn();
    const onAdd = jest.fn();
    await render(<WaitlistView config={servicesConfig} items={[entry({})]} onBook={onBook} onAdd={onAdd} now={NOW} today={TODAY} online onOffer={noop} onRemove={onRemove} t={t} locale="es" />);
    await fireEvent.press(screen.getByRole("button", { name: "Reservarle ahora" }));
    expect(onBook).toHaveBeenCalledWith(expect.objectContaining({ id: "w" }));
    await fireEvent.press(screen.getByRole("button", { name: "Quitar" }));
    expect(onRemove).toHaveBeenCalledWith(expect.objectContaining({ id: "w" }));
    await fireEvent.press(screen.getByRole("button", { name: "Apuntar a alguien" }));
    expect(onAdd).toHaveBeenCalled();
  });

  it("putting someone on it by hand needs their phone, as booking does (064 R3.7)", async () => {
    const onSave = jest.fn();
    await render(<WaitlistAddForm config={servicesConfig} today={TODAY} saving={false} error={null} online onSave={onSave} t={t} locale="es" />);
    await fireEvent.changeText(screen.getByLabelText("Nombre y apellido"), "Ana Pérez");
    await fireEvent.press(screen.getByRole("button", { name: "Apuntar" }));
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText("Escribe el teléfono de quien se apunta.")).toBeTruthy();
    await fireEvent.changeText(screen.getByLabelText("Teléfono"), "+56 9 1111 2222");
    await fireEvent.press(screen.getByRole("button", { name: "Apuntar" }));
    // A week of open days ahead, by default: from Thursday 22, the 29th.
    expect(onSave).toHaveBeenCalledWith({
      partySize: 1,
      name: "Ana Pérez",
      phone: "+56 9 1111 2222",
      inPerson: false,
      serviceId: "s-corte",
      proId: null,
      date: null,
      time: null,
      until: "2026-10-29",
    });
  });

  it("in Aforo, how many, the day and the time if they say it", async () => {
    const onSave = jest.fn();
    await render(<WaitlistAddForm config={capacityConfig} today={TODAY} saving={false} error={null} online onSave={onSave} t={t} locale="es" />);
    await fireEvent.changeText(screen.getByLabelText("Nombre y apellido"), "Martín Herrera");
    await fireEvent.changeText(screen.getByLabelText("Teléfono"), "+56 9 4321 8765");
    await fireEvent.press(screen.getByLabelText("Uno más"));
    await fireEvent.press(screen.getByRole("radio", { name: "13:30" }));
    await fireEvent.press(screen.getByRole("button", { name: "Apuntar" }));
    expect(onSave).toHaveBeenCalledWith({ partySize: 3, name: "Martín Herrera", phone: "+56 9 4321 8765", inPerson: false, date: TODAY, time: 810 });
  });
});

describe("booking settings the web already changed (R17.1, R17.3)", () => {
  it("the agent's minimum notice, from the API's own steps", async () => {
    const onPatch = jest.fn();
    await render(<ReservasSettings config={{ ...servicesConfig, agent: { minNoticeMin: 60 } }} online saving={false} onPatch={onPatch} onUnblock={noop} onBlock={noop} t={t} locale="es" />);
    expect(screen.getByText("Citas que da el agente")).toBeTruthy();
    const notice = (label: string) => screen.getByRole("radio", { name: `Antelación mínima del agente: ${label}` });
    expect(notice("1 h").props.accessibilityState).toMatchObject({ checked: true });
    for (const label of ["Sin antelación", "15 min", "30 min", "2 h", "4 h", "24 h"]) expect(notice(label)).toBeTruthy();
    await fireEvent.press(notice("24 h"));
    expect(onPatch).toHaveBeenCalledWith({ agent: { minNoticeMin: 1440 } });
  });

  it("the reminders", async () => {
    const onPatch = jest.fn();
    await render(<ReservasSettings config={{ ...servicesConfig, reminders: true }} online saving={false} onPatch={onPatch} onUnblock={noop} onBlock={noop} t={t} locale="es" />);
    await fireEvent(screen.getByLabelText("Recordatorio por WhatsApp 24 horas antes"), "valueChange", false);
    expect(onPatch).toHaveBeenCalledWith({ reminders: false });
  });

  it("offline, both are read, not offered", async () => {
    await render(<ReservasSettings config={{ ...servicesConfig, agent: { minNoticeMin: 240 } }} online={false} saving={false} onPatch={noop} onUnblock={noop} onBlock={noop} t={t} locale="es" />);
    expect(screen.queryByRole("radio", { name: "Antelación mínima del agente: 1 h" })).toBeNull();
    expect(screen.getByText("4 h")).toBeTruthy();
  });

  it("what only the web edits is said once, and «Editar en la web» goes there — no dead button", async () => {
    const onWeb = jest.fn();
    await render(<ReservasSettings config={servicesConfig} online saving={false} onPatch={noop} onUnblock={noop} onBlock={noop} onWeb={onWeb} t={t} locale="es" />);
    expect(screen.getByText("Horario, equipo, servicios y plantillas vienen del perfil del negocio y se editan en la web.")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: /Editar en la web/ }));
    expect(onWeb).toHaveBeenCalled();
  });
});
