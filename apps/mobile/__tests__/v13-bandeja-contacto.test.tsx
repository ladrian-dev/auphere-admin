import { fireEvent, render, screen } from "@testing-library/react-native";

/**
 * Spec 069, Requisito 12 (T020, T034): the contact says its real channel and
 * what its identifier is — «Teléfono» on WhatsApp, «Cuenta» on Instagram and
 * Messenger (Historia 2, escenario 3) — with the photo when the API has one.
 */
const mockDetail = { current: {} as Record<string, unknown> };
jest.mock("@/api/endpoints", () => ({ endpoints: { setTags: jest.fn(), setNote: jest.fn() } }));
jest.mock("@/api/hooks", () => ({
  useConversation: () => mockDetail.current,
  useSuggestedTags: () => ({ data: { tags: [] } }),
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
  useReservasConfig: () => ({ data: { timezone: "Europe/Madrid" } }),
  useBizToday: () => "2026-11-21",
}));
jest.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ setQueryData: jest.fn(), invalidateQueries: jest.fn() }),
}));
jest.mock("@/api/v13-bandeja-hooks", () => ({
  useAvatarSource: (id: string, has: boolean) => (has ? { uri: `http://api/console/lite/inbox/conversations/${id}/avatar`, headers: { Authorization: "Bearer tok" } } : null),
}));
const mockImage = jest.fn();
jest.mock("expo-image", () => ({ Image: (p: unknown) => (mockImage(p), null) }));

const detail = (kind: string, handle: string, extra: Record<string, unknown> = {}) => ({
  id: "c1",
  state: "agent",
  assignee: null,
  agent: { id: "a1", name: "Recepción" },
  handled_by_agent: { id: "a1", name: "Recepción" },
  control_version: 1,
  window: { open: true, agent_open: true, closes_at: null },
  channel: { kind, connected: true },
  contact: { name: "Sofía Herrera", handle, first_message_at: "2026-11-18T09:00:00Z", conversations: 2, has_avatar: false, ...extra },
  summary: null,
  waiting_reason: null,
  tags: [],
  note: { body: "", updated_at: null },
  activity: [],
});

const Contacto = require("@/app/conversacion/[id]/contacto").default;

beforeEach(() => {
  mockHasReservas.current = false;
  mockImage.mockClear();
});

it.each([
  ["instagram", "@sofi.herrera", "Instagram", "Cuenta"],
  ["messenger", "Sofía Herrera", "Messenger", "Cuenta"],
  ["whatsapp", "+34 612 48 19 07", "WhatsApp", "Teléfono"],
])("on %s it says the channel and «%s» as its %s", async (kind, handle, channel, label) => {
  mockDetail.current = { data: detail(kind, handle), isError: false, refetch: jest.fn() };
  await render(<Contacto />);
  expect(screen.getByLabelText(`Canal: ${channel}`)).toBeTruthy();
  expect(screen.getByLabelText(`${label}: ${handle}`)).toBeTruthy();
  if (kind !== "whatsapp") expect(screen.queryByText("WhatsApp")).toBeNull();
});

it("the first message, the conversations and who answers, from the data", async () => {
  mockDetail.current = { data: detail("instagram", "@sofi.herrera"), isError: false, refetch: jest.fn() };
  await render(<Contacto />);
  expect(screen.getByLabelText(/^Primer mensaje: 18 de noviembre de 2026$/)).toBeTruthy();
  expect(screen.getByLabelText("Conversaciones: 2")).toBeTruthy();
  expect(screen.getByText("Atiende Recepción")).toBeTruthy();
});

it("with a photo from the API it is fetched with the phone's credential, never as a link", async () => {
  mockDetail.current = { data: detail("instagram", "@sofi.herrera", { has_avatar: true }), isError: false, refetch: jest.fn() };
  await render(<Contacto />);
  const source = (mockImage.mock.calls.at(-1)?.[0] as { source: { uri: string; headers: Record<string, string> } }).source;
  expect(source.uri).toContain("/conversations/c1/avatar");
  expect(source.headers.Authorization).toBe("Bearer tok");
});

it("the next reservation opens it (R12.2)", async () => {
  mockHasReservas.current = true;
  const next = { id: "r1", starts_at: "2026-11-22T16:00:00Z", local: { date: "2026-11-22", start: "17:00", end: "17:30" }, status: "confirmed", service_name: "Revisión", party_size: null };
  mockDetail.current = { data: { ...detail("whatsapp", "+34 600 000 000"), contact: { ...detail("whatsapp", "+34 600 000 000").contact, next_booking: next } }, isError: false, refetch: jest.fn() };
  await render(<Contacto />);
  await fireEvent.press(screen.getByRole("button", { name: /^Próxima reserva\./ }));
  expect(mockNavigate).toHaveBeenCalledWith({ pathname: "/reservas", params: { date: "2026-11-22", open: "r1" } });
});
