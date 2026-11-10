import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";

import { ApiError } from "@/api/errors";

/**
 * Spec 031 (T080, R12.1, R12.2): the contact sheet.
 */
const mockSetTags = jest.fn();
const mockSetNote = jest.fn();
const mockDetail = { current: {} as Record<string, unknown> };
jest.mock("@/api/endpoints", () => ({
  endpoints: { setTags: (...a: unknown[]) => mockSetTags(...a), setNote: (...a: unknown[]) => mockSetNote(...a) },
}));
jest.mock("@/api/hooks", () => ({
  useConversation: () => mockDetail.current,
  useSuggestedTags: () => ({ data: { tags: ["vip", "reserva"] } }),
}));
jest.mock("@/ui/online", () => ({ useOnline: () => true }));
const mockBack = jest.fn();
const mockNavigate = jest.fn();
jest.mock("expo-router", () => ({
  useLocalSearchParams: () => ({ id: "c1" }),
  router: { back: (...a: unknown[]) => mockBack(...a), navigate: (...a: unknown[]) => mockNavigate(...a) },
}));
const mockHasReservas = { current: false };
jest.mock("@/api/reservas-hooks", () => ({
  useHasReservas: () => mockHasReservas.current,
  useReservasConfig: () => ({ data: { timezone: "America/Santiago" } }),
  useBizToday: () => "2026-10-22",
}));
let mockGlass = false;
jest.mock("expo-glass-effect", () => ({ isLiquidGlassAvailable: () => mockGlass }));
const mockSetQueryData = jest.fn();
jest.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ setQueryData: mockSetQueryData, invalidateQueries: jest.fn() }),
}));

const detail = {
  id: "c1",
  state: "person",
  assignee: { kind: "member", name: null, is_me: true },
  agent: { id: "a1", name: "Recepción" },
  control_version: 2,
  window: { open: true, closes_at: null },
  channel: { kind: "whatsapp", connected: true },
  contact: { name: "Ana López", handle: "+34 600 111 222", first_message_at: "2026-09-01T10:00:00Z", conversations: 3 },
  summary: "Quiere cambiar la cita del jueves.",
  waiting_reason: null,
  tags: ["cliente"],
  note: { body: "Prefiere WhatsApp.", updated_at: null },
  activity: [{ kind: "takeover", at: "2026-10-08T10:00:00Z", actor: { kind: "member", name: null, is_me: true }, detail: null }],
};

const Contacto = require("@/app/conversacion/[id]/contacto").default;

beforeEach(() => {
  mockDetail.current = { data: detail, isError: false, refetch: jest.fn() };
  mockHasReservas.current = false;
  mockBack.mockReset();
  mockNavigate.mockReset();
  mockSetTags.mockReset();
  mockSetNote.mockReset();
});

describe("as a sheet with glass (spec 042, T063, T067, R1.7)", () => {
  it("with Liquid Glass the scroll paints no background and respects the inset of a transparent header", async () => {
    mockGlass = true;
    const { StyleSheet } = require("react-native");
    await render(<Contacto />);
    const scroll = screen.getByTestId("contact-scroll");
    expect(StyleSheet.flatten(scroll.props.style)?.backgroundColor).toBeUndefined();
    expect(scroll.props.contentInsetAdjustmentBehavior).toBe("automatic");
    mockGlass = false;
  });

  it("without it, the background of today", async () => {
    const { StyleSheet } = require("react-native");
    const { tokens } = require("@/theme/tokens.gen");
    await render(<Contacto />);
    expect(StyleSheet.flatten(screen.getByTestId("contact-scroll").props.style)?.backgroundColor).toBe(tokens.light.background);
  });
});

it("shows the data, the summary, the tags, the note and the activity", async () => {
  await render(<Contacto />);
  expect(screen.getByRole("header", { name: "Ana López" })).toBeTruthy();
  expect(screen.getByLabelText("Teléfono: +34 600 111 222")).toBeTruthy();
  expect(screen.getByText("Quiere cambiar la cita del jueves.")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Quitar cliente" })).toBeTruthy();
  expect(screen.getByLabelText("Notas internas").props.value).toBe("Prefiere WhatsApp.");
  expect(screen.getByText("Tomaste el control")).toBeTruthy();
});

it("adding and removing a tag calls PUT …/tags", async () => {
  mockSetTags.mockResolvedValue({ tags: ["cliente", "vip"] });
  await render(<Contacto />);
  await fireEvent.press(screen.getByRole("button", { name: "Agregar etiqueta: vip" }));
  expect(mockSetTags).toHaveBeenCalledWith("c1", ["cliente", "vip"]);
  await fireEvent.press(screen.getByRole("button", { name: "Quitar cliente" }));
  expect(mockSetTags).toHaveBeenLastCalledWith("c1", []);
});

it("editing the note calls PUT …/note and says it is saved", async () => {
  mockSetNote.mockResolvedValue({ body: "Prefiere llamadas.", updated_at: "2026-10-08T11:00:00Z" });
  await render(<Contacto />);
  await fireEvent.changeText(screen.getByLabelText("Notas internas"), "Prefiere llamadas.");
  await fireEvent.press(screen.getByRole("button", { name: "Guardar nota" }));
  expect(mockSetNote).toHaveBeenCalledWith("c1", "Prefiere llamadas.");
  await waitFor(() => expect(screen.getByText("Guardada")).toBeTruthy());
});

it("a refused change (422) is said at the field and undone", async () => {
  mockSetTags.mockRejectedValue(new ApiError(422, "too_many_tags"));
  await render(<Contacto />);
  await fireEvent.press(screen.getByRole("button", { name: "Agregar etiqueta: vip" }));
  await waitFor(() => expect(screen.getByText("No se pudo completar. Inténtalo de nuevo.")).toBeTruthy());
  expect(mockSetQueryData).toHaveBeenCalled();
});

it("loading and error states", async () => {
  mockDetail.current = { data: undefined, isError: false, refetch: jest.fn() };
  await render(<Contacto />);
  expect(screen.getByRole("progressbar")).toBeTruthy();
  mockDetail.current = { data: undefined, isError: true, refetch: jest.fn() };
  await render(<Contacto />);
  expect(screen.getByRole("alert")).toBeTruthy();
});

/**
 * Spec 044, Historia 7, Requisito 12: the contact's next reservation, and the
 * way to it without changing tabs by hand.
 */
describe("the next reservation (R12)", () => {
  // 043 §1: the contact gains `next_booking`.
  const next = {
    id: "r9",
    starts_at: "2026-10-23T20:00:00Z",
    local: { date: "2026-10-23", start: "17:00", end: "17:45" },
    status: "confirmed",
    service_name: "Corte y peinado con Marcos",
    party_size: null,
  };

  it("with Reservas and a reservation ahead, a row that says when and what", async () => {
    mockHasReservas.current = true;
    mockDetail.current = { data: { ...detail, contact: { ...detail.contact, next_booking: next } }, isError: false, refetch: jest.fn() };
    await render(<Contacto />);
    expect(screen.getByRole("button", { name: "Próxima reserva. Mañana a las 17:00 · Corte y peinado con Marcos" })).toBeTruthy();
  });

  it("takes you to that day in Reservas with the reservation open, closing the sheet (R12.2)", async () => {
    mockHasReservas.current = true;
    mockDetail.current = { data: { ...detail, contact: { ...detail.contact, next_booking: next } }, isError: false, refetch: jest.fn() };
    await render(<Contacto />);
    await fireEvent.press(screen.getByRole("button", { name: /^Próxima reserva\./ }));
    expect(mockBack).toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith({ pathname: "/reservas", params: { date: "2026-10-23", open: "r9" } });
  });

  it("without the module there is nothing — not even with a reservation (R1.2)", async () => {
    mockDetail.current = { data: { ...detail, contact: { ...detail.contact, next_booking: next } }, isError: false, refetch: jest.fn() };
    await render(<Contacto />);
    expect(screen.queryByText("Próxima reserva")).toBeNull();
  });

  it("with the module but nothing ahead, nothing either", async () => {
    mockHasReservas.current = true;
    await render(<Contacto />);
    expect(screen.queryByText("Próxima reserva")).toBeNull();
  });
});
