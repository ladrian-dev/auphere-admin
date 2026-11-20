import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { FinishForm } from "../signup/[token]/finish-form";

const completeSignupAction = vi.fn();
vi.mock("@/lib/auth-actions", () => ({ completeSignupAction: (...a: unknown[]) => completeSignupAction(...a) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));
const router = vi.hoisted(() => ({ replace: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

function mount() {
  const r = render(
    <LocaleProvider locale="es">
      <FinishForm token="tok_abcdefghijklmnop" email="ana@agencia.com" />
    </LocaleProvider>,
  );
  return { ...r, pw: r.container.querySelector('input[autocomplete="new-password"]') as HTMLInputElement };
}

afterEach(() => vi.clearAllMocks());

describe("Terminar la cuenta (spec 067, R4)", () => {
  it("el correo verificado se lee como texto, no como campo deshabilitado (R4.2)", () => {
    const { container } = mount();
    expect(screen.getByTestId("signup-email")).toHaveTextContent("ana@agencia.com");
    expect(screen.getByText("Correo verificado")).toBeInTheDocument();
    expect(container.querySelector("input[disabled]")).toBeNull();
  });

  it("la regla de los 12 caracteres se marca mientras se escribe, y mostrar/ocultar funciona (R4.3)", async () => {
    const { pw } = mount();
    const rule = () => screen.getByText(/12 caracteres o más/).closest("li")!;
    expect(rule()).not.toHaveAttribute("data-ok");
    fireEvent.change(pw, { target: { value: "Auphere2026!" } });
    await waitFor(() => expect(rule()).toHaveAttribute("data-ok"));
    fireEvent.click(screen.getByRole("button", { name: "Mostrar contraseña" }));
    expect(pw.type).toBe("text");
  });

  it("sin empresa, el error va en su campo y el foco también (R4.4)", async () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Crear mi cuenta" }));
    const company = screen.getByRole("textbox", { name: "Nombre de la empresa" });
    await waitFor(() => expect(document.activeElement).toBe(company));
    expect(completeSignupAction).not.toHaveBeenCalled();
  });

  it("al terminar entra en la consola sin mandar el correo (R4.2, R4.5)", async () => {
    completeSignupAction.mockResolvedValue({ ok: true, partnerSlug: "agencia" });
    const { pw } = mount();
    fireEvent.change(screen.getByRole("textbox", { name: "Nombre de la empresa" }), { target: { value: "Agencia Sol" } });
    fireEvent.change(pw, { target: { value: "Auphere2026!" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear mi cuenta" }));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/"));
    const sent = completeSignupAction.mock.calls[0]![0] as Record<string, unknown>;
    expect(sent).toMatchObject({ token: "tok_abcdefghijklmnop", company_name: "Agencia Sol", password: "Auphere2026!" });
    expect(sent).not.toHaveProperty("email");
  });
});
