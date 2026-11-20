import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { RESEND_AFTER_S, ForgotForm } from "../forgot/forgot-form";
import { FORGOT_EMAIL_KEY } from "../forgot/handoff";

const requestPasswordResetAction = vi.fn();
vi.mock("@/lib/auth-actions", () => ({
  requestPasswordResetAction: (...a: unknown[]) => requestPasswordResetAction(...a),
}));
const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

function mount() {
  return render(
    <LocaleProvider locale="es">
      <ForgotForm />
    </LocaleProvider>,
  );
}

async function send(email: string) {
  fireEvent.change(screen.getByRole("textbox", { name: "Correo" }), { target: { value: email } });
  fireEvent.click(screen.getByRole("button", { name: "Mandarme el enlace" }));
  await screen.findByText("Mira tu correo");
}

beforeEach(() => {
  requestPasswordResetAction.mockReset();
  // Spec 011, R1.3: la acción contesta igual exista o no la cuenta.
  requestPasswordResetAction.mockResolvedValue({ ok: true });
});
afterEach(() => {
  sessionStorage.clear();
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("Recuperar la cuenta (spec 066, R4.3–R4.5)", () => {
  it("trae el correo que se escribió en Entrar y lo borra al leerlo (R4.3)", async () => {
    sessionStorage.setItem(FORGOT_EMAIL_KEY, "ana@agencia.com");
    mount();
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Correo" })).toHaveValue("ana@agencia.com"));
    expect(sessionStorage.getItem(FORGOT_EMAIL_KEY)).toBeNull();
  });

  it("«enviado» repite el correo escrito y nada más que eso (R4.4)", async () => {
    mount();
    await send("ana@agencia.com");
    expect(screen.getByTestId("forgot-sent-body")).toHaveTextContent(
      "Si ana@agencia.com tiene cuenta, ya tiene un enlace esperando.",
    );
    expect(requestPasswordResetAction).toHaveBeenCalledWith({ email: "ana@agencia.com" });
  });

  it("la pantalla es la misma para cualquier dirección: el oráculo sigue cerrado (spec 011, R1.3)", async () => {
    const a = mount();
    await send("tiene-cuenta@agencia.com");
    const one = a.container.innerHTML.replaceAll("tiene-cuenta@agencia.com", "X");
    a.unmount();
    const b = mount();
    await send("no-existe@agencia.com");
    const two = b.container.innerHTML.replaceAll("no-existe@agencia.com", "X");
    expect(two).toBe(one);
  });

  it("«Cambiar» vuelve al formulario con el correo puesto (R4.4)", async () => {
    mount();
    await send("ana@agencia.con");
    fireEvent.click(screen.getByRole("button", { name: "Cambiar el correo" }));
    expect(screen.getByRole("textbox", { name: "Correo" })).toHaveValue("ana@agencia.con");
  });

  it("«Reenviar» espera 30 s con la cuenta atrás a la vista y vuelve a pedir (R4.4, R4.5)", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mount();
    await send("ana@agencia.com");
    const btn = await screen.findByRole("button", { name: /^Reenviar en \d+ s$/ });
    expect(btn).toBeDisabled();
    expect(btn).toHaveTextContent(new RegExp(`Reenviar en (${RESEND_AFTER_S}|${RESEND_AFTER_S - 1}) s`));
    for (let i = 0; i < RESEND_AFTER_S; i++) {
      await act(async () => {
        vi.advanceTimersByTime(1000);
      });
    }
    const again = screen.getByRole("button", { name: "Reenviar el enlace" });
    expect(again).toBeEnabled();
    fireEvent.click(again);
    await waitFor(() => expect(requestPasswordResetAction).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Te mandamos otro enlace. El anterior deja de valer."));
    expect(await screen.findByRole("button", { name: /^Reenviar en \d+ s$/ })).toBeDisabled();
  });

  it("la cuenta atrás no está en la región que se anuncia", async () => {
    mount();
    await send("ana@agencia.com");
    expect(screen.getByRole("status")).not.toHaveTextContent(/Reenviar/);
  });
});
