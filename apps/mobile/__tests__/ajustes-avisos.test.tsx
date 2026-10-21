import { fireEvent, render, screen } from "@testing-library/react-native";
import { Alert, Linking } from "react-native";

/**
 * Spec 031 (T103, R10.2, R10.3, R11.1–R11.4): Ajustes.
 */
let mockPermission = "granted";
const mockEnable = jest.fn();
const mockSignOut = jest.fn();
const mockRequestDeletion = jest.fn(async () => undefined);
jest.mock("@/push/provider", () => ({ usePush: () => ({ permission: mockPermission, enable: mockEnable }) }));
jest.mock("@/auth/session", () => ({ useSession: () => ({ signOut: mockSignOut }) }));
jest.mock("@/api/hooks", () => ({
  useMe: () => ({ data: { user: { name: "Valeria Ríos", email: "valeria@flor.test" }, client: { name: "Flor y Encanto" }, nav: ["panel", "inbox"] } }),
  useNotices: () => ({ data: { kinds: ["inbox.waiting", "client.balance"] } }),
}));
jest.mock("@/api/endpoints", () => ({ endpoints: { setNotices: jest.fn(), requestDeletion: () => mockRequestDeletion() } }));
jest.mock("@/ui/online", () => ({ useOnline: () => true }));
jest.mock("@tanstack/react-query", () => ({ useQueryClient: () => ({ setQueryData: jest.fn() }) }));
jest.mock("expo-web-browser", () => ({ openBrowserAsync: jest.fn() }));

const Ajustes = require("@/app/ajustes").default;

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

it("«Cerrar sesión» confirms, then signs out this phone only", async () => {
  const alert = jest.spyOn(Alert, "alert");
  await render(<Ajustes />);
  await fireEvent.press(screen.getByRole("button", { name: "Cerrar sesión" }));
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
    expect(colour("Cerrar sesión")).not.toBe(tokens.light.destructive);
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
