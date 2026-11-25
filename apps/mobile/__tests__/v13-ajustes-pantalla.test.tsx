import { fireEvent, render, screen, within } from "@testing-library/react-native";
import { Alert, Linking } from "react-native";

import type { AutocloseState } from "@/api/v13-ajustes-hooks";

/**
 * Spec 069, Historia 8, Requisito 19 (T040) and 17.2 (T038): Ajustes — the
 * account and the business, the connected channels with their state, this
 * phone's notices (turning the urgent one off asks first), the quiet hours,
 * the Bandeja's inactivity close, privacy and support, the web console,
 * signing out with what it means, the deletion request and the version.
 */
let mockNav = ["panel", "inbox"];
let mockOnline = true;
let mockAgents = [{ id: "a1", name: "Recepción" }];
let mockChannels: { kind: string; connected: boolean }[] = [];
let mockNotices: Record<string, unknown> = { kinds: ["inbox.waiting", "inbox.message_for_you", "client.balance"] };
let mockAutoclose: AutocloseState = { state: "off" };
const mockSetNotices = jest.fn(async (kinds: string[], quiet?: boolean) => ({ kinds, ...(quiet === undefined ? {} : { quiet_outside_hours: quiet }) }));
const mockSignOut = jest.fn();
const mockOpen = jest.fn();
jest.mock("@/push/provider", () => ({ usePush: () => ({ permission: "granted", enable: jest.fn() }) }));
jest.mock("@/auth/session", () => ({ useSession: () => ({ signOut: mockSignOut }) }));
jest.mock("@/api/hooks", () => ({
  useMe: () => ({
    data: {
      user: { name: "Valeria Ríos", email: "valeria@flor.test" },
      client: { name: "Flor y Encanto" },
      nav: mockNav,
      agents: mockAgents,
      channels: mockChannels,
      business: { timezone: "America/Santiago", hours: null, hours_label: "lunes a viernes 9:00–19:00" },
    },
  }),
  useNotices: () => ({ data: mockNotices }),
}));
jest.mock("@/api/v13-ajustes-hooks", () => ({ useInboxAutoclose: () => mockAutoclose }));
jest.mock("@/api/endpoints", () => ({
  endpoints: { setNotices: (k: string[], q?: boolean) => mockSetNotices(k, q), requestDeletion: jest.fn(async () => undefined) },
}));
jest.mock("@/api/reservas", () => ({ demo: null }));
jest.mock("@/ui/online", () => ({ useOnline: () => mockOnline }));
jest.mock("@tanstack/react-query", () => ({ useQueryClient: () => ({ setQueryData: jest.fn() }) }));
jest.mock("expo-web-browser", () => ({ openBrowserAsync: (url: string) => mockOpen(url) }));

const Ajustes = require("@/app/ajustes").default;

beforeEach(() => {
  mockNav = ["panel", "inbox"];
  mockOnline = true;
  mockAgents = [{ id: "a1", name: "Recepción" }];
  mockChannels = [];
  mockNotices = { kinds: ["inbox.waiting", "inbox.message_for_you", "client.balance"] };
  mockAutoclose = { state: "off" };
  mockSetNotices.mockClear();
  mockOpen.mockClear();
});

describe("connected channels (R19.1)", () => {
  it("each channel the app knows, with its own mark and its state in words; other kinds are not drawn", async () => {
    mockChannels = [
      { kind: "whatsapp", connected: true },
      { kind: "whatsapp", connected: false },
      { kind: "instagram", connected: true },
      { kind: "messenger", connected: false },
      { kind: "telegram", connected: true },
    ];
    await render(<Ajustes />);
    const section = screen.getByTestId("settings-channels");
    expect(within(section).getByLabelText("WhatsApp: 1 de 2 conectados")).toBeTruthy();
    expect(within(section).getByLabelText("Instagram: Conectado")).toBeTruthy();
    expect(within(section).getByLabelText("Messenger: Sin conectar")).toBeTruthy();
    expect(within(section).queryByText(/telegram/i)).toBeNull();
    // Not every one is connected: «{agent} atiende en todos» would not be true.
    expect(within(section).queryByText(/atiende en todos/)).toBeNull();
  });

  it("all connected and one agent: «{agent} atiende en todos», the name from `/me`", async () => {
    mockChannels = [
      { kind: "whatsapp", connected: true },
      { kind: "instagram", connected: true },
    ];
    await render(<Ajustes />);
    expect(screen.getByText("Recepción atiende en todos")).toBeTruthy();
  });

  it("none yet: it says so and where they are connected", async () => {
    await render(<Ajustes />);
    expect(screen.getByText("Todavía no hay canales conectados. Se conectan desde la consola web.")).toBeTruthy();
  });
});

describe("the urgent notice asks before going off (R19.2, Historia 8 escenario 1)", () => {
  it("off: «¿Apagar el aviso urgente?» first, and nothing is saved until «Apagar»", async () => {
    const alert = jest.spyOn(Alert, "alert");
    await render(<Ajustes />);
    await fireEvent(screen.getByRole("switch", { name: "Una conversación espera a una persona" }), "valueChange", false);
    const [title, body, buttons] = alert.mock.calls.at(-1)!;
    expect(title).toBe("¿Apagar el aviso urgente?");
    expect(body).toBe("No sabrás en este teléfono cuándo alguien espera a una persona.");
    const [keep, off] = buttons as { text: string; style?: string; onPress?: () => void }[];
    expect(keep!.text).toBe("Mantenerlo");
    expect(off!.text).toBe("Apagar");
    // «Apagar» is the dialog's main action, not a destructive one (design §10.1).
    expect(off!.style).not.toBe("destructive");
    expect(mockSetNotices).not.toHaveBeenCalled();
    keep!.onPress?.();
    expect(mockSetNotices).not.toHaveBeenCalled();
    off!.onPress?.();
    expect(mockSetNotices).toHaveBeenCalledWith(["inbox.message_for_you", "client.balance"], undefined);
  });

  it("on again: no question", async () => {
    mockNotices = { kinds: ["client.balance"] };
    const alert = jest.spyOn(Alert, "alert");
    alert.mockClear();
    await render(<Ajustes />);
    await fireEvent(screen.getByRole("switch", { name: "Una conversación espera a una persona" }), "valueChange", true);
    expect(alert).not.toHaveBeenCalled();
    expect(mockSetNotices).toHaveBeenCalledWith(["inbox.waiting", "client.balance"], undefined);
  });

  it("any other kind goes off without asking", async () => {
    const alert = jest.spyOn(Alert, "alert");
    alert.mockClear();
    await render(<Ajustes />);
    await fireEvent(screen.getByRole("switch", { name: "Mensaje nuevo donde respondes tú" }), "valueChange", false);
    expect(alert).not.toHaveBeenCalled();
    expect(mockSetNotices).toHaveBeenCalledWith(["inbox.waiting", "client.balance"], undefined);
  });
});

describe("the Bandeja's inactivity close (R17.2)", () => {
  it("the choices of the web, the stored one ticked; choosing one saves it", async () => {
    const save = jest.fn(async () => undefined);
    mockAutoclose = { state: "ready", hours: 72, status: "idle", save };
    await render(<Ajustes />);
    const section = screen.getByTestId("settings-inbox");
    expect(within(section).getByRole("header", { name: "Bandeja" })).toBeTruthy();
    expect(within(section).getByText("Cerrar las conversaciones sin mensajes")).toBeTruthy();
    const radios = within(section).getAllByRole("radio");
    expect(radios.map((r) => r.props.accessibilityLabel)).toEqual(["Nunca", "Tras 24 horas", "Tras 3 días", "Tras 7 días", "Tras 30 días"]);
    expect(within(section).getByRole("radio", { name: "Tras 3 días" }).props.accessibilityState).toMatchObject({ checked: true });
    await fireEvent.press(within(section).getByRole("radio", { name: "Tras 7 días" }));
    expect(save).toHaveBeenCalledWith(168);
    await fireEvent.press(within(section).getByRole("radio", { name: "Nunca" }));
    expect(save).toHaveBeenCalledWith(null);
  });

  it("a failed save says so (what is stored is back, by the hook)", async () => {
    mockAutoclose = { state: "ready", hours: null, status: "failed", save: jest.fn() };
    await render(<Ajustes />);
    expect(screen.getByText("No se pudo guardar. Inténtalo de nuevo.")).toBeTruthy();
  });

  it("loading and failing to read are said in place, with «Reintentar»", async () => {
    mockAutoclose = { state: "loading" };
    await render(<Ajustes />);
    expect(screen.getByRole("progressbar", { name: "Cargando los ajustes" })).toBeTruthy();
    const retry = jest.fn();
    mockAutoclose = { state: "error", retry };
    await render(<Ajustes />);
    expect(screen.getByText("No pudimos cargar los ajustes.")).toBeTruthy();
    await fireEvent.press(within(screen.getByTestId("settings-inbox")).getByRole("button", { name: "Reintentar" }));
    expect(retry).toHaveBeenCalled();
  });

  it("offline nothing can be chosen", async () => {
    mockOnline = false;
    const save = jest.fn();
    mockAutoclose = { state: "ready", hours: 24, status: "idle", save };
    await render(<Ajustes />);
    const radio = within(screen.getByTestId("settings-inbox")).getByRole("radio", { name: "Tras 3 días" });
    expect(radio.props.accessibilityState).toMatchObject({ disabled: true });
    await fireEvent.press(radio);
    expect(save).not.toHaveBeenCalled();
  });

  it("without the Bandeja there is no such section", async () => {
    mockNav = ["panel", "usage"];
    await render(<Ajustes />);
    expect(screen.queryByTestId("settings-inbox")).toBeNull();
  });
});

describe("privacy and support (R19.1, Historia 8 escenario 2)", () => {
  it("«Política de privacidad» opens the published policy", async () => {
    await render(<Ajustes />);
    await fireEvent.press(screen.getByRole("button", { name: /^Política de privacidad/ }));
    expect(mockOpen).toHaveBeenCalledWith("https://www.auphere.com/es/privacidad");
  });

  it("«Soporte» writes to contacto@auphere.com, and the address is on screen", async () => {
    const open = jest.spyOn(Linking, "openURL").mockResolvedValue(undefined);
    await render(<Ajustes />);
    expect(screen.getByText("contacto@auphere.com")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: /^Soporte/ }));
    expect(open).toHaveBeenCalledWith("mailto:contacto@auphere.com");
  });
});

describe("signing out says what it means (R19.3)", () => {
  it("one agent: it names it, says the notices stop here and the agent keeps answering", async () => {
    const alert = jest.spyOn(Alert, "alert");
    await render(<Ajustes />);
    await fireEvent.press(screen.getByRole("button", { name: "Cerrar sesión en este teléfono" }));
    const [title, body, buttons] = alert.mock.calls.at(-1)!;
    expect(title).toBe("¿Cerrar sesión?");
    expect(body).toBe("Recepción sigue atendiendo. Dejas de recibir avisos en este teléfono. Tus otros teléfonos siguen como están.");
    expect((buttons as { text: string }[]).map((b) => b.text)).toEqual(["Cancelar", "Cerrar sesión"]);
  });

  it("several agents: «Tus agentes siguen atendiendo», never a made-up name", async () => {
    mockAgents = [
      { id: "a1", name: "Recepción" },
      { id: "a2", name: "Ventas" },
    ];
    const alert = jest.spyOn(Alert, "alert");
    await render(<Ajustes />);
    await fireEvent.press(screen.getByRole("button", { name: "Cerrar sesión en este teléfono" }));
    expect(alert.mock.calls.at(-1)![1]).toBe("Tus agentes siguen atendiendo. Dejas de recibir avisos en este teléfono. Tus otros teléfonos siguen como están.");
  });
});

it("the version, as the design names the app", async () => {
  await render(<Ajustes />);
  expect(screen.getByText(/^Auphere Customers \d+\.\d+\.\d+/)).toBeTruthy();
});

it("offline: it says so, with what is on screen still readable", async () => {
  mockOnline = false;
  await render(<Ajustes />);
  expect(screen.getByText("Sin conexión. Ves lo último que se cargó.")).toBeTruthy();
  expect(screen.getByText("Valeria Ríos")).toBeTruthy();
});
