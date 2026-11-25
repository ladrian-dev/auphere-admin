import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { SIGNUP_RESEND_AFTER_S, SignupForm } from "../signup/signup-form";

const signUpAction = vi.fn();
vi.mock("@/lib/auth-actions", () => ({ signUpAction: (...a: unknown[]) => signUpAction(...a) }));
const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a> }));

const PAGE_LANG = "es" as const;

function mount(google: React.ReactNode = null) {
  return render(
    <LocaleProvider locale={PAGE_LANG}>
      <SignupForm google={google} />
    </LocaleProvider>,
  );
}

async function send(email: string) {
  fireEvent.change(screen.getByRole("textbox", { name: "Correo de trabajo" }), { target: { value: email } });
  fireEvent.click(screen.getByRole("button", { name: "Continuar" }));
  await screen.findByText("Revisa tu correo");
}

beforeEach(() => {
  signUpAction.mockReset();
  // Spec 006, R1.2: la acción contesta igual pueda registrarse o no.
  signUpAction.mockResolvedValue({ ok: true });
});
afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("Crear cuenta (spec 067, R2–R3)", () => {
  it("el campo es «Correo de trabajo» con su ejemplo, y hay salida a Entrar (R2.3, R2.4)", () => {
    mount();
    const input = screen.getByRole("textbox", { name: "Correo de trabajo" });
    expect(input).toHaveAttribute("placeholder", "nombre@agencia.com");
    expect(input).toHaveAttribute("inputmode", "email");
    expect(screen.getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", "/login");
  });

  it("Google va encima y se va con el formulario al «enviado» (R2.2)", async () => {
    mount(<button type="button">Registrarte con Google</button>);
    expect(screen.getByRole("button", { name: "Registrarte con Google" })).toBeInTheDocument();
    await send("ana@agencia.com");
    expect(screen.queryByRole("button", { name: "Registrarte con Google" })).toBeNull();
  });

  it("«enviado» repite el correo escrito y pide el alta en el idioma de la página (R3.1)", async () => {
    mount();
    await send("ana@agencia.com");
    expect(screen.getByTestId("signup-sent-body")).toHaveTextContent("Si ana@agencia.com puede registrarse, ya tiene un enlace esperando.");
    // El idioma sale del LocaleProvider de la página, no de un literal.
    expect(signUpAction.mock.calls[0]![0]).toMatchObject({ email: "ana@agencia.com" });
    expect((signUpAction.mock.calls[0]![0] as { locale: string }).locale).toBe(PAGE_LANG);
  });

  it("la pantalla es la misma para cualquier dirección: el oráculo sigue cerrado (spec 006, R1.2)", async () => {
    const a = mount();
    await send("ya-tiene@agencia.com");
    const one = a.container.innerHTML.replaceAll("ya-tiene@agencia.com", "X");
    a.unmount();
    const b = mount();
    await send("nueva@agencia.com");
    expect(b.container.innerHTML.replaceAll("nueva@agencia.com", "X")).toBe(one);
  });

  it("«Usar otro correo» vuelve al formulario con el correo puesto (R3.3)", async () => {
    mount();
    await send("ana@agencia.con");
    fireEvent.click(screen.getByRole("button", { name: "Usar otro correo" }));
    expect(screen.getByRole("textbox", { name: "Correo de trabajo" })).toHaveValue("ana@agencia.con");
  });

  it("«Reenviar» espera 30 s y vuelve a pedir; la cuenta atrás no se anuncia (R3.4, R3.5)", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mount();
    await send("ana@agencia.com");
    expect(await screen.findByRole("button", { name: /^Reenviar en \d+ s$/ })).toBeDisabled();
    expect(screen.getByRole("status")).not.toHaveTextContent(/Reenviar/);
    for (let i = 0; i < SIGNUP_RESEND_AFTER_S; i++) {
      await act(async () => {
        vi.advanceTimersByTime(1000);
      });
    }
    fireEvent.click(screen.getByRole("button", { name: "Reenviar el enlace" }));
    await waitFor(() => expect(signUpAction).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it("demasiadas solicitudes se dice como hoy (R3.4)", async () => {
    signUpAction.mockResolvedValue({ ok: false, reason: "rate_limited" });
    mount();
    fireEvent.change(screen.getByRole("textbox", { name: "Correo de trabajo" }), { target: { value: "ana@agencia.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Continuar" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Demasiadas solicitudes. Prueba dentro de un minuto."));
    expect(screen.queryByText("Revisa tu correo")).toBeNull();
  });
});
