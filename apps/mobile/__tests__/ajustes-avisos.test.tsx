import { fireEvent, render, screen } from "@testing-library/react-native";
import { Alert, Linking } from "react-native";

/**
 * Spec 031 (T103, R10.2, R10.3, R11.1–R11.4): Ajustes.
 */
let mockPermission = "granted";
let mockNav = ["panel", "inbox"];
let mockNotices: Record<string, unknown> = { kinds: ["inbox.waiting", "client.balance"] };
const mockSetNotices = jest.fn(async (kinds: string[], quiet?: boolean) => ({ kinds, ...(quiet === undefined ? {} : { quiet_outside_hours: quiet }) }));
const mockEnable = jest.fn();
const mockSignOut = jest.fn();
const mockRequestDeletion = jest.fn(async () => undefined);
jest.mock("@/push/provider", () => ({ usePush: () => ({ permission: mockPermission, enable: mockEnable }) }));
jest.mock("@/auth/session", () => ({ useSession: () => ({ signOut: mockSignOut }) }));
jest.mock("@/api/hooks", () => ({
  // 045 §4: the business hours come with `/me`.
  useMe: () => ({
    data: {
      user: { name: "Valeria Ríos", email: "valeria@flor.test" },
      client: { name: "Flor y Encanto" },
      nav: mockNav,
      business: { timezone: "America/Santiago", hours: null, hours_label: "lunes a viernes 9:00–19:00, sábado 9:00–14:00" },
    },
  }),
  useNotices: () => ({ data: mockNotices }),
}));
jest.mock("@/api/endpoints", () => ({
  endpoints: { setNotices: (k: string[], q?: boolean) => mockSetNotices(k, q), requestDeletion: () => mockRequestDeletion() },
}));
// No example data in tests: the real endpoints are the ones called.
jest.mock("@/api/reservas", () => ({ demo: null }));
jest.mock("@/ui/online", () => ({ useOnline: () => true }));
jest.mock("@tanstack/react-query", () => ({ useQueryClient: () => ({ setQueryData: jest.fn() }) }));
jest.mock("expo-web-browser", () => ({ openBrowserAsync: jest.fn() }));
let mockGlass = false;
jest.mock("expo-glass-effect", () => ({ isLiquidGlassAvailable: () => mockGlass }));

const Ajustes = require("@/app/ajustes").default;

describe("as a sheet with glass (spec 042, T063, T066, R1.7)", () => {
  it("with Liquid Glass the scroll paints no background and respects the transparent header's inset", async () => {
    mockGlass = true;
    const { StyleSheet } = require("react-native");
    await render(<Ajustes />);
    const scroll = screen.getByTestId("settings-scroll");
    expect(StyleSheet.flatten(scroll.props.style)?.backgroundColor).toBeUndefined();
    expect(scroll.props.contentInsetAdjustmentBehavior).toBe("automatic");
    mockGlass = false;
  });

  it("without it, the background of today", async () => {
    const { StyleSheet } = require("react-native");
    const { tokens } = require("@/theme/tokens.gen");
    await render(<Ajustes />);
    expect(StyleSheet.flatten(screen.getByTestId("settings-scroll").props.style)?.backgroundColor).toBe(tokens.light.background);
  });
});

it("who you are here: name, email, business and role", async () => {
  await render(<Ajustes />);
  expect(screen.getByText("Valeria Ríos")).toBeTruthy();
  expect(screen.getByText("valeria@flor.test")).toBeTruthy();
  expect(screen.getByLabelText("Negocio: Flor y Encanto")).toBeTruthy();
  expect(screen.getByLabelText("Papel: Persona del negocio")).toBeTruthy();
});

it("with permission, one switch per kind this person can get", async () => {
  mockPermission = "granted";
  await render(<Ajustes />);
  expect(screen.getAllByRole("switch")).toHaveLength(3);
  expect(screen.getByRole("switch", { name: "Mensaje nuevo donde respondes tú" }).props.value).toBe(false);
});

it("denied: no switch, the reason, and the phone's settings", async () => {
  mockPermission = "denied";
  const open = jest.spyOn(Linking, "openSettings").mockResolvedValue();
  await render(<Ajustes />);
  expect(screen.queryAllByRole("switch")).toHaveLength(0);
  expect(screen.getByText("Los avisos están desactivados en los ajustes del teléfono.")).toBeTruthy();
  await fireEvent.press(screen.getByRole("button", { name: "Abrir los ajustes del teléfono" }));
  expect(open).toHaveBeenCalled();
});

it("after «Ahora no», «Activar avisos» asks the system", async () => {
  mockPermission = "undetermined";
  await render(<Ajustes />);
  await fireEvent.press(screen.getByRole("button", { name: "Activar avisos" }));
  expect(mockEnable).toHaveBeenCalled();
});

it("«Solicitar el borrado» confirms first and says what happens next", async () => {
  mockPermission = "granted";
  const alert = jest.spyOn(Alert, "alert");
  await render(<Ajustes />);
  await fireEvent.press(screen.getByRole("button", { name: "Solicitar el borrado de la cuenta" }));
  const [title, body, buttons] = alert.mock.calls[0]!;
  expect(title).toBe("¿Solicitar el borrado de tu cuenta?");
  expect(body).toMatch(/un mes como máximo/);
  expect(mockRequestDeletion).not.toHaveBeenCalled();
  (buttons as { onPress?: () => void }[])[1]!.onPress?.();
  expect(mockRequestDeletion).toHaveBeenCalled();
});

it("«Cerrar sesión en este teléfono» confirms, then signs out this phone only", async () => {
  const alert = jest.spyOn(Alert, "alert");
  await render(<Ajustes />);
  await fireEvent.press(screen.getByRole("button", { name: "Cerrar sesión en este teléfono" }));
  const [, body, buttons] = alert.mock.calls.at(-1)!;
  expect(body).toMatch(/Tus otros teléfonos siguen como están/);
  (buttons as { onPress?: () => void }[])[1]!.onPress?.();
  expect(mockSignOut).toHaveBeenCalled();
});

describe("two risks, two sections (spec 042, T040, R8)", () => {
  it("«Cerrar sesión» and the account's deletion live in different groups, the deletion last", async () => {
    mockPermission = "granted";
    await render(<Ajustes />);
    const groups = screen.getAllByTestId(/^settings-/).map((n) => n.props.testID as string);
    expect(groups.indexOf("settings-signout")).toBeGreaterThan(-1);
    expect(groups.indexOf("settings-deletion")).toBe(groups.length - 1);
    expect(groups.indexOf("settings-deletion")).not.toBe(groups.indexOf("settings-signout"));
  });

  it("only the deletion wears the colour of danger, and it says what happens next before being tapped", async () => {
    const { tokens } = require("@/theme/tokens.gen");
    const { StyleSheet } = require("react-native");
    await render(<Ajustes />);
    const colour = (text: string) => StyleSheet.flatten(screen.getByText(text).props.style).color as string;
    expect(colour("Solicitar el borrado de la cuenta")).toBe(tokens.light.destructive);
    expect(colour("Cerrar sesión en este teléfono")).not.toBe(tokens.light.destructive);
    expect(screen.getByText("Auphere te escribirá para confirmarlo y cerrará tu acceso.")).toBeTruthy();
  });

  it("the way to the web says it leaves the app", async () => {
    await render(<Ajustes />);
    expect(screen.getByTestId("row-indicator-external")).toBeTruthy();
    expect(screen.queryByTestId("row-indicator-push")).toBeNull();
  });
});

it("the version says which environment a test build talks to, and nothing in production", () => {
  const { versionLabel } = require("@/lib/version");
  expect(versionLabel("1.0.0", "production")).toBe("1.0.0");
  expect(versionLabel("1.0.0", "staging")).toBe("1.0.0 · staging");
  expect(versionLabel("1.0.0", "development")).toBe("1.0.0 · development");
});

/**
 * Spec 044 (Historia 10, R14.1–R14.3): notices grouped by module, Reservas'
 * three only with the module, and the quiet hours when the API has them.
 */
describe("notices by module (spec 044, R14.1, R14.2)", () => {
  beforeEach(() => {
    mockPermission = "granted";
    mockSetNotices.mockClear();
  });
  afterEach(() => {
    mockNav = ["panel", "inbox"];
    mockNotices = { kinds: ["inbox.waiting", "client.balance"] };
  });

  it("with Reservas: three groups — Bandeja, Reservas, Saldo — and the waitlist one off unless the API says on", async () => {
    mockNav = ["panel", "inbox", "reservas", "usage"];
    mockNotices = { kinds: ["inbox.waiting", "client.balance", "reservas.agent_change", "reservas.cancelled_today"] };
    await render(<Ajustes />);
    for (const g of ["Bandeja", "Reservas", "Saldo"]) expect(screen.getByRole("header", { name: g })).toBeTruthy();
    expect(screen.getAllByRole("switch")).toHaveLength(6);
    expect(screen.getByRole("switch", { name: "Reserva nueva o cambiada por el agente" }).props.value).toBe(true);
    expect(screen.getByRole("switch", { name: "Cancelaciones de hoy" }).props.value).toBe(true);
    expect(screen.getByRole("switch", { name: "Alguien de la lista de espera aceptó" }).props.value).toBe(false);
  });

  it("without Reservas: no Reservas group and none of its kinds", async () => {
    await render(<Ajustes />);
    expect(screen.queryByRole("header", { name: "Reservas" })).toBeNull();
    expect(screen.queryByRole("switch", { name: "Cancelaciones de hoy" })).toBeNull();
  });

  it("turning a kind on sends the whole set this phone gets", async () => {
    mockNav = ["panel", "inbox", "reservas"];
    mockNotices = { kinds: ["inbox.waiting"] };
    await render(<Ajustes />);
    await fireEvent(screen.getByRole("switch", { name: "Alguien de la lista de espera aceptó" }), "valueChange", true);
    expect(mockSetNotices).toHaveBeenCalledWith(["inbox.waiting", "reservas.waitlist_accepted"], undefined);
  });
});

describe("quiet hours (spec 044, R14.3)", () => {
  beforeEach(() => {
    mockPermission = "granted";
    mockSetNotices.mockClear();
  });
  afterEach(() => {
    mockNotices = { kinds: ["inbox.waiting", "client.balance"] };
  });

  it("when the API has them: the switch, the business hours in its hint, and that the urgent still comes", async () => {
    mockNotices = { kinds: ["inbox.waiting"], quiet_outside_hours: true };
    await render(<Ajustes />);
    const quiet = screen.getByRole("switch", { name: "Silenciar fuera del horario del negocio" });
    expect(quiet.props.value).toBe(true);
    expect(screen.getByText("lunes a viernes 9:00–19:00, sábado 9:00–14:00. Lo urgente sigue llegando.")).toBeTruthy();
    await fireEvent(quiet, "valueChange", false);
    expect(mockSetNotices).toHaveBeenCalledWith(["inbox.waiting"], false);
  });

  it("without them in the API, there is no switch", async () => {
    await render(<Ajustes />);
    expect(screen.queryByRole("switch", { name: "Silenciar fuera del horario del negocio" })).toBeNull();
  });
});
