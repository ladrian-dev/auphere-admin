import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { ResetForm } from "../reset/[token]/reset-form";

const finishPasswordResetAction = vi.fn();
vi.mock("@/lib/auth-actions", () => ({
  finishPasswordResetAction: (...a: unknown[]) => finishPasswordResetAction(...a),
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));
vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a> }));

function mount() {
  const r = render(
    <LocaleProvider locale="es">
      <ResetForm token="tok_abcdefghijklmnop" />
    </LocaleProvider>,
  );
  const [pw, confirm] = Array.from(r.container.querySelectorAll('input[autocomplete="new-password"]')) as HTMLInputElement[];
  return { ...r, pw: pw!, confirm: confirm! };
}

function rule(name: RegExp) {
  return screen.getByText(name).closest("li")!;
}

afterEach(() => vi.clearAllMocks());

describe("Contraseña nueva (spec 066, R5)", () => {
  it("las dos reglas se marcan mientras se escribe (R5.2)", async () => {
    const { pw, confirm } = mount();
    expect(rule(/12 caracteres o más/)).not.toHaveAttribute("data-ok");
    fireEvent.change(pw, { target: { value: "Auphere2026!" } });
    await waitFor(() => expect(rule(/12 caracteres o más/)).toHaveAttribute("data-ok"));
    expect(rule(/Las dos coinciden/)).not.toHaveAttribute("data-ok");
    fireEvent.change(confirm, { target: { value: "Auphere2026!" } });
    await waitFor(() => expect(rule(/Las dos coinciden/)).toHaveAttribute("data-ok"));
    // Nunca solo color: el estado también se dice en texto.
    expect(rule(/Las dos coinciden/)).toHaveTextContent("cumplida");
  });

  it("si no coinciden, el error va en «Repítela» y el foco también (R5.3)", async () => {
    const { pw, confirm } = mount();
    fireEvent.change(pw, { target: { value: "Auphere2026!" } });
    fireEvent.change(confirm, { target: { value: "Auphere2025!" } });
    fireEvent.click(screen.getByRole("button", { name: "Cambiar la contraseña" }));
    expect(await screen.findByText("Las dos no coinciden.")).toBeInTheDocument();
    await waitFor(() => expect(document.activeElement).toBe(confirm));
    expect(finishPasswordResetAction).not.toHaveBeenCalled();
  });

  it("un solo botón muestra u oculta las dos (R5.1)", () => {
    const { pw, confirm } = mount();
    fireEvent.click(screen.getByRole("button", { name: "Mostrar las contraseñas" }));
    expect(pw.type).toBe("text");
    expect(confirm.type).toBe("text");
  });

  it("el aviso de que te deja fuera va antes del botón (spec 011, R3.6)", () => {
    const { container } = mount();
    const warning = screen.getByText("Esto te deja fuera de todas partes");
    const button = screen.getByRole("button", { name: "Cambiar la contraseña" });
    const nodes = Array.from(container.querySelectorAll("*"));
    expect(nodes.indexOf(warning)).toBeLessThan(nodes.indexOf(button));
  });

  it("al terminar manda a Entrar y no abre sesión (spec 011, D-5)", async () => {
    finishPasswordResetAction.mockResolvedValue({ ok: true });
    const { pw, confirm } = mount();
    fireEvent.change(pw, { target: { value: "Auphere2026!" } });
    fireEvent.change(confirm, { target: { value: "Auphere2026!" } });
    fireEvent.click(screen.getByRole("button", { name: "Cambiar la contraseña" }));
    expect(await screen.findByText("Contraseña cambiada")).toBeInTheDocument();
    expect(finishPasswordResetAction).toHaveBeenCalledWith({ token: "tok_abcdefghijklmnop", password: "Auphere2026!" });
    expect(screen.getByRole("link", { name: "Volver a la entrada" })).toHaveAttribute("href", "/login");
  });
});
