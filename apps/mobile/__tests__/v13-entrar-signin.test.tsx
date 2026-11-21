import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";

/**
 * Spec 069 (R5.1, R5.4, R5.5, R1.4; Historia 7): «Entrar» on the living
 * liquid, with each field's error under it and only after the first attempt.
 * Everything Entrar did before stays (sign-in.test.tsx).
 */
const mockSession = {
  state: { status: "signed-out", closedReason: null as string | null },
  signInWithPassword: jest.fn(),
  signInWithGoogle: jest.fn(),
  signOut: jest.fn(),
};
const mockPush = jest.fn();
let mockOnline = true;
let mockGoogle = true;

jest.mock("@/auth/session", () => ({ useSession: () => mockSession }));
jest.mock("@/ui/online", () => ({ useOnline: () => mockOnline }));
jest.mock("@/api/hooks", () => ({ useAppConfig: () => ({ data: { sign_in: { google: mockGoogle } } }) }));
jest.mock("expo-router", () => ({ router: { push: (...a: unknown[]) => mockPush(...a), replace: jest.fn(), back: jest.fn() }, useLocalSearchParams: () => ({}) }));
jest.mock("expo-image", () => ({ Image: () => null }));
jest.mock("expo-web-browser", () => ({ openBrowserAsync: jest.fn(), openAuthSessionAsync: jest.fn() }));

const SignIn = require("@/app/sign-in").default;

beforeEach(() => {
  mockSession.signInWithPassword.mockReset();
  mockSession.signInWithGoogle.mockReset();
  mockSession.state = { status: "signed-out", closedReason: null };
  mockPush.mockReset();
  mockOnline = true;
  mockGoogle = true;
});

describe("Entrar, as the design draws it (R5.1)", () => {
  it("the brand, the headline in the display style, and the card with every way in", async () => {
    await render(<SignIn />);
    expect(screen.getByText("Auphere")).toBeTruthy();
    const headline = screen.getByRole("header", { name: "Tus clientes, siempre accesibles" });
    expect(headline.props.style).toEqual(expect.arrayContaining([expect.objectContaining({ fontSize: 28, lineHeight: 34, fontWeight: "600" })]));
    expect(screen.getByLabelText("Correo")).toBeTruthy();
    expect(screen.getByLabelText("Contraseña")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Mostrar la contraseña" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "¿Olvidaste tu contraseña?" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Entrar" })).toBeTruthy();
    // The «o» between the two ways is decoration for assistive tech: the two buttons say it all.
    expect(screen.getByText("o", { includeHiddenElements: true })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Continuar con Google" })).toBeTruthy();
  });

  it("the liquid is decoration: hidden from assistive tech and it never covers the form", async () => {
    await render(<SignIn />);
    const liquid = screen.getByTestId("liquid-ground", { includeHiddenElements: true });
    expect(liquid.props.accessible).toBe(false);
    expect(liquid.props.importantForAccessibility).toBe("no-hide-descendants");
    expect(liquid.props.pointerEvents).toBe("none");
    expect(screen.getByTestId("entry-card")).toBeTruthy();
  });
});

describe("each field says what is wrong, under it, after the first attempt (R5.4)", () => {
  it("nothing is flagged before trying", async () => {
    await render(<SignIn />);
    expect(screen.queryByText("Escribe tu contraseña.")).toBeNull();
    expect(screen.queryByText("Escribe el correo con el que entras a Auphere.")).toBeNull();
  });

  it("an empty password: «Escribe tu contraseña.», and no attempt (Historia 7, escenario 1)", async () => {
    await render(<SignIn />);
    await fireEvent.changeText(screen.getByLabelText("Correo"), "valeria@flor.test");
    await fireEvent.press(screen.getByRole("button", { name: "Entrar" }));
    expect(mockSession.signInWithPassword).not.toHaveBeenCalled();
    expect(screen.getByText("Escribe tu contraseña.")).toBeTruthy();
    expect(screen.queryByText("Escribe el correo con el que entras a Auphere.")).toBeNull();
    // The error is the field's: it names the problem next to it, and the field says it is wrong.
    expect(screen.getByLabelText("Contraseña").props.accessibilityHint).toBe("Escribe tu contraseña.");
  });

  it("an email that is not one is flagged on its own field", async () => {
    await render(<SignIn />);
    await fireEvent.changeText(screen.getByLabelText("Correo"), "valeria@flor");
    await fireEvent.changeText(screen.getByLabelText("Contraseña"), "secreta");
    await fireEvent.press(screen.getByRole("button", { name: "Entrar" }));
    expect(mockSession.signInWithPassword).not.toHaveBeenCalled();
    expect(screen.getByText("Escribe el correo con el que entras a Auphere.")).toBeTruthy();
    expect(screen.queryByText("Escribe tu contraseña.")).toBeNull();
  });

  it("after the first attempt the error follows what is typed, and goes when it is fixed", async () => {
    await render(<SignIn />);
    await fireEvent.press(screen.getByRole("button", { name: "Entrar" }));
    expect(screen.getByText("Escribe tu contraseña.")).toBeTruthy();
    expect(screen.getByText("Escribe el correo con el que entras a Auphere.")).toBeTruthy();
    await fireEvent.changeText(screen.getByLabelText("Contraseña"), "s");
    expect(screen.queryByText("Escribe tu contraseña.")).toBeNull();
    await fireEvent.changeText(screen.getByLabelText("Correo"), "valeria@flor.test");
    expect(screen.queryByText("Escribe el correo con el que entras a Auphere.")).toBeNull();
    mockSession.signInWithPassword.mockResolvedValue({ kind: "ok" });
    await fireEvent.press(screen.getByRole("button", { name: "Entrar" }));
    await waitFor(() => expect(mockSession.signInWithPassword).toHaveBeenCalledWith("valeria@flor.test", "s"));
  });
});

describe("without a connection (R5.5)", () => {
  it("the card says so in words, and nothing is tried", async () => {
    mockOnline = false;
    await render(<SignIn />);
    expect(screen.getByText("Sin conexión")).toBeTruthy();
    expect(screen.getByText("No hay conexión. Conéctate a internet para entrar.")).toBeTruthy();
    await fireEvent.changeText(screen.getByLabelText("Correo"), "valeria@flor.test");
    await fireEvent.changeText(screen.getByLabelText("Contraseña"), "secreta");
    await fireEvent.press(screen.getByRole("button", { name: "Entrar" }));
    await fireEvent.press(screen.getByRole("button", { name: "Continuar con Google" }));
    expect(mockSession.signInWithPassword).not.toHaveBeenCalled();
    expect(mockSession.signInWithGoogle).not.toHaveBeenCalled();
  });
});
