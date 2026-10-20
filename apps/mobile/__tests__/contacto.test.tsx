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
jest.mock("expo-router", () => ({ useLocalSearchParams: () => ({ id: "c1" }) }));
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
  mockSetTags.mockReset();
  mockSetNote.mockReset();
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
