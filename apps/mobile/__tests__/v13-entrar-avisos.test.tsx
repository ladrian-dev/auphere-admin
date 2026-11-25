import { fireEvent, render, screen, waitFor, within } from "@testing-library/react-native";
import { AccessibilityInfo, Platform } from "react-native";

/**
 * Spec 069 (R7.1–R7.3, R1.8, R1.9, R4.3; design §3.4): before the system asks,
 * a real example of the urgent notice — on glass, because a notice is the
 * system's control, not content — and the kinds this phone gets, each with
 * when it arrives. «Activar avisos» opens the system's own permission; a «no»
 * is told where to change it, and the app goes on.
 */
const mockEnable = jest.fn(async (): Promise<string> => "granted");
const mockBack = jest.fn();
const mockAsked = jest.fn(async () => undefined);
let mockGlass = true;

jest.mock("@/push/provider", () => ({ usePush: () => ({ permission: "undetermined", enable: () => mockEnable() }) }));
jest.mock("@/api/hooks", () => ({ useMe: () => ({ data: { nav: ["panel", "inbox", "reservas"] } }) }));
jest.mock("@/auth/store", () => ({ markNoticesAsked: () => mockAsked() }));
jest.mock("expo-router", () => ({ router: { back: () => mockBack(), canGoBack: () => true } }));
jest.mock("expo-image", () => ({ Image: () => null }));
jest.mock("expo-glass-effect", () => {
  const RN = jest.requireActual<typeof import("react-native")>("react-native");
  return {
    isLiquidGlassAvailable: () => mockGlass,
    GlassView: (p: Record<string, unknown>) => <RN.View testID="glass-view" {...p} />,
  };
});

const Screen = require("@/app/notices-permission").default;
let reduceTransparency = false;

beforeEach(() => {
  mockEnable.mockReset();
  mockEnable.mockImplementation(async () => "granted");
  mockBack.mockReset();
  mockAsked.mockClear();
  mockGlass = true;
  reduceTransparency = false;
  Platform.OS = "ios";
  jest.spyOn(AccessibilityInfo, "isReduceTransparencyEnabled").mockImplementation(async () => reduceTransparency);
});

const example = () => screen.getByLabelText(/^Ejemplo de aviso: Lucía Fernández espera a una persona/);

describe("the example notice (R7.1)", () => {
  it("is the urgent one, as the phone shows it, on Liquid Glass where the system draws it", async () => {
    await render(<Screen />);
    await waitFor(() => expect(within(example()).getByTestId("glass-view", { includeHiddenElements: true })).toBeTruthy());
    expect(within(example()).getByText("Auphere Customers", { includeHiddenElements: true })).toBeTruthy();
    expect(within(example()).getByText("ahora", { includeHiddenElements: true })).toBeTruthy();
  });

  it("is opaque with «Reducir transparencia» (R1.9)", async () => {
    reduceTransparency = true;
    await render(<Screen />);
    await waitFor(() => expect(within(example()).queryByTestId("glass-view", { includeHiddenElements: true })).toBeNull());
  });

  it("is a tonal surface on Android, never imitated glass (R4.3)", async () => {
    Platform.OS = "android";
    mockGlass = false;
    await render(<Screen />);
    expect(within(example()).queryByTestId("glass-view", { includeHiddenElements: true })).toBeNull();
  });
});

describe("what this phone gets", () => {
  it("each kind says when it arrives, and the urgent one carries the colour of waiting and its words", async () => {
    await render(<Screen />);
    expect(screen.getByText("Una conversación espera a una persona")).toBeTruthy();
    expect(screen.getByText("Cuando el agente pide ayuda. Es el aviso urgente.")).toBeTruthy();
    expect(screen.getByText("Cambios en las reservas de hoy")).toBeTruthy();
    expect(screen.getByText("Puedes cambiar cada uno después en Ajustes.")).toBeTruthy();
  });
});

describe("the answer (R7.2, R7.3)", () => {
  it("«Activar avisos» opens the system's own permission; granted, it goes on", async () => {
    await render(<Screen />);
    await fireEvent.press(screen.getByRole("button", { name: "Activar avisos" }));
    await waitFor(() => expect(mockBack).toHaveBeenCalled());
    expect(mockEnable).toHaveBeenCalledTimes(1);
    expect(mockAsked).toHaveBeenCalled();
    expect(screen.queryByText(/Sin avisos en este teléfono/)).toBeNull();
  });

  it("a «no» says they can be turned on in Ajustes, and «Seguir» goes on", async () => {
    mockEnable.mockImplementation(async () => "denied");
    await render(<Screen />);
    await fireEvent.press(screen.getByRole("button", { name: "Activar avisos" }));
    await waitFor(() => expect(screen.getByText("Sin avisos en este teléfono. Puedes activarlos en Ajustes cuando quieras.")).toBeTruthy());
    expect(mockBack).not.toHaveBeenCalled();
    const foot = screen.getByTestId("entry-footer");
    expect(within(foot).queryByRole("button", { name: "Activar avisos" })).toBeNull();
    await fireEvent.press(within(foot).getByRole("button", { name: "Seguir" }));
    expect(mockBack).toHaveBeenCalled();
    expect(mockEnable).toHaveBeenCalledTimes(1);
  });

  it("«Ahora no» never asks the system", async () => {
    await render(<Screen />);
    await fireEvent.press(screen.getByRole("button", { name: "Ahora no" }));
    await waitFor(() => expect(mockBack).toHaveBeenCalled());
    expect(mockEnable).not.toHaveBeenCalled();
  });
});
