import { createHash } from "node:crypto";

import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";

import { createPkce } from "@/auth/pkce";
import { googleUrl, readCallback, outcomeOfError } from "@/auth/sign-in";

/**
 * Spec 031 (T118, R1 enmendado el 2026-10-20): the app's own way in — email
 * and password, or Google — and what each way back says. Nothing of the
 * partner console.
 */
const mockSession = {
  state: { status: "signed-out", closedReason: null as string | null },
  signInWithPassword: jest.fn(),
  signInWithGoogle: jest.fn(),
  signOut: jest.fn(),
};
const mockPush = jest.fn();
const mockReplace = jest.fn();
const mockReset = jest.fn(async (_email: string) => undefined);
let mockOnline = true;
let mockGoogle = true;

jest.mock("@/auth/session", () => ({ useSession: () => mockSession }));
jest.mock("@/ui/online", () => ({ useOnline: () => mockOnline }));
jest.mock("@/api/hooks", () => ({ useAppConfig: () => ({ data: { sign_in: { google: mockGoogle } } }) }));
jest.mock("@/api/endpoints", () => ({ endpoints: { passwordReset: (email: string) => mockReset(email) } }));
jest.mock("expo-router", () => ({
  router: { push: (...a: unknown[]) => mockPush(...a), replace: (...a: unknown[]) => mockReplace(...a), back: jest.fn() },
  useLocalSearchParams: () => ({}),
}));
jest.mock("expo-image", () => ({ Image: () => null }));
jest.mock("expo-web-browser", () => ({ openBrowserAsync: jest.fn(), openAuthSessionAsync: jest.fn() }));

const b64url = (buf: Buffer) => buf.toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

describe("Google's way there and back", () => {
  it("is S256 over a 43-char base64url verifier, with a random state", async () => {
    const a = await createPkce();
    const b = await createPkce();
    expect(a.verifier).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(a.challenge).toBe(b64url(createHash("sha256").update(a.verifier).digest()));
    expect(a.state).not.toBe(b.state);
  });

  it("goes to the API, never to the console, with the challenge and the state", () => {
    const url = new URL(googleUrl({ challenge: "c".repeat(43), state: "s".repeat(22) }));
    expect(url.pathname).toBe("/app/sign-in/google");
    expect(url.searchParams.get("code_challenge")).toBe("c".repeat(43));
    expect(url.searchParams.get("state")).toBe("s".repeat(22));
    expect(url.href).not.toContain("app-auth");
  });

  it("rejects a return with another state", () => {
    expect(readCallback("auphere-customers://auth/callback?code=AB12CD34&state=other", "mine")).toEqual({ error: "state_mismatch" });
    expect(readCallback("auphere-customers://auth/callback?code=AB12CD34&state=mine", "mine")).toEqual({ code: "AB12CD34" });
    expect(readCallback("auphere-customers://auth/callback?error=google_account_mismatch&state=mine", "mine")).toEqual({
      error: "google_account_mismatch",
    });
  });

  it("each refusal from the API has its own outcome", () => {
    expect(outcomeOfError("invalid_credentials")).toEqual({ kind: "invalid-credentials" });
    expect(outcomeOfError("google_account_mismatch")).toEqual({ kind: "google-mismatch" });
    expect(outcomeOfError("email_not_verified")).toEqual({ kind: "google-mismatch" });
    expect(outcomeOfError("not_a_client")).toEqual({ kind: "not-a-client" });
    expect(outcomeOfError("no_access")).toEqual({ kind: "no-access" });
    expect(outcomeOfError("cancelled")).toEqual({ kind: "cancelled" });
    expect(outcomeOfError("google_unavailable")).toEqual({ kind: "google-unavailable" });
    expect(outcomeOfError("anything else")).toEqual({ kind: "failed" });
  });
});

describe("«Entrar»", () => {
  const SignIn = require("@/app/sign-in").default;
  beforeEach(() => {
    mockSession.signInWithPassword.mockReset();
    mockSession.signInWithGoogle.mockReset();
    mockSession.state = { status: "signed-out", closedReason: null };
    mockPush.mockReset();
    mockOnline = true;
    mockGoogle = true;
  });

  async function fill(email: string, password: string) {
    await fireEvent.changeText(screen.getByLabelText("Correo"), email);
    await fireEvent.changeText(screen.getByLabelText("Contraseña"), password);
  }

  it("asks for the email and password the system can fill, and never mentions the partner console", async () => {
    await render(<SignIn />);
    const email = screen.getByLabelText("Correo");
    const password = screen.getByLabelText("Contraseña");
    expect(email.props.autoComplete).toBe("email");
    expect(email.props.textContentType).toBe("username");
    expect(email.props.keyboardType).toBe("email-address");
    expect(password.props.autoComplete).toBe("current-password");
    expect(password.props.textContentType).toBe("password");
    expect(password.props.secureTextEntry).toBe(true);
    expect(screen.queryByText(/partner/i)).toBeNull();
    expect(screen.queryByText(/consola de partners/i)).toBeNull();
  });

  it("shows and hides the password", async () => {
    await render(<SignIn />);
    await fireEvent.press(screen.getByRole("button", { name: "Mostrar la contraseña" }));
    expect(screen.getByLabelText("Contraseña").props.secureTextEntry).toBe(false);
    await fireEvent.press(screen.getByRole("button", { name: "Ocultar la contraseña" }));
    expect(screen.getByLabelText("Contraseña").props.secureTextEntry).toBe(true);
  });

  it("does not try without both fields, and says what is missing", async () => {
    await render(<SignIn />);
    await fill("valeria@flor.test", "");
    await fireEvent.press(screen.getByRole("button", { name: "Entrar" }));
    expect(mockSession.signInWithPassword).not.toHaveBeenCalled();
    expect(screen.getByText("Escribe tu correo y tu contraseña.")).toBeTruthy();
  });

  it("signs in with what was written, trimmed", async () => {
    mockSession.signInWithPassword.mockResolvedValue({ kind: "ok" });
    await render(<SignIn />);
    await fill("  valeria@flor.test ", "secreta");
    await fireEvent.press(screen.getByRole("button", { name: "Entrar" }));
    await waitFor(() => expect(mockSession.signInWithPassword).toHaveBeenCalledWith("valeria@flor.test", "secreta"));
  });

  it("a wrong email or password says so without saying which", async () => {
    mockSession.signInWithPassword.mockResolvedValue({ kind: "invalid-credentials" });
    await render(<SignIn />);
    await fill("valeria@flor.test", "mala");
    await fireEvent.press(screen.getByRole("button", { name: "Entrar" }));
    await waitFor(() => expect(screen.getByText("El correo o la contraseña no son correctos.")).toBeTruthy());
  });

  it("too many attempts ask to wait", async () => {
    mockSession.signInWithPassword.mockResolvedValue({ kind: "rate-limited" });
    await render(<SignIn />);
    await fill("valeria@flor.test", "mala");
    await fireEvent.press(screen.getByRole("button", { name: "Entrar" }));
    await waitFor(() => expect(screen.getByText("Demasiados intentos. Espera un minuto y vuelve a probar.")).toBeTruthy());
  });

  it("a partner member goes to R1.5, a business without access to R1.6", async () => {
    mockSession.signInWithPassword.mockResolvedValueOnce({ kind: "not-a-client" }).mockResolvedValueOnce({ kind: "no-access" });
    await render(<SignIn />);
    await fill("socia@partner.test", "secreta");
    await fireEvent.press(screen.getByRole("button", { name: "Entrar" }));
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/not-a-client"));
    await fireEvent.press(screen.getByRole("button", { name: "Entrar" }));
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/no-access"));
  });

  it("Google with another email's account says to use the right one, and keeps the password", async () => {
    mockSession.signInWithGoogle.mockResolvedValue({ kind: "google-mismatch" });
    await render(<SignIn />);
    await fireEvent.press(screen.getByRole("button", { name: "Continuar con Google" }));
    await waitFor(() =>
      expect(screen.getByText(/Esa cuenta de Google no es la del correo con el que Auphere te dio acceso/)).toBeTruthy(),
    );
    expect(screen.getByLabelText("Contraseña")).toBeTruthy();
  });

  it("a cancelled Google window comes back saying so", async () => {
    mockSession.signInWithGoogle.mockResolvedValue({ kind: "cancelled" });
    await render(<SignIn />);
    await fireEvent.press(screen.getByRole("button", { name: "Continuar con Google" }));
    await waitFor(() => expect(screen.getByText("No terminaste de entrar. Vuelve a intentarlo cuando quieras.")).toBeTruthy());
  });

  it("without Google on the API there is no Google button", async () => {
    mockGoogle = false;
    await render(<SignIn />);
    expect(screen.queryByRole("button", { name: "Continuar con Google" })).toBeNull();
  });

  it("offline, it says so and tries nothing", async () => {
    mockOnline = false;
    await render(<SignIn />);
    expect(screen.getByText("No hay conexión. Conéctate a internet para entrar.")).toBeTruthy();
    await fill("valeria@flor.test", "secreta");
    await fireEvent.press(screen.getByRole("button", { name: "Entrar" }));
    expect(mockSession.signInWithPassword).not.toHaveBeenCalled();
  });

  it("a closed session lands here with its reason (R7.2)", async () => {
    mockSession.state = { status: "signed-out", closedReason: "closed_by_person" };
    await render(<SignIn />);
    expect(screen.getByText("Cerraste la sesión de este teléfono desde la consola.")).toBeTruthy();
  });

  it("«¿Olvidaste tu contraseña?» carries the email written so far", async () => {
    await render(<SignIn />);
    await fill("valeria@flor.test", "");
    await fireEvent.press(screen.getByRole("button", { name: "¿Olvidaste tu contraseña?" }));
    expect(mockPush).toHaveBeenCalledWith({ pathname: "/forgot-password", params: { email: "valeria@flor.test" } });
  });
});

describe("«¿Olvidaste tu contraseña?» (R1.7)", () => {
  const Forgot = require("@/app/forgot-password").default;
  beforeEach(() => {
    mockReset.mockClear();
    mockOnline = true;
  });

  it("sends the link and says the same whether or not the email has access", async () => {
    await render(<Forgot />);
    await fireEvent.changeText(screen.getByLabelText("Correo"), " valeria@flor.test ");
    await fireEvent.press(screen.getByRole("button", { name: "Enviar el enlace" }));
    await waitFor(() => expect(mockReset).toHaveBeenCalledWith("valeria@flor.test"));
    expect(screen.getByText(/Si ese correo tiene acceso, te hemos enviado un enlace/)).toBeTruthy();
  });

  it("does not send without an email", async () => {
    await render(<Forgot />);
    await fireEvent.press(screen.getByRole("button", { name: "Enviar el enlace" }));
    expect(mockReset).not.toHaveBeenCalled();
    expect(screen.getByText("Escribe tu correo.")).toBeTruthy();
  });
});

describe("R1.5 and R1.6", () => {
  it("a partner member is told the app is not theirs, with no way into the partner console", async () => {
    const NotAClient = require("@/app/not-a-client").default;
    await render(<NotAClient />);
    expect(screen.getByText("Esta app es para los negocios que atiende Auphere")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Abrir la consola" })).toBeNull();
    expect(screen.getByRole("button", { name: "Entrar con otra cuenta" })).toBeTruthy();
  });

  it("no access says whom to ask", async () => {
    const NoAccess = require("@/app/no-access").default;
    await render(<NoAccess />);
    expect(screen.getByText(/Pide acceso a la persona que te invitó a la consola/)).toBeTruthy();
  });
});
