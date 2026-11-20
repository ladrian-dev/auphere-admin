import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { FORGOT_EMAIL_KEY } from "../forgot/handoff";
import { LoginForm } from "../login/login-form";

vi.mock("@/lib/auth-actions", () => ({ signInAction: vi.fn() }));
vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }) }));
vi.mock("next/link", () => ({
  default: ({ href, children, onClick, ...rest }: { href: string; children: React.ReactNode; onClick?: (e: unknown) => void }) => (
    <a
      href={href}
      onClick={(e) => {
        e.preventDefault();
        onClick?.(e);
      }}
      {...rest}
    >
      {children}
    </a>
  ),
}));

function mount() {
  return render(
    <LocaleProvider locale="es">
      <LoginForm redirectTo="/" />
    </LocaleProvider>,
  );
}

afterEach(() => sessionStorage.clear());

describe("Entrar (spec 066, R4.1–R4.3)", () => {
  it("mostrar/ocultar cambia el campo y dice su estado (R4.1)", () => {
    const { container } = mount();
    const input = container.querySelector('input[autocomplete="current-password"]') as HTMLInputElement;
    expect(input.type).toBe("password");
    const toggle = screen.getByRole("button", { name: "Mostrar contraseña" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(toggle);
    expect(input.type).toBe("text");
    expect(screen.getByRole("button", { name: "Ocultar contraseña" })).toHaveAttribute("aria-pressed", "true");
  });

  it("el botón de mostrar no se confunde con «Entrar»", () => {
    mount();
    expect(screen.getAllByRole("button", { name: /entrar/i })).toHaveLength(1);
  });

  it("el correo escrito pasa a Recuperar por sessionStorage, no por la URL (R4.3)", () => {
    mount();
    fireEvent.change(screen.getByRole("textbox", { name: "Correo" }), { target: { value: "ana@agencia.com" } });
    const link = screen.getByRole("link", { name: /olvidado/i });
    expect(link.getAttribute("href")).toBe("/forgot");
    fireEvent.click(link);
    expect(sessionStorage.getItem(FORGOT_EMAIL_KEY)).toBe("ana@agencia.com");
  });

  it("sin correo escrito no deja nada guardado", () => {
    sessionStorage.setItem(FORGOT_EMAIL_KEY, "viejo@x.com");
    mount();
    fireEvent.click(screen.getByRole("link", { name: /olvidado/i }));
    expect(sessionStorage.getItem(FORGOT_EMAIL_KEY)).toBeNull();
  });
});
