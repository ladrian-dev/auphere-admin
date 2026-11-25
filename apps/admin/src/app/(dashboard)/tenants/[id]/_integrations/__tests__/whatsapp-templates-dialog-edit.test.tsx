/**
 * Spec 075 (requisito 9): el panel edita las plantillas de WhatsApp de un
 * cliente con el mismo editor que la consola (`TemplateEditor`, de
 * `@nexus/ui`) y con las mismas reglas: «Editar» solo donde la API no pone un
 * bloqueo, la línea que dice por qué cuando lo hay, y la acción de servidor
 * que exige operador y lo nombra ante la API.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import type { WhatsAppTemplate } from "@/lib/backend";

const list = vi.hoisted(() => vi.fn());
const edit = vi.hoisted(() => vi.fn());
vi.mock("../setup-actions", () => ({
  listWhatsAppTemplatesAction: (...args: unknown[]) => list(...args),
  editWhatsAppTemplateAction: (...args: unknown[]) => edit(...args),
  createWhatsAppTemplateAction: vi.fn(),
  deleteWhatsAppTemplateAction: vi.fn(),
}));

const toastSuccess = vi.hoisted(() => vi.fn());
const toastError = vi.hoisted(() => vi.fn());
vi.mock("sonner", () => ({ toast: { success: (...a: unknown[]) => toastSuccess(...a), error: (...a: unknown[]) => toastError(...a) } }));

const { WhatsAppTemplatesDialog } = await import("../whatsapp-templates-dialog");

const DRAFT = {
  category: "UTILITY",
  header_text: null,
  body_text: "Hola {{nombre}}, te esperamos {{cuando}}",
  footer_text: null,
  buttons: [],
  examples: { nombre: "Camila", cuando: "el jueves" },
};

function tpl(over: Partial<WhatsAppTemplate>): WhatsAppTemplate {
  return {
    id: "1",
    name: "recordatorio",
    language: "es",
    category: "UTILITY",
    status: "REJECTED",
    quality_score: null,
    components: [{ type: "BODY", text: DRAFT.body_text }],
    edit_blocker: null,
    draft: DRAFT,
    version: "3f9a0c1d2b4e5f60",
    system_variables: null,
    ...over,
  };
}

const TEMPLATES = [
  tpl({}),
  tpl({ name: "aprobada", status: "APPROVED", version: "bbbbbbbbbbbbbbbb" }),
  tpl({ name: "en_revision", status: "PENDING", edit_blocker: "status", draft: null }),
  tpl({ name: "con_imagen", edit_blocker: "media_header", draft: null }),
];

async function open() {
  const user = userEvent.setup();
  render(<WhatsAppTemplatesDialog tenantId="t1" />);
  await user.click(screen.getByRole("button", { name: "Plantillas" }));
  await screen.findByText("recordatorio");
  return user;
}

const body = () => screen.getByLabelText("Texto del mensaje") as HTMLTextAreaElement;

describe("Editar una plantilla desde el panel (spec 075, 9.1–9.3)", () => {
  beforeEach(() => {
    list.mockReset();
    edit.mockReset();
    toastSuccess.mockReset();
    toastError.mockReset();
    list.mockResolvedValue({ ok: true, data: { templates: TEMPLATES, waba_id: "W1" } });
  });

  it("«Editar» sale con las mismas reglas que en la consola", async () => {
    await open();
    expect(screen.getByRole("button", { name: "Editar plantilla recordatorio (Español)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Editar plantilla aprobada (Español)" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Editar plantilla en_revision/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Editar plantilla con_imagen/ })).toBeNull();
    // Bloqueada: una línea con el motivo y dónde se edita (3.2).
    const blocked = screen.getByText("con_imagen").closest("li") as HTMLElement;
    expect(blocked).toHaveTextContent("se edita en WhatsApp Manager");
  });

  it("un texto largo no saca «Editar» ni «Borrar» del diálogo (visto en staging el 2026-11-25)", async () => {
    // En staging, una línea de texto en `truncate` ensanchaba la lista a
    // 1136 px dentro de un diálogo de 640: los botones quedaban fuera de vista.
    // Una pista de rejilla `auto` crece hasta el texto entero; sin `min-w-0`
    // en la fila y con una columna `minmax(0, 1fr)` se queda en el ancho.
    await open();
    const row = screen.getByText("recordatorio").closest("li") as HTMLElement;
    const list = row.closest("ul") as HTMLElement;
    expect(list.className).toContain("grid-cols-1");
    expect(row.className).toContain("min-w-0");
    expect(within(row).getByText(DRAFT.body_text).className).toContain("truncate");
  });

  it("el editor es el de @nexus/ui en modo edición: el nombre y el idioma son el título", async () => {
    const user = await open();
    await user.click(screen.getByRole("button", { name: "Editar plantilla recordatorio (Español)" }));
    const dialog = await screen.findByRole("dialog", { name: "Editar plantilla" });
    expect(within(dialog).getByTestId("template-identity")).toHaveTextContent("recordatorio");
    expect(within(dialog).queryByLabelText("Nombre")).toBeNull();
    expect(body().value).toBe(DRAFT.body_text);
    // Rechazada: deja cambiar la categoría (9.2, D6).
    expect(within(dialog).getAllByRole("radio")).toHaveLength(2);
  });

  it("en una aprobada no ofrece la categoría", async () => {
    const user = await open();
    await user.click(screen.getByRole("button", { name: "Editar plantilla aprobada (Español)" }));
    const dialog = await screen.findByRole("dialog", { name: "Editar plantilla" });
    expect(within(dialog).queryAllByRole("radio")).toHaveLength(0);
  });

  it("guarda con la huella y el borrador, y con éxito recarga la lista", async () => {
    edit.mockResolvedValue({ ok: true, data: { name: "recordatorio", language: "es", changed: true, status: "PENDING", category: "UTILITY" } });
    const user = await open();
    await user.click(screen.getByRole("button", { name: "Editar plantilla recordatorio (Español)" }));
    await screen.findByRole("dialog", { name: "Editar plantilla" });
    fireEvent.change(body(), { target: { value: "Hola {{nombre}}, te esperamos {{cuando}}. Gracias." } });
    await user.click(screen.getByRole("button", { name: "Enviar a Meta para revisión" }));
    await waitFor(() => expect(edit).toHaveBeenCalledTimes(1));
    const [tenantId, name, language, sent] = edit.mock.calls[0]!;
    expect([tenantId, name, language]).toEqual(["t1", "recordatorio", "es"]);
    expect(sent).toMatchObject({
      version: "3f9a0c1d2b4e5f60",
      confirm: false,
      category: "UTILITY",
      body_text: "Hola {{nombre}}, te esperamos {{cuando}}. Gracias.",
      examples: { nombre: "Camila", cuando: "el jueves" },
    });
    expect(sent).not.toHaveProperty("name");
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
    expect(toastSuccess).toHaveBeenCalledWith("Cambios enviados a Meta. Estado: En revisión.");
  });

  it("si Meta rechaza, enseña su motivo y conserva lo escrito", async () => {
    edit.mockResolvedValue({
      ok: false,
      error: "meta_rejected",
      code: "meta_rejected",
      info: { meta_code: 100, meta_subcode: null, user_message: "El texto parece promocional." },
    });
    const user = await open();
    await user.click(screen.getByRole("button", { name: "Editar plantilla recordatorio (Español)" }));
    await screen.findByRole("dialog", { name: "Editar plantilla" });
    fireEvent.change(body(), { target: { value: "Hola {{nombre}}, te esperamos {{cuando}}. Gracias." } });
    await user.click(screen.getByRole("button", { name: "Enviar a Meta para revisión" }));
    expect(await screen.findByText("Meta no aceptó el cambio: El texto parece promocional.")).toBeInTheDocument();
    expect(body().value).toBe("Hola {{nombre}}, te esperamos {{cuando}}. Gracias.");
  });

  it("si la acción falla sin respuesta, lo dice y conserva lo escrito", async () => {
    edit.mockRejectedValue(new Error("network"));
    const user = await open();
    await user.click(screen.getByRole("button", { name: "Editar plantilla recordatorio (Español)" }));
    await screen.findByRole("dialog", { name: "Editar plantilla" });
    fireEvent.change(body(), { target: { value: "Hola {{nombre}}, te esperamos {{cuando}}. Gracias." } });
    await user.click(screen.getByRole("button", { name: "Enviar a Meta para revisión" }));
    expect(await screen.findByText("No se pudo guardar. Inténtalo de nuevo en un momento.")).toBeInTheDocument();
    expect(body().value).toBe("Hola {{nombre}}, te esperamos {{cuando}}. Gracias.");
  });

  it("si la plantilla cambió mientras tanto, lo dice y ofrece recargar", async () => {
    edit.mockResolvedValue({ ok: false, error: "template_changed", code: "template_changed", info: {} });
    const user = await open();
    await user.click(screen.getByRole("button", { name: "Editar plantilla recordatorio (Español)" }));
    await screen.findByRole("dialog", { name: "Editar plantilla" });
    fireEvent.change(body(), { target: { value: "Hola {{nombre}}, te esperamos {{cuando}}. Gracias." } });
    await user.click(screen.getByRole("button", { name: "Enviar a Meta para revisión" }));
    expect(await screen.findByText(/Alguien cambió esta plantilla mientras la editabas/)).toBeInTheDocument();
    list.mockResolvedValue({
      ok: true,
      data: { templates: [tpl({ version: "eeeeeeeeeeeeeeee", draft: { ...DRAFT, body_text: "Hola {{nombre}}, nos vemos {{cuando}}. Saludos." } })], waba_id: "W1" },
    });
    await user.click(screen.getByRole("button", { name: "Recargar" }));
    await waitFor(() => expect(body().value).toBe("Hola {{nombre}}, nos vemos {{cuando}}. Saludos."));
  });

  async function conflict(user: Awaited<ReturnType<typeof open>>) {
    edit.mockResolvedValue({ ok: false, error: "template_changed", code: "template_changed", info: {} });
    await user.click(screen.getByRole("button", { name: "Editar plantilla recordatorio (Español)" }));
    await screen.findByRole("dialog", { name: "Editar plantilla" });
    fireEvent.change(body(), { target: { value: "Hola {{nombre}}, te esperamos {{cuando}}. Gracias." } });
    await user.click(screen.getByRole("button", { name: "Enviar a Meta para revisión" }));
    return screen.findByRole("button", { name: "Recargar" });
  }

  it("mientras recarga, «Recargar» dice que está en ello", async () => {
    const user = await open();
    const reload = await conflict(user);
    let answer: (v: unknown) => void = () => {};
    list.mockReturnValue(new Promise((r) => (answer = r)));
    await user.click(reload);
    expect(reload).toHaveAttribute("aria-busy", "true");
    answer({ ok: true, data: { templates: [tpl({ version: "eeeeeeeeeeeeeeee" })], waba_id: "W1" } });
    await waitFor(() => expect(screen.getByRole("button", { name: "Enviar a Meta para revisión" })).toBeEnabled());
  });

  it("si la lista no se puede recargar, lo dice en el editor y conserva lo escrito", async () => {
    const user = await open();
    const reload = await conflict(user);
    list.mockResolvedValue({ ok: false, error: "Meta no responde." });
    await user.click(reload);
    const dialog = screen.getByRole("dialog", { name: "Editar plantilla" });
    expect(await within(dialog).findByText(/No se pudo recargar la plantilla: Meta no responde\./)).toBeInTheDocument();
    expect(body().value).toBe("Hola {{nombre}}, te esperamos {{cuando}}. Gracias.");
  });

  it("si la plantilla ya no existe al recargar, se cierra y lo dice", async () => {
    const user = await open();
    const reload = await conflict(user);
    list.mockResolvedValue({ ok: true, data: { templates: TEMPLATES.slice(1), waba_id: "W1" } });
    await user.click(reload);
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Editar plantilla" })).toBeNull());
    expect(toastError).toHaveBeenCalledWith("Esta plantilla ya no existe en ese idioma.");
  });

  it("la lista y el editor con su aviso de conflicto pasan axe", async () => {
    const user = await open();
    expect(await axeViolations()).toEqual([]);
    await conflict(user);
    expect(await axeViolations()).toEqual([]);
  });
});

// ── la acción de servidor ──────────────────────────────────────────────

describe("editWhatsAppTemplateAction (8.3)", () => {
  type Sent = { url: string; method: string; headers: Record<string, string>; body: unknown };
  const sent: Sent[] = [];
  let reply: { status: number; body: unknown } = { status: 200, body: {} };

  async function load(requireOperator: () => Promise<{ id: string }>) {
    vi.resetModules();
    vi.doUnmock("../setup-actions");
    vi.doMock("server-only", () => ({}));
    vi.doMock("next/cache", () => ({ revalidatePath: vi.fn() }));
    vi.doMock("@/lib/session", () => ({ requireOperator }));
    return (await import("../setup-actions")).editWhatsAppTemplateAction;
  }

  const BODY = {
    version: "3f9a0c1d2b4e5f60",
    confirm: false,
    category: "UTILITY" as const,
    body_text: "Hola {{nombre}}, te esperamos. Gracias.",
    buttons: [],
    examples: { nombre: "Camila" },
  };
  const TENANT = "22222222-2222-4222-8222-222222222222";

  beforeEach(() => {
    sent.length = 0;
    reply = { status: 200, body: { name: "recordatorio", language: "es", changed: true, status: "PENDING", category: "UTILITY" } };
    vi.stubGlobal("fetch", async (url: string, init: RequestInit) => {
      sent.push({
        url,
        method: init.method ?? "GET",
        headers: init.headers as Record<string, string>,
        body: init.body ? JSON.parse(String(init.body)) : undefined,
      });
      return new Response(JSON.stringify(reply.body), { status: reply.status, headers: { "Content-Type": "application/json" } });
    });
  });

  afterEach(() => vi.unstubAllGlobals());

  it("exige operador antes de llamar a la API", async () => {
    const action = await load(async () => {
      throw new Error("NEXT_REDIRECT");
    });
    await expect(action(TENANT, "recordatorio", "es", BODY)).rejects.toThrow("NEXT_REDIRECT");
    expect(sent).toHaveLength(0);
  });

  it("manda PUT por nombre e idioma y nombra al operador con X-Operator-Id", async () => {
    const action = await load(async () => ({ id: "op-1" }));
    const result = await action(TENANT, "recordatorio", "es_CL", BODY);
    expect(result.ok).toBe(true);
    expect(sent[0]!.method).toBe("PUT");
    expect(sent[0]!.url).toMatch(new RegExp(`/admin/tenants/${TENANT}/whatsapp/templates/recordatorio/es_CL$`));
    expect(sent[0]!.headers["X-Operator-Id"]).toBe("op-1");
    expect(sent[0]!.body).toMatchObject({ version: "3f9a0c1d2b4e5f60", confirm: false, body_text: BODY.body_text });
  });

  it("un nombre o un cliente que no valen no llegan a la URL", async () => {
    const action = await load(async () => ({ id: "op-1" }));
    expect((await action(TENANT, "../x", "es", BODY)).ok).toBe(false);
    expect((await action("../x", "recordatorio", "es", BODY)).ok).toBe(false);
    expect(sent).toHaveLength(0);
  });

  it("devuelve el código y los datos del rechazo, no solo un texto", async () => {
    const action = await load(async () => ({ id: "op-1" }));
    reply = { status: 409, body: { detail: { code: "confirmation_required", reasons: [{ kind: "approved" }] } } };
    const result = await action(TENANT, "recordatorio", "es", BODY);
    expect(result).toMatchObject({ ok: false, code: "confirmation_required", info: { reasons: [{ kind: "approved" }] } });
  });
});
