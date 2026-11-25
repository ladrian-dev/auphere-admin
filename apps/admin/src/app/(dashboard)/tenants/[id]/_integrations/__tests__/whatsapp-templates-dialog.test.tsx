import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WhatsAppTemplatesDialog } from "../whatsapp-templates-dialog";

/**
 * Spec 075, requisito 10 (D7, 2026-11-25): el panel crea con el mismo editor
 * que la consola (`TemplateEditor` de `@nexus/ui`), también las plantillas de
 * autenticación de la 077, y manda a la API la forma de la consola. Ningún
 * formulario propio.
 */

const create = vi.fn();
vi.mock("../setup-actions", () => ({
  listWhatsAppTemplatesAction: () => Promise.resolve({ ok: true, data: { templates: [], waba_id: "w1" } }),
  createWhatsAppTemplateAction: (...args: unknown[]) => create(...args),
  deleteWhatsAppTemplateAction: vi.fn(),
  editWhatsAppTemplateAction: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

async function openEditor() {
  const user = userEvent.setup();
  render(<WhatsAppTemplatesDialog tenantId="t1" />);
  await user.click(screen.getByRole("button", { name: "Plantillas" }));
  await user.click(await screen.findByRole("button", { name: "Nueva plantilla" }));
  const editor = await screen.findByRole("dialog", { name: "Nueva plantilla" });
  await user.type(within(editor).getByLabelText("Nombre"), "tecfin_codigo");
  return { user, editor };
}

const send = (editor: HTMLElement) => within(editor).getByRole("button", { name: "Enviar a Meta para revisión" });

describe("Nueva plantilla en el panel: el editor de la consola (spec 075, 10.1, 10.5)", () => {
  beforeEach(() => {
    create.mockReset();
    create.mockResolvedValue({ ok: true, data: { id: "1", name: "tecfin_codigo", status: "PENDING", category: "UTILITY", audit_log_id: "a" } });
  });

  it("opens the shared editor: the three categories, the whole message and the preview", async () => {
    const { editor } = await openEditor();
    expect(within(editor).getAllByRole("radio")).toHaveLength(3);
    expect(within(editor).getByRole("radio", { name: /Utilidad/ })).toBeChecked();
    expect(within(editor).getByLabelText("Encabezado (opcional)")).toBeInTheDocument();
    expect(within(editor).getByLabelText("Texto del mensaje")).toBeInTheDocument();
    expect(within(editor).getByLabelText("Pie (opcional)")).toBeInTheDocument();
    expect(within(editor).getByRole("button", { name: "Añadir botón" })).toBeInTheDocument();
    expect(within(editor).getByLabelText("Así lo verá el cliente")).toBeInTheDocument();
  });

  it("Utilidad sends the console's shape, not Meta's components", async () => {
    const { user, editor } = await openEditor();
    await user.type(within(editor).getByLabelText("Texto del mensaje"), "Tu pedido sale hoy.");
    await user.click(send(editor));
    await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
    expect(create).toHaveBeenCalledWith("t1", {
      name: "tecfin_codigo",
      language: "es",
      category: "UTILITY",
      body_text: "Tu pedido sale hoy.",
      buttons: [],
      examples: {},
    });
    expect(create.mock.calls[0]![1]).not.toHaveProperty("components");
  });

  it("Autenticación asks for the button, the expiry and the notice instead of the text, and sends otp_* only (077, 3.1)", async () => {
    const { user, editor } = await openEditor();
    await user.click(within(editor).getByRole("radio", { name: /Autenticación/ }));
    expect(within(editor).queryByLabelText("Texto del mensaje")).toBeNull();
    expect(within(editor).getByLabelText("Texto del botón")).toHaveValue("Copiar código");
    const preview = within(editor).getByLabelText("Así lo verá el cliente");
    expect(preview).toHaveTextContent("123456 es tu código de verificación. Por tu seguridad, no lo compartas.");
    expect(preview).toHaveTextContent("Este código caduca en 10 minutos.");

    await user.click(within(editor).getByLabelText(/Aviso de seguridad/));
    expect(preview).not.toHaveTextContent("Por tu seguridad");
    await user.clear(within(editor).getByLabelText("Caduca en (min)"));
    await user.type(within(editor).getByLabelText("Caduca en (min)"), "5");

    await user.click(send(editor));
    await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
    expect(create.mock.calls[0]).toStrictEqual([
      "t1",
      {
        name: "tecfin_codigo",
        language: "es",
        category: "AUTHENTICATION",
        otp_button_text: "Copiar código",
        otp_expiration_minutes: 5,
        otp_security_recommendation: false,
      },
    ]);
  });

  it("previews Meta's fixed text only for a Spanish template; for another language it says Meta writes it (10.3)", async () => {
    const { user, editor } = await openEditor();
    await user.click(within(editor).getByRole("radio", { name: /Autenticación/ }));
    const preview = within(editor).getByLabelText("Así lo verá el cliente");
    expect(preview).toHaveTextContent("Vista previa en español");
    await user.selectOptions(within(editor).getByLabelText("Idioma"), "en");
    expect(preview).not.toHaveTextContent("es tu código de verificación");
    expect(preview).toHaveTextContent("Meta pone el texto fijo en English, el idioma de la plantilla");
    await user.selectOptions(within(editor).getByLabelText("Idioma"), "es_CL");
    expect(preview).toHaveTextContent("Vista previa en español");
  });

  it("refuses an expiry outside 1–90 before calling the API", async () => {
    const { user, editor } = await openEditor();
    await user.click(within(editor).getByRole("radio", { name: /Autenticación/ }));
    await user.clear(within(editor).getByLabelText("Caduca en (min)"));
    await user.type(within(editor).getByLabelText("Caduca en (min)"), "120");
    expect(within(editor).getByLabelText("Caduca en (min)")).toHaveAttribute("aria-invalid", "true");
    await user.click(send(editor));
    expect(create).not.toHaveBeenCalled();
    expect(within(editor).getByText("Falta una caducidad de 1 a 90 minutos.")).toBeInTheDocument();
  });

  it("says Meta's refusal inside the editor and keeps what was written", async () => {
    create.mockResolvedValue({ ok: false, error: "Meta rechazó la creación: nombre en uso." });
    const { user, editor } = await openEditor();
    await user.type(within(editor).getByLabelText("Texto del mensaje"), "Tu pedido sale hoy.");
    await user.click(send(editor));
    expect(await within(editor).findByText("Meta rechazó la creación: nombre en uso.")).toBeInTheDocument();
    expect(within(editor).getByLabelText("Nombre")).toHaveValue("tecfin_codigo");
  });

  it("closes the editor once Meta takes it", async () => {
    const { user, editor } = await openEditor();
    await user.type(within(editor).getByLabelText("Texto del mensaje"), "Tu pedido sale hoy.");
    await user.click(send(editor));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Nueva plantilla" })).toBeNull());
  });
});

describe("createWhatsAppTemplateAction (10.5, 8.3)", () => {
  type Sent = { url: string; method: string; body: unknown };
  const sent: Sent[] = [];
  const TENANT = "22222222-2222-4222-8222-222222222222";
  let reply: { status: number; body: unknown } = { status: 201, body: {} };

  async function load(requireOperator: () => Promise<{ id: string }>) {
    vi.resetModules();
    vi.doUnmock("../setup-actions");
    vi.doMock("server-only", () => ({}));
    vi.doMock("next/cache", () => ({ revalidatePath: vi.fn() }));
    vi.doMock("@/lib/session", () => ({ requireOperator }));
    return (await import("../setup-actions")).createWhatsAppTemplateAction;
  }

  beforeEach(() => {
    sent.length = 0;
    reply = { status: 201, body: { id: "1", name: "aviso", status: "PENDING", category: "UTILITY", audit_log_id: "a" } };
    vi.stubGlobal("fetch", async (url: string, init: RequestInit) => {
      sent.push({ url, method: init.method ?? "GET", body: init.body ? JSON.parse(String(init.body)) : undefined });
      return new Response(JSON.stringify(reply.body), { status: reply.status, headers: { "Content-Type": "application/json" } });
    });
  });

  afterEach(() => vi.unstubAllGlobals());

  it("exige operador antes de llamar a la API", async () => {
    const action = await load(async () => {
      throw new Error("NEXT_REDIRECT");
    });
    await expect(
      action(TENANT, { name: "aviso", language: "es", category: "UTILITY", body_text: "Hola.", buttons: [], examples: {} }),
    ).rejects.toThrow("NEXT_REDIRECT");
    expect(sent).toHaveLength(0);
  });

  it("manda a la API la forma de la consola, sin un encabezado o un pie vacíos", async () => {
    const action = await load(async () => ({ id: "op-1" }));
    const result = await action(TENANT, {
      name: "aviso",
      language: "es_CL",
      category: "UTILITY",
      header_text: "",
      body_text: "Hola {{nombre}}, ya está.",
      footer_text: "",
      buttons: [{ type: "QUICK_REPLY", label: "Gracias" }],
      examples: { nombre: "Camila" },
    });
    expect(result.ok).toBe(true);
    expect(sent[0]!.method).toBe("POST");
    expect(sent[0]!.url).toMatch(new RegExp(`/admin/tenants/${TENANT}/whatsapp/templates$`));
    expect(sent[0]!.body).toStrictEqual({
      name: "aviso",
      language: "es_CL",
      category: "UTILITY",
      body_text: "Hola {{nombre}}, ya está.",
      buttons: [{ type: "QUICK_REPLY", label: "Gracias" }],
      examples: { nombre: "Camila" },
    });
  });

  it("un 422 de validación de la API llega como una frase, no como la lista de FastAPI (el editor la pinta)", async () => {
    const action = await load(async () => ({ id: "op-1" }));
    reply = { status: 422, body: { detail: [{ type: "too_long", loc: ["body", "examples"], msg: "too many" }] } };
    const result = await action(TENANT, { name: "aviso", language: "es", category: "UTILITY", body_text: "Hola.", buttons: [], examples: {} });
    expect(result.ok).toBe(false);
    expect(typeof (result as { error: unknown }).error).toBe("string");
    expect((result as { error: string }).error).toMatch(/422/);
  });

  it("lo que no es la forma de la consola no llega a la API", async () => {
    const action = await load(async () => ({ id: "op-1" }));
    const bad: unknown[] = [
      { name: "aviso", language: "es", category: "UTILITY", components: [{ type: "BODY", text: "Hola" }] },
      { name: "codigo", language: "es", category: "AUTHENTICATION", otp: { button_text: "Copiar" } },
      { name: "codigo", language: "es", category: "AUTHENTICATION", otp_button_text: "Copiar", otp_security_recommendation: true, body_text: "Tu código" },
      { name: "Aviso Pago", language: "es", category: "UTILITY", body_text: "Hola." },
    ];
    for (const body of bad) {
      expect((await action(TENANT, body as never)).ok).toBe(false);
    }
    expect((await action("../x", { name: "aviso", language: "es", category: "UTILITY", body_text: "Hola.", buttons: [], examples: {} })).ok).toBe(false);
    expect(sent).toHaveLength(0);
  });
});
