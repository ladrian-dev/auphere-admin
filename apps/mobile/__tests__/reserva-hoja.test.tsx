import { fireEvent, render, screen } from "@testing-library/react-native";

import { t as translate, type T } from "@/i18n/t";

import { capacityConfig, marcos, peinado, res, servicesConfig, TODAY } from "../test/reservas-fixtures";

const { ReservaSheet } = require("@/features/reservas/sheet") as typeof import("@/features/reservas/sheet");

/**
 * Spec 044, Historia 2, Requisito 4: one reservation in its sheet — what, when,
 * with whom, where it came from — and only the actions the API allows.
 */
const t: T = (k, v) => translate("es", k, v);
const noop = () => undefined;

const pending = res({
  id: "p",
  start: 17 * 60,
  end: 17 * 60 + 45,
  date: "2026-10-23",
  state: "pending",
  service: peinado,
  pro: marcos,
  customer: { name: "Lucía Fernández", phone: "+56 9 6123 4567" },
  actions: ["confirm", "cancel"],
  // 043 §4 `events`: the API says what happened; the sheet says it in words.
  events: [
    { kind: "created", at: "2026-10-22T01:14:00Z", actor: null, data: { channel: "whatsapp", origin: "agent" } },
    { kind: "confirmation_requested", at: "2026-10-22T12:00:00Z", actor: null, data: {} },
  ],
});

describe("the sheet of a reservation (R4.1)", () => {
  it("in Servicios: service, length and price, with whom, when, the channel, the origin and the history", async () => {
    await render(<ReservaSheet r={pending} config={servicesConfig} today={TODAY} online onAct={noop} onCancel={noop} t={t} locale="es" />);
    expect(screen.getByText("Lucía Fernández")).toBeTruthy();
    expect(screen.getByText(/Corte y peinado · 45 min · \$18\.000/)).toBeTruthy();
    expect(screen.getByLabelText("Cuándo: Mañana · 17:00 – 17:45")).toBeTruthy();
    expect(screen.getByLabelText("Con: Marcos Soto")).toBeTruthy();
    expect(screen.getByLabelText("Canal: WhatsApp")).toBeTruthy();
    expect(screen.getByText("La reservó el agente por WhatsApp")).toBeTruthy();
    expect(screen.getByText(/Se le pidió confirmación por WhatsApp/)).toBeTruthy();
  });

  it("says the state once, and the history oldest first whatever order it comes in (first iOS pass)", async () => {
    const shuffled = { ...pending, events: [...pending.events].reverse() };
    await render(<ReservaSheet r={shuffled} config={servicesConfig} today={TODAY} online onAct={noop} onCancel={noop} t={t} locale="es" />);
    expect(screen.getAllByText("Sin confirmar", { includeHiddenElements: true })).toHaveLength(1);
    const lines = screen.getAllByText(/El agente la reservó por WhatsApp ·|Se le pidió confirmación por WhatsApp ·/).map((n) => String(n.props.children[0]));
    expect(lines).toEqual(["El agente la reservó por WhatsApp", "Se le pidió confirmación por WhatsApp"]);
  });

  it("in Aforo: the party and the table time", async () => {
    const r = res({ id: "c", start: 810, end: 900, partySize: 4, actions: ["arrived", "noshow"], lateMinutes: null });
    await render(<ReservaSheet r={r} config={capacityConfig} today={TODAY} online onAct={noop} onCancel={noop} t={t} locale="es" />);
    expect(screen.getByText("4 comensales")).toBeTruthy();
    expect(screen.getByLabelText("Tiempo máximo de mesa: 1 h 30 min")).toBeTruthy();
  });
});

describe("its actions (R4.2–R4.6)", () => {
  it("says a failed action inside the sheet — a notice would sit under it on iOS (gate review)", async () => {
    await render(<ReservaSheet r={pending} config={servicesConfig} today={TODAY} online error="La reserva cambió mientras tanto. Ya ves la última." onAct={noop} onCancel={noop} t={t} locale="es" />);
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText("La reserva cambió mientras tanto. Ya ves la última.")).toBeTruthy();
  });

  it("offers only what the API allows: confirm and cancel here, never «Llegó» in Servicios", async () => {
    await render(<ReservaSheet r={pending} config={servicesConfig} today={TODAY} online onAct={noop} onCancel={noop} t={t} locale="es" />);
    expect(screen.getByText("Marcar confirmada")).toBeTruthy();
    expect(screen.getByText("Cancelar la reserva")).toBeTruthy();
    expect(screen.queryByText("Llegó")).toBeNull();
    expect(screen.queryByText("No vino")).toBeNull();
  });

  it("confirming acts at once; cancelling goes through its confirmation", async () => {
    const onAct = jest.fn();
    const onCancel = jest.fn();
    await render(<ReservaSheet r={pending} config={servicesConfig} today={TODAY} online onAct={onAct} onCancel={onCancel} t={t} locale="es" />);
    await fireEvent.press(screen.getByText("Marcar confirmada"));
    expect(onAct).toHaveBeenCalledWith("confirm");
    await fireEvent.press(screen.getByText("Cancelar la reserva"));
    expect(onCancel).toHaveBeenCalled();
    expect(onAct).not.toHaveBeenCalledWith("cancel");
  });

  it("offline, no action at all", async () => {
    await render(<ReservaSheet r={pending} config={servicesConfig} today={TODAY} online={false} onAct={noop} onCancel={noop} t={t} locale="es" />);
    expect(screen.queryByText("Marcar confirmada")).toBeNull();
    expect(screen.getByText("Sin conexión: conéctate para hacer cambios.")).toBeTruthy();
  });
});

describe("the cancel confirmation (R4.3, clarification 2)", () => {
  const { cancelCopy } = require("@/features/reservas/sheet") as typeof import("@/features/reservas/sheet");

  it("says the customer gets a WhatsApp, or that they cannot be told", () => {
    expect(cancelCopy(pending, t)).toEqual({ title: "¿Cancelar la reserva de Lucía Fernández?", body: "Le avisamos por WhatsApp y el hueco queda libre." });
    expect(cancelCopy({ ...pending, customer: { name: "X", phone: null } }, t).body).toBe("No dejó teléfono: no se le puede avisar. El hueco queda libre.");
  });
});
