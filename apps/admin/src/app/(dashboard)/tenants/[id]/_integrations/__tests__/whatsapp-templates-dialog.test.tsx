import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WhatsAppTemplatesDialog } from "../whatsapp-templates-dialog";
import { isSpanishTemplate, otpPreview } from "../otp-template";

const create = vi.fn();
vi.mock("../setup-actions", () => ({
  listWhatsAppTemplatesAction: () => Promise.resolve({ ok: true, data: { templates: [], waba_id: "w1" } }),
  createWhatsAppTemplateAction: (...args: unknown[]) => create(...args),
  deleteWhatsAppTemplateAction: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

async function openForm() {
  const user = userEvent.setup();
  render(<WhatsAppTemplatesDialog tenantId="t1" />);
  await user.click(screen.getByRole("button", { name: "Plantillas" }));
  await user.click(await screen.findByRole("button", { name: "Nueva plantilla" }));
  await user.type(screen.getByLabelText("Nombre"), "tecfin_codigo");
  return user;
}

describe("templates dialog (spec 077, 3.1–3.3)", () => {
  beforeEach(() => {
    create.mockReset();
    create.mockResolvedValue({ ok: true, data: { id: "1", name: "tecfin_codigo", status: "PENDING", category: "AUTHENTICATION", audit_log_id: "a" } });
  });

  it("Utilidad sends exactly what it sent before", async () => {
    const user = await openForm();
    await user.type(screen.getByLabelText("Texto del mensaje"), "Tu pedido sale hoy.");
    await user.click(screen.getByRole("button", { name: "Enviar a revisión" }));
    expect(create).toHaveBeenCalledWith("t1", {
      name: "tecfin_codigo",
      language: "es",
      category: "UTILITY",
      components: [{ type: "BODY", text: "Tu pedido sale hoy." }],
    });
  });

  it("Autenticación asks for the button, the expiry and the security notice instead of the text, and sends `otp`", async () => {
    const user = await openForm();
    await user.selectOptions(screen.getByLabelText("Categoría"), "AUTHENTICATION");
    expect(screen.queryByLabelText("Texto del mensaje")).toBeNull();
    expect(screen.getByLabelText("Texto del botón")).toHaveValue("Copiar código");
    expect(screen.getByText(/es tu código de verificación\. Por tu seguridad, no lo compartas\./)).toBeInTheDocument();
    expect(screen.getByText("Este código caduca en 10 minutos.")).toBeInTheDocument();

    await user.click(screen.getByLabelText("Aviso de seguridad"));
    expect(screen.queryByText(/Por tu seguridad/)).toBeNull();
    await user.clear(screen.getByLabelText("Caduca en (min)"));
    await user.type(screen.getByLabelText("Caduca en (min)"), "5");

    await user.click(screen.getByRole("button", { name: "Enviar a revisión" }));
    expect(create).toHaveBeenCalledWith("t1", {
      name: "tecfin_codigo",
      language: "es",
      category: "AUTHENTICATION",
      otp: { button_text: "Copiar código", code_expiration_minutes: 5, add_security_recommendation: false },
    });
    // Never free text: Meta refuses it for this category.
    expect(create.mock.calls[0]![1]).not.toHaveProperty("components");
  });

  it("previews Meta's fixed text only for a Spanish template; for another language it says Meta writes it", async () => {
    const user = await openForm();
    await user.selectOptions(screen.getByLabelText("Categoría"), "AUTHENTICATION");
    expect(screen.getByText("Vista previa en español")).toBeInTheDocument();
    expect(screen.queryByText("Texto fijo de Meta")).toBeNull();

    await user.clear(screen.getByLabelText("Idioma"));
    await user.type(screen.getByLabelText("Idioma"), "en_US");
    expect(screen.queryByText("Vista previa en español")).toBeNull();
    expect(screen.queryByText(/es tu código de verificación/)).toBeNull();
    expect(screen.getByText(/Meta pone el texto fijo en el idioma de la plantilla/)).toHaveTextContent("(en_US)");

    await user.clear(screen.getByLabelText("Idioma"));
    await user.type(screen.getByLabelText("Idioma"), "es_CL");
    expect(screen.getByText("Vista previa en español")).toBeInTheDocument();
  });

  it("refuses an expiry outside 1–90 before calling the API", async () => {
    const user = await openForm();
    await user.selectOptions(screen.getByLabelText("Categoría"), "AUTHENTICATION");
    await user.clear(screen.getByLabelText("Caduca en (min)"));
    await user.type(screen.getByLabelText("Caduca en (min)"), "120");
    expect(screen.getByLabelText("Caduca en (min)")).toHaveAttribute("aria-invalid", "true");
    await user.click(screen.getByRole("button", { name: "Enviar a revisión" }));
    expect(create).not.toHaveBeenCalled();
  });
});

describe("Meta's fixed text", () => {
  it("is Spanish, so it stands only for a template in Spanish", () => {
    expect(isSpanishTemplate("es")).toBe(true);
    expect(isSpanishTemplate(" ES_mx ")).toBe(true);
    expect(isSpanishTemplate("en_US")).toBe(false);
    expect(isSpanishTemplate("pt_BR")).toBe(false);
    expect(isSpanishTemplate("")).toBe(false);
  });

  it("follows the fields: no expiry line without minutes", () => {
    expect(otpPreview({ buttonText: "", minutes: "", security: true })).toEqual({
      body: "123456 es tu código de verificación. Por tu seguridad, no lo compartas.",
      footer: null,
      button: "Copiar código",
    });
    expect(otpPreview({ buttonText: "Copiar", minutes: "1", security: false }).footer).toBe("Este código caduca en 1 minuto.");
  });
});
