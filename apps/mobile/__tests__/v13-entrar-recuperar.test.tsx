import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";

/**
 * Spec 069 (R6.1–R6.3; design §3.2): «Contraseña nueva» says where the link
 * went, lets the address be changed, and offers another link after 30 s with
 * the countdown in sight — saying the same whether or not the account exists
 * (spec 011, R1.3).
 */
const mockReset = jest.fn(async (_email: string) => undefined);
const mockBack = jest.fn();
let mockOnline = true;
let mockParams: { email?: string } = {};

jest.mock("@/ui/online", () => ({ useOnline: () => mockOnline }));
jest.mock("@/api/endpoints", () => ({ endpoints: { passwordReset: (email: string) => mockReset(email) } }));
jest.mock("expo-router", () => ({ router: { back: () => mockBack(), push: jest.fn(), replace: jest.fn() }, useLocalSearchParams: () => mockParams }));
jest.mock("expo-image", () => ({ Image: () => null }));

const Forgot = require("@/app/forgot-password").default;

beforeEach(() => {
  mockReset.mockReset();
  mockReset.mockImplementation(async () => undefined);
  mockBack.mockReset();
  mockOnline = true;
  mockParams = { email: "valeria@flor.test" };
  jest.useFakeTimers();
});
afterEach(() => {
  jest.useRealTimers();
});

async function send() {
  await fireEvent.press(screen.getByRole("button", { name: "Enviar el enlace" }));
  await waitFor(() => expect(screen.getByRole("header", { name: "Revisa tu correo" })).toBeTruthy());
}

describe("asking for the link", () => {
  it("starts with the email Entrar carried, says what happens meanwhile, and can go back", async () => {
    await render(<Forgot />);
    expect(screen.getByRole("header", { name: "Crea una contraseña nueva" })).toBeTruthy();
    expect(screen.getByText("Te enviaremos un enlace para crearla. Tus conversaciones siguen atendidas mientras tanto.")).toBeTruthy();
    expect(screen.getByLabelText("Correo").props.value).toBe("valeria@flor.test");
    await fireEvent.press(screen.getByRole("button", { name: "Atrás" }));
    expect(mockBack).toHaveBeenCalled();
  });

  it("the missing email is said under the field, after trying", async () => {
    mockParams = {};
    await render(<Forgot />);
    expect(screen.queryByText("Escribe tu correo.")).toBeNull();
    await fireEvent.press(screen.getByRole("button", { name: "Enviar el enlace" }));
    expect(mockReset).not.toHaveBeenCalled();
    expect(screen.getByText("Escribe tu correo.")).toBeTruthy();
    expect(screen.getByLabelText("Correo").props.accessibilityHint).toBe("Escribe tu correo.");
  });

  it("without a connection it says so and sends nothing", async () => {
    mockOnline = false;
    await render(<Forgot />);
    await fireEvent.press(screen.getByRole("button", { name: "Enviar el enlace" }));
    expect(mockReset).not.toHaveBeenCalled();
    expect(screen.getByText("No hay conexión. Conéctate a internet para entrar.")).toBeTruthy();
  });

  it("a failure keeps the form and says to try again", async () => {
    mockReset.mockRejectedValueOnce(new Error("500"));
    await render(<Forgot />);
    await fireEvent.press(screen.getByRole("button", { name: "Enviar el enlace" }));
    await waitFor(() => expect(screen.getByText("No pudimos enviarlo. Inténtalo de nuevo.")).toBeTruthy());
    expect(screen.queryByRole("header", { name: "Revisa tu correo" })).toBeNull();
  });
});

describe("«Revisa tu correo» (R6.1)", () => {
  it("shows the address written, what comes next and whom to ask", async () => {
    await render(<Forgot />);
    await send();
    expect(mockReset).toHaveBeenCalledWith("valeria@flor.test");
    expect(screen.getByLabelText("Correo: valeria@flor.test")).toBeTruthy();
    expect(screen.getByText("Abre el correo de Auphere")).toBeTruthy();
    // The link's life is the API's (services/password_reset.py, RESET_TTL), not the demo's 30 minutes.
    expect(screen.getByText("El enlace dura una hora.")).toBeTruthy();
    expect(screen.getByText(/pídeselo a quien gestiona tu negocio en Auphere/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Volver a entrar" })).toBeTruthy();
  });

  it("the screen reader reads each step with its hint, not only «Qué sigue» (review H12, WCAG 1.3.1)", async () => {
    await render(<Forgot />);
    await send();
    expect(screen.getByLabelText("Paso 1: Abre el correo de Auphere")).toBeTruthy();
    expect(screen.getByLabelText("Paso 2: Abre el enlace y crea la contraseña. El enlace dura una hora.")).toBeTruthy();
    expect(screen.getByLabelText("Paso 3: Vuelve aquí y entra. Tus conversaciones siguen atendidas mientras tanto.")).toBeTruthy();
    expect(screen.queryByLabelText("Qué sigue")).toBeNull();
  });

  it("«Cambiar» goes back to the form with the address, to fix it", async () => {
    await render(<Forgot />);
    await send();
    await fireEvent.press(screen.getByRole("button", { name: "Usar otro correo" }));
    expect(screen.getByRole("header", { name: "Crea una contraseña nueva" })).toBeTruthy();
    expect(screen.getByLabelText("Correo").props.value).toBe("valeria@flor.test");
  });

  it("the same words whether or not the account exists (R6.3)", async () => {
    const said = async (email: string) => {
      mockParams = { email };
      const view = await render(<Forgot />);
      await send();
      const text = screen
        .getAllByText(/.+/)
        .map((n) => String(n.props.children))
        .join(" | ")
        .replaceAll(email, "<correo>");
      await view.unmount();
      return text;
    };
    const known = await said("valeria@flor.test");
    const unknown = await said("nadie@ninguna.test");
    expect(unknown).toBe(known);
    expect(known).toContain("Si ese correo tiene acceso, te hemos enviado un enlace");
  });
});

describe("another link, after 30 s (R6.2)", () => {
  it("counts down in sight, then sends again and starts over", async () => {
    await render(<Forgot />);
    await send();
    const wait = screen.getByRole("button", { name: "Reenviar en 0:30" });
    expect(wait.props.accessibilityState).toEqual(expect.objectContaining({ disabled: true }));
    await act(() => jest.advanceTimersByTime(10_000));
    expect(screen.getByRole("button", { name: "Reenviar en 0:20" })).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Reenviar en 0:20" }));
    expect(mockReset).toHaveBeenCalledTimes(1);
    await act(() => jest.advanceTimersByTime(20_000));
    const again = screen.getByRole("button", { name: "Reenviar el enlace" });
    expect(again.props.accessibilityState).toEqual(expect.objectContaining({ disabled: false }));
    await fireEvent.press(again);
    await waitFor(() => expect(mockReset).toHaveBeenCalledTimes(2));
    expect(screen.getByText("Listo. Si ese correo tiene acceso, te llegará otro enlace.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reenviar en 0:30" })).toBeTruthy();
  });
});
