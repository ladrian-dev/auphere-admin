import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react-native";
import { Alert } from "react-native";

import { ApiError } from "@/api/errors";
import { keys } from "@/api/query";
import { checkLocation, locationBody } from "@/features/business/locations-list";
import { checkService, serviceBody, type ServiceForm } from "@/features/business/services-list";
import { checkSpecial, newSpecial } from "@/features/business/special-dates";
import { t as translate, type T } from "@/i18n/t";
import {
  changeLine,
  checkShifts,
  conflictOf,
  layoutFor,
  normalizeTime,
  parseAmount,
  priceText,
  provenanceText,
  validTime,
  weekOf,
  writeErrorText,
} from "@/lib/business-model";
import { clearDrafts, peekDraft, useDraft } from "@/lib/drafts";

import { business, CHANGE, LOCATION, Providers, SERVICE, SPECIAL, testClient } from "../test/fabrica-fixtures";

/**
 * Spec 047, T169 (requirements 9, 10, 11, 13, 50.1, 50.4, 50.5, 50.9): Negocio
 * on the phone — the hours, the special dates, the services and the
 * locations; the revision on every write and the conflict when someone saved
 * first; «Deshacer»; and nothing saved or queued without a connection, with
 * what was typed kept.
 */
const t: T = (k, v) => translate("es", k, v);
// Whole screens with a real query cache: a loaded machine running the suite in parallel needs more than 5 s.
jest.setTimeout(15_000);

const mockEndpoints = {
  business: jest.fn(),
  me: jest.fn(),
  putHours: jest.fn(),
  locationHours: jest.fn(),
  putLocationHours: jest.fn(),
  addSpecialDate: jest.fn(),
  editSpecialDate: jest.fn(),
  archiveSpecialDate: jest.fn(),
  addService: jest.fn(),
  editService: jest.fn(),
  archiveService: jest.fn(),
  addLocation: jest.fn(),
  editLocation: jest.fn(),
  archiveLocation: jest.fn(),
  restoreLocation: jest.fn(),
  undoChange: jest.fn(),
};
jest.mock("@/api/endpoints", () => ({ endpoints: new Proxy({}, { get: (_t, k: string) => (mockEndpoints as Record<string, unknown>)[k] }) }));
jest.mock("@/api/reservas", () => ({ demo: null }));
let mockOnline = true;
jest.mock("@/ui/online", () => ({ useOnline: () => mockOnline }));
const mockPush = jest.fn();
jest.mock("expo-router", () => ({ Stack: { Screen: () => null }, router: { push: (...a: unknown[]) => mockPush(...a), back: jest.fn() } }));

const me = { user: { name: "Valeria", email: "v@flor.test" }, client: { name: "Flor y Encanto", modules: ["business"] }, nav: ["panel", "business"], agents: [], channels: [], balance_contact: { kind: "partner", name: "Amacrux" }, business: { timezone: "America/Santiago", hours: null, hours_label: null } };

beforeEach(() => {
  // Drafts live for the whole process, as in the app: each test starts from none.
  clearDrafts();
  mockOnline = true;
  mockPush.mockReset();
  for (const f of Object.values(mockEndpoints)) f.mockReset();
  mockEndpoints.business.mockResolvedValue(business());
  mockEndpoints.me.mockResolvedValue(me);
});

async function open(route: string) {
  const Screen = require(`@/app/negocio/${route}`).default as () => React.JSX.Element;
  const client = testClient();
  client.setQueryData(keys.business, business());
  client.setQueryData(keys.me, me);
  const view = await render(
    <Providers client={client}>
      <Screen />
    </Providers>,
  );
  return { client, view };
}

describe("the rules said before sending (the API's own)", () => {
  it("times as a thumb types them", () => {
    expect(normalizeTime("9")).toBe("09:00");
    expect(normalizeTime("930")).toBe("09:30");
    expect(normalizeTime("9.3")).toBe("09:30");
    expect(normalizeTime("17h")).toBe("17:00");
    expect(validTime("24:00")).toBe(false);
    expect(validTime("24:00", true)).toBe(true);
    expect(validTime("25:00", true)).toBe(false);
  });

  it("overlapping shifts and a wrong time are found; a night shift past midnight is not an overlap", () => {
    expect(checkShifts("mon", [{ open: "09:00", close: "14:00" }, { open: "13:00", close: "18:00" }])).toMatchObject({ code: "overlap", shift: 1 });
    expect(checkShifts("tue", [{ open: "9:00", close: "14:00" }])).toMatchObject({ code: "invalid_time", shift: 0 });
    expect(checkShifts("fri", [{ open: "20:00", close: "02:00" }])).toBeNull();
  });

  it("«Por bloques» stays only while Monday to Friday match: nothing is lost (10.6)", () => {
    const week = weekOf(business().hours);
    expect(layoutFor(week, "blocks")).toBe("blocks");
    expect(layoutFor({ ...week, wed: [] }, "blocks")).toBe("daily");
    expect(layoutFor(week, "daily")).toBe("daily");
  });

  it("amounts in the business's currency: CLP has no decimals, EUR has two", () => {
    expect(parseAmount("15.000", 0)).toBe(15000);
    expect(parseAmount("15000", 0)).toBe(15000);
    expect(parseAmount("12,50", 2)).toBe(1250);
    expect(parseAmount("12.5", 2)).toBe(1250);
    expect(parseAmount("12,5055", 2)).toBeNull();
    expect(parseAmount("doce", 2)).toBeNull();
    expect(priceText({ kind: "amount", amount_minor: 15000 }, "CLP", 0, "es", t)).toMatch(/15\.000/);
    expect(priceText({ kind: "none" }, "CLP", 0, "es", t)).toBe("Sin precio");
  });

  it("services, special dates and locations say what the API would refuse", () => {
    const base: ServiceForm = { id: null, name: "", description: "", bookable: true, duration: "30", priceKind: "none", amount: "" };
    expect(checkService(base, 0)).toBe("name_required");
    expect(checkService({ ...base, name: "Tinte", duration: "33" }, 0)).toBe("duration_invalid");
    expect(checkService({ ...base, name: "Tinte", priceKind: "amount" }, 0)).toBe("price_amount_required");
    // Not booked: no duration goes, or the API answers `duration_not_allowed`.
    expect(serviceBody({ ...base, name: "Consulta", bookable: false, duration: "30" }, 0).duration_min).toBeNull();
    expect(checkSpecial({ ...newSpecial("2026-12-24"), to: "2026-12-23" })).toBe("date_range");
    expect(checkSpecial({ ...newSpecial("2026-12-24"), closed: false })).toBe("no_shifts");
    expect(checkLocation({ id: null, name: "Centro", address: "", phone: "600 123" })).toBe("phone_invalid");
    expect(locationBody({ id: null, name: " Centro ", address: "", phone: "+56 9 5555 0101" })).toEqual({ name: "Centro", address: null, phone_e164: "+56955550101" });
  });

  it("where a datum came from and the last change, in words (13.1)", () => {
    expect(provenanceText({ source: "person", by: { kind: "client_user", name: "Marta" }, origin: "app" }, t)).toBe("Editado por Marta desde la app");
    expect(provenanceText({ source: "web", review: "pending" }, t)).toBe("Leído de la web · revísalo");
    const line = changeLine(business().history[0]!, t, "es", new Date("2026-10-28T12:00:00Z"));
    expect(line).toBe("Horarios · Marta desde la app · hace 5 minutos");
  });

  it("a refusal in the console's words; a conflict carries the section as it is now", () => {
    expect(writeErrorText(new ApiError(422, "overlap", { day: "tue" }), t)).toBe("Dos turnos se pisan (Martes).");
    expect(writeErrorText(new ApiError(422, "name_required"), t, "locations")).toBe("Escribe el nombre de la sede.");
    expect(writeErrorText(new ApiError(0, "offline"), t)).toMatch(/^Sin conexión: no se guarda nada/);
    expect(conflictOf(new ApiError(412, "revision_conflict", { current: { revision: 9 } }))).toEqual({ current: { revision: 9 } });
    expect(conflictOf(new ApiError(409, "already_undone"))).toBeNull();
  });
});

describe("Negocio (T169, 50.1)", () => {
  it("three ways in, each saying what it holds and where it came from, and the last change with «Deshacer»", async () => {
    mockEndpoints.undoChange.mockResolvedValue({ section: "hours", revision: 5, change_id: null });
    await open("index");
    expect(screen.getByText("De lunes a viernes de 9:00 a 14:00 y de 17:00 a 20:00, los sábados de 10:00 a 14:00\n1 fecha especial\nEditado por Marta desde la app")).toBeTruthy();
    expect(screen.getByLabelText(/^Servicios\. 1 servicio\. Leído de la web · revísalo/)).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: /^Sedes/ }));
    expect(mockPush).toHaveBeenCalledWith("/negocio/sedes");
    await fireEvent.press(screen.getByRole("button", { name: /^Deshacer el último cambio de Horarios/ }));
    expect(mockEndpoints.undoChange).toHaveBeenCalledWith(CHANGE, expect.any(String));
    expect(await screen.findByText("Cambio deshecho. Los agentes ya usan lo anterior.")).toBeTruthy();
  });
});

describe("Negocio › Horario (10, 13, 50.4, 50.5)", () => {
  it("«Así lo dirá el agente» first; a change shows the bar; saving sends the week, the revision and a key", async () => {
    const saved = { ...business().hours, revision: 5, label: "De lunes a viernes de 9:00 a 15:00" };
    mockEndpoints.putHours.mockResolvedValue(saved);
    await open("horario");
    expect(screen.getByText(business().hours.label!)).toBeTruthy();
    // From here on, the API has the new week.
    mockEndpoints.business.mockResolvedValue(business({ hours: saved }));
    expect(screen.queryByRole("button", { name: "Guardar horario" })).toBeNull();
    await fireEvent.changeText(screen.getAllByLabelText("Cierra (turno 1)")[0]!, "15:00");
    expect(screen.getByText("Guarda para ver cómo lo dirá el agente.")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Guardar horario" }));
    expect(mockEndpoints.putHours).toHaveBeenCalledWith(expect.objectContaining({ mon: [{ open: "09:00", close: "15:00" }, { open: "17:00", close: "20:00" }], sun: [] }), "daily", 4, expect.any(String));
    expect(await screen.findByText("De lunes a viernes de 9:00 a 15:00")).toBeTruthy();
    expect(screen.getByText("Guardado. Los agentes lo usan desde el siguiente mensaje.")).toBeTruthy();
    // The notice offers «Deshacer» of this very change.
    expect(screen.getAllByRole("button", { name: "Deshacer" }).length).toBeGreaterThan(0);
  });

  it("with locations, «Horario de» picks whose week: a location uses the business's until it has its own, saved with the Sedes revision (9, 10)", async () => {
    const inherited = { ...business().hours, revision: 1, location_id: LOCATION, inherits: true };
    mockEndpoints.locationHours.mockResolvedValue(inherited);
    mockEndpoints.putLocationHours.mockResolvedValue({ ...inherited, revision: 2, inherits: false, label: "Los sábados de 10:00 a 14:00" });
    await open("horario");
    await fireEvent.press(screen.getByRole("radio", { name: "Providencia" }));
    const inherit = await screen.findByLabelText("Usar el horario del negocio");
    expect(mockEndpoints.locationHours).toHaveBeenCalledWith(LOCATION);
    expect(inherit.props.value).toBe(true);
    // While it uses the business's week there is no week of its own to edit.
    expect(screen.queryAllByLabelText("Cierra (turno 1)")).toHaveLength(0);
    await fireEvent(inherit, "valueChange", false);
    await fireEvent.changeText(screen.getAllByLabelText("Cierra (turno 1)")[0]!, "15:00");
    await fireEvent.press(screen.getByRole("button", { name: "Guardar horario" }));
    await waitFor(() => expect(mockEndpoints.putLocationHours).toHaveBeenCalled());
    const [id, week, revision, key] = mockEndpoints.putLocationHours.mock.calls[0]!;
    expect([id, revision]).toEqual([LOCATION, 1]);
    expect(week).toMatchObject({ layout: "daily", days: expect.objectContaining({ mon: [{ open: "09:00", close: "15:00" }, { open: "17:00", close: "20:00" }] }) });
    expect(key).toEqual(expect.any(String));
    // The business's own week is not touched.
    expect(mockEndpoints.putHours).not.toHaveBeenCalled();
  });

  it("a day closes with its switch, and opens again from the day before", async () => {
    await open("horario");
    await fireEvent(screen.getByLabelText("Abierto el sábado"), "valueChange", false);
    expect(screen.queryByTestId("shifts-sat")).toBeNull();
    await fireEvent(screen.getByLabelText("Abierto el domingo"), "valueChange", true);
    expect(screen.getByTestId("shifts-sun")).toBeTruthy();
  });

  it("a wrong time is said in words before anything is sent", async () => {
    await open("horario");
    await fireEvent.changeText(screen.getAllByLabelText("Abre (turno 2)")[0]!, "13:00");
    await fireEvent.press(screen.getByRole("button", { name: "Guardar horario" }));
    expect(mockEndpoints.putHours).not.toHaveBeenCalled();
    expect(screen.getByText("Dos turnos se pisan (Lunes).")).toBeTruthy();
  });

  it("offline: nothing is sent or queued, the bar says why, and what was typed is there when the screen opens again", async () => {
    mockOnline = false;
    await open("horario");
    await fireEvent.changeText(screen.getAllByLabelText("Cierra (turno 1)")[0]!, "15:30");
    expect(screen.getByText("Sin conexión: no se guarda nada. Lo que escribiste sigue aquí hasta que vuelva la conexión.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Guardar horario" }).props.accessibilityState).toMatchObject({ disabled: true });
    await fireEvent.press(screen.getByRole("button", { name: "Guardar horario" }));
    expect(mockEndpoints.putHours).not.toHaveBeenCalled();
    expect(peekDraft("negocio.hours")).toBeTruthy();
  });

  it("…and the screen opened again finds what was typed", async () => {
    const first = await open("horario");
    await fireEvent.changeText(screen.getAllByLabelText("Cierra (turno 1)")[0]!, "15:30");
    await act(async () => first.view.unmount());
    await open("horario");
    expect(screen.getAllByLabelText("Cierra (turno 1)")[0]!.props.value).toBe("15:30");
    expect(screen.getByRole("button", { name: "Guardar horario" })).toBeTruthy();
  });

  it("someone saved first (412): what was typed stays, and the person chooses — «Guardar lo mío» goes with the new revision (13.4)", async () => {
    mockEndpoints.putHours.mockRejectedValueOnce(new ApiError(412, "revision_conflict", { current: { ...business().hours, revision: 6 }, changes: [] }));
    await open("horario");
    await fireEvent.changeText(screen.getAllByLabelText("Cierra (turno 1)")[0]!, "15:00");
    await fireEvent.press(screen.getByRole("button", { name: "Guardar horario" }));
    expect(await screen.findByText("Alguien cambió esto mientras lo editabas. Lo que escribiste sigue aquí: elige qué se queda.")).toBeTruthy();
    expect(screen.getAllByLabelText("Cierra (turno 1)")[0]!.props.value).toBe("15:00");
    mockEndpoints.putHours.mockResolvedValue({ ...business().hours, revision: 7 });
    await fireEvent.press(screen.getByRole("button", { name: "Guardar lo mío" }));
    expect(mockEndpoints.putHours).toHaveBeenLastCalledWith(expect.anything(), "daily", 6, expect.any(String));
  });

  it("«Ver lo nuevo» drops what was typed and shows what is there", async () => {
    mockEndpoints.putHours.mockRejectedValueOnce(new ApiError(412, "revision_conflict", { current: { ...business().hours, revision: 6 }, changes: [] }));
    await open("horario");
    await fireEvent.changeText(screen.getAllByLabelText("Cierra (turno 1)")[0]!, "15:00");
    await fireEvent.press(screen.getByRole("button", { name: "Guardar horario" }));
    await fireEvent.press(await screen.findByRole("button", { name: "Ver lo nuevo" }));
    expect(screen.getAllByLabelText("Cierra (turno 1)")[0]!.props.value).toBe("14:00");
    expect(screen.queryByTestId("conflict")).toBeNull();
  });

  it("a special date: closed all day, saved with its section's revision; removing one asks first", async () => {
    mockEndpoints.addSpecialDate.mockResolvedValue({ ...business().special_dates, revision: 3 });
    await open("horario");
    expect(screen.getByLabelText(/^Navidad\. 25 dic · Cerrado/)).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Añadir fecha especial" }));
    await fireEvent.changeText(screen.getByLabelText("Nombre (opcional)"), "Año Nuevo");
    await fireEvent.press(screen.getByRole("button", { name: "Guardar fecha" }));
    expect(mockEndpoints.addSpecialDate).toHaveBeenCalledWith(expect.objectContaining({ name: "Año Nuevo", closed: true, shifts: [] }), 2, expect.any(String));
    const alert = jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
    mockEndpoints.archiveSpecialDate.mockResolvedValue({ ...business().special_dates, revision: 4, items: [] });
    await fireEvent.press(screen.getByRole("button", { name: "Quitar Navidad" }));
    expect(alert).toHaveBeenCalledWith("¿Quitar Navidad?", expect.any(String), expect.any(Array));
    const buttons = alert.mock.calls[0]![2] as { text: string; onPress?: () => void }[];
    await act(async () => buttons.find((b) => b.text === "Quitar Navidad")!.onPress!());
    expect(mockEndpoints.archiveSpecialDate).toHaveBeenCalledWith(SPECIAL, 2, expect.any(String));
    alert.mockRestore();
  });
});

describe("Negocio › Horario › changing a special date (10.3)", () => {
  it("opens its form at the top, with what it had; open that day, it gets a shift and saves with PATCH", async () => {
    mockEndpoints.editSpecialDate.mockResolvedValue({ ...business().special_dates, revision: 3 });
    await open("horario");
    await fireEvent.press(screen.getByRole("button", { name: "Cambiar Navidad" }));
    expect(screen.getByLabelText("Nombre (opcional)").props.value).toBe("Navidad");
    expect(screen.queryByRole("button", { name: "Añadir fecha especial" })).toBeNull();
    await fireEvent(screen.getByLabelText("Cerrado todo el día"), "valueChange", false);
    await fireEvent.press(screen.getByRole("button", { name: "Guardar fecha" }));
    expect(mockEndpoints.editSpecialDate).toHaveBeenCalledWith(
      SPECIAL,
      { name: "Navidad", from: "2026-12-25", to: "2026-12-25", closed: false, shifts: [{ open: "10:00", close: "14:00" }], location_id: null },
      2,
      expect.any(String),
    );
  });

  it("the dates are chosen on a calendar whose days are buttons with their date", async () => {
    await open("horario");
    await fireEvent.press(screen.getByRole("button", { name: "Añadir fecha especial" }));
    await fireEvent.press(screen.getByRole("button", { name: /^Hasta: / }));
    expect(screen.getByTestId("date-calendar")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Mes siguiente" }));
    const days = screen.getAllByRole("button").filter((b) => /^\S+, \d+ de \S+ de \d{4}$/u.test(b.props.accessibilityLabel ?? ""));
    expect(days.length).toBeGreaterThanOrEqual(28);
  });
});

describe("Negocio › Servicios (11, 50.1)", () => {
  it("each with its price, duration and who offers it; «Editar» changes the price — never the name, which is the partner's", async () => {
    mockEndpoints.editService.mockResolvedValue(business().services);
    await open("servicios");
    expect(screen.getByLabelText(/^Corte de pelo\. \$15\.000\. 30 min · Se reserva\. Lavado incluido\.\. Lo usan: Recepción$/)).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Editar Corte de pelo" }));
    expect(screen.queryByLabelText("Nombre")).toBeNull();
    await fireEvent.changeText(screen.getByLabelText("Importe en CLP"), "18.000");
    await fireEvent.press(screen.getByRole("button", { name: "Guardar servicio" }));
    expect(mockEndpoints.editService).toHaveBeenCalledWith(
      SERVICE,
      { description: "Lavado incluido.", bookable: true, duration_min: 30, price: { kind: "amount", amount_minor: 18000 } },
      7,
      expect.any(String),
    );
    expect(await screen.findByText("Servicio guardado. El agente lo usa desde el siguiente mensaje.")).toBeTruthy();
  });

  it("a new one needs a name; who offers it is not offered as a control (50.3)", async () => {
    await open("servicios");
    await fireEvent.press(screen.getByRole("button", { name: "Añadir servicio" }));
    await fireEvent.press(screen.getByRole("button", { name: "Guardar servicio" }));
    expect(screen.getByText("Escribe el nombre del servicio.")).toBeTruthy();
    expect(mockEndpoints.addService).not.toHaveBeenCalled();
    expect(screen.queryByText("Quién lo ofrece")).toBeNull();
    expect(screen.getByText(/Qué agentes lo ofrecen lo decide Amacrux\./)).toBeTruthy();
  });
});

describe("Negocio › Sedes (9)", () => {
  it("adding one checks the phone; archiving asks, and the notice brings it back", async () => {
    mockEndpoints.addLocation.mockResolvedValue(business().locations);
    await open("sedes");
    await fireEvent.press(screen.getByRole("button", { name: "Añadir sede" }));
    await fireEvent.changeText(screen.getByLabelText("Nombre"), "Ñuñoa");
    await fireEvent.changeText(screen.getByLabelText("Teléfono"), "5555");
    await fireEvent.press(screen.getByRole("button", { name: "Guardar sede" }));
    expect(screen.getByText("Escribe el teléfono con el prefijo del país, por ejemplo +34600123456.")).toBeTruthy();
    await fireEvent.changeText(screen.getByLabelText("Teléfono"), "+56 9 5555 0202");
    await fireEvent.press(screen.getByRole("button", { name: "Guardar sede" }));
    expect(mockEndpoints.addLocation).toHaveBeenCalledWith({ name: "Ñuñoa", address: null, phone_e164: "+56955550202" }, 1, expect.any(String));
    await waitFor(() => expect(screen.queryByTestId("location-form-new")).toBeNull());

    const alert = jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
    mockEndpoints.archiveLocation.mockResolvedValue({ ...business().locations, revision: 2, items: [] });
    mockEndpoints.restoreLocation.mockResolvedValue(business().locations);
    await fireEvent.press(screen.getByRole("button", { name: "Editar Providencia" }));
    await fireEvent.press(screen.getByRole("button", { name: "Archivar Providencia" }));
    const buttons = alert.mock.calls[0]![2] as { text: string; onPress?: () => void }[];
    await act(async () => buttons.find((b) => b.text === "Archivar Providencia")!.onPress!());
    expect(mockEndpoints.archiveLocation).toHaveBeenCalledWith(LOCATION, 1, expect.any(String));
    expect(await screen.findByText("Providencia archivada.")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Deshacer" }));
    await waitFor(() => expect(mockEndpoints.restoreLocation).toHaveBeenCalledWith(LOCATION, expect.any(Number), expect.any(String)));
    alert.mockRestore();
  });
});

describe("what was typed stays, in memory (50.5)", () => {
  it("survives leaving the screen and coming back; a save clears it", async () => {
    const first = await renderHook(() => useDraft<string>("test.draft"));
    await act(async () => first.result.current[1]("Lunes cerrado"));
    first.unmount();
    const again = await renderHook(() => useDraft<string>("test.draft"));
    expect(again.result.current[0]).toBe("Lunes cerrado");
    await act(async () => again.result.current[1](null));
    expect(peekDraft("test.draft")).toBeUndefined();
  });
});
