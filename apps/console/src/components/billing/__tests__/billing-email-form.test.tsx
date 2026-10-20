/**
 * The partner sets its own billing e-mail (owner, 2026-10-20). The 3D Secure
 * notice goes there, so the screen no longer says «escríbenos».
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const setEmail = vi.fn();
vi.mock("@/app/(console)/billing/actions", () => ({
  setBillingEmailAction: (input: { billing_email: string | null }) => setEmail(input),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { toast } from "sonner";

import { LocaleProvider } from "@/i18n/client";

import { BillingEmailForm } from "../billing-email-form";

function paint(props: Partial<React.ComponentProps<typeof BillingEmailForm>> = {}) {
  return render(
    <LocaleProvider locale="es">
      <BillingEmailForm email={null} contactEmail="contacto@partner.example" canManage {...props} />
    </LocaleProvider>,
  );
}

describe("el correo de facturación", () => {
  beforeEach(() => {
    setEmail.mockReset();
    setEmail.mockResolvedValue({ ok: true, data: { billing_email: "facturas@partner.example" } });
  });

  it("vacío, dice adónde van hoy los avisos y no pide escribir a Auphere", () => {
    paint();
    expect(screen.getByText("No configurado. Los avisos van a contacto@partner.example.")).toBeInTheDocument();
    expect(screen.queryByText(/escríbenos/i)).toBeNull();
  });

  it("quien gestiona la facturación lo añade y se guarda", async () => {
    paint();
    await userEvent.click(screen.getByRole("button", { name: "Añadir" }));
    await userEvent.type(screen.getByLabelText("Correo de facturación"), "facturas@partner.example");
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(setEmail).toHaveBeenCalledWith({ billing_email: "facturas@partner.example" }));
    expect(toast.success).toHaveBeenCalled();
  });

  it("un correo mal escrito se para en la pantalla", async () => {
    paint({ email: "viejo@partner.example" });
    await userEvent.click(screen.getByRole("button", { name: "Cambiar" }));
    const input = screen.getByLabelText("Correo de facturación");
    await userEvent.clear(input);
    await userEvent.type(input, "no-es-correo");
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));
    expect(setEmail).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith("Escribe un correo válido.");
  });

  it("quien solo lo lee no ve el botón", () => {
    paint({ email: "facturas@partner.example", canManage: false });
    expect(screen.getByText("facturas@partner.example")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
