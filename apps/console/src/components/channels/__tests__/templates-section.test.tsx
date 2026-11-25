import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { TemplateList, TemplateRow } from "@/lib/backend/channels";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
const editTemplateAction = vi.hoisted(() => vi.fn());
vi.mock("@/app/(console)/clients/[ref]/channels/actions", () => ({ deleteTemplateAction: vi.fn(), createTemplateAction: vi.fn(), editTemplateAction }));

const { TemplatesSection } = await import("../templates-section");

const row = (over: Partial<TemplateRow>): TemplateRow => ({
  id: "1",
  name: "recordatorio_cita",
  language: "es",
  category: "UTILITY",
  status: "APPROVED",
  quality_score: null,
  pending_category: null,
  components: [],
  rejection_reason: null,
  suggested_action: "none",
  last_event_at: null,
  ...over,
});

describe("las plantillas dicen su calidad y su cambio de categoría (spec 050, 4.1)", () => {
  it("la calidad en palabras y la categoría que Meta va a aplicar", () => {
    render(
      <LocaleProvider locale="es">
        <TemplatesSection
          refId="demo"
          manage={false}
          error={null}
          list={{
            items: [row({ quality_score: "YELLOW", pending_category: "MARKETING" }), row({ name: "bienvenida", quality_score: "UNKNOWN" })],
            approved: 2,
            rejected: 0,
            pending: 0,
          }}
        />
      </LocaleProvider>,
    );
    expect(screen.getByText("Media")).toBeVisible();
    expect(screen.getByText("Meta la pasa a Marketing en un día")).toBeVisible();
    // Sin puntuación de Meta, una raya y no un código.
    expect(screen.queryByText("UNKNOWN")).toBeNull();
  });
});

describe("una plantilla rechazada se lee entera y se corrige (QA 2026-10-30)", () => {
  const rejected = row({
    name: "aviso_pago",
    language: "es_CL",
    status: "REJECTED",
    rejection_reason: "INVALID_FORMAT: The parameter format is not supported because it has a variable at the end of the message.",
    suggested_action: "fix_format",
    components: [
      { type: "BODY", text: "Hola {{nombre}}, tu pago vence hoy {{fecha}}", example: { body_text_named_params: [{ param_name: "nombre", example: "Ana" }] } },
      { type: "BUTTONS", buttons: [{ type: "QUICK_REPLY", text: "Pagar" }] },
    ],
  });

  it("el idioma en palabras, el motivo completo en el detalle y «Duplicar y corregir» abre el compositor con lo enviado", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();
    render(
      <LocaleProvider locale="es">
        <TemplatesSection refId="demo" manage error={null} list={{ items: [rejected], approved: 0, rejected: 1, pending: 0 }} />
      </LocaleProvider>,
    );
    expect(screen.getByText("Español de Chile")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "aviso_pago" }));
    const dialog = await screen.findByRole("dialog", { name: "aviso_pago" });
    expect(dialog).toHaveTextContent("it has a variable at the end of the message.");
    expect(dialog).toHaveTextContent("Hola Ana");
    await user.click(screen.getByRole("button", { name: "Duplicar y corregir" }));
    expect(await screen.findByLabelText("Nombre")).toHaveValue("aviso_pago_v2");
  });

  it("«Duplicar y corregir» una de autenticación abre el mismo editor en Autenticación, con su botón y su caducidad (spec 075, 10.4)", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();
    const otp = row({
      name: "tecfin_codigo",
      category: "AUTHENTICATION",
      status: "REJECTED",
      rejection_reason: "INVALID_FORMAT",
      suggested_action: "fix_format",
      components: [
        { type: "BODY", text: "*{{1}}* es tu código de verificación.", add_security_recommendation: false },
        { type: "FOOTER", text: "Este código caduca en 5 minutos.", code_expiration_minutes: 5 },
        { type: "BUTTONS", buttons: [{ type: "OTP", otp_type: "COPY_CODE", text: "Copiar" }] },
      ],
    });
    render(
      <LocaleProvider locale="es">
        <TemplatesSection refId="demo" manage error={null} list={{ items: [otp], approved: 0, rejected: 1, pending: 0 }} />
      </LocaleProvider>,
    );
    await user.click(screen.getByRole("button", { name: "tecfin_codigo" }));
    await user.click(await screen.findByRole("button", { name: "Duplicar y corregir" }));
    expect(await screen.findByLabelText("Nombre")).toHaveValue("tecfin_codigo_v2");
    expect(screen.getByRole("radio", { name: /Autenticación/ })).toBeChecked();
    expect(screen.queryByLabelText("Texto del mensaje")).toBeNull();
    expect(screen.getByLabelText("Texto del botón")).toHaveValue("Copiar");
    expect(screen.getByLabelText("Caduca en (min)")).toHaveValue(5);
    expect(screen.getByLabelText(/Aviso de seguridad/)).not.toBeChecked();
  });
});

describe("editar una plantilla desde la consola (spec 075)", () => {
  const draft = {
    category: "UTILITY",
    header_text: null,
    body_text: "Hola {{nombre}}, tu pago vence {{fecha}}",
    footer_text: null,
    buttons: [{ type: "QUICK_REPLY", label: "Pagar" }],
    examples: { nombre: "Ana", fecha: "el lunes" },
  };
  const editable = row({
    name: "aviso_pago",
    language: "es_CL",
    status: "REJECTED",
    rejection_reason: "INVALID_FORMAT: The parameter format is not supported because it has a variable at the end of the message.",
    suggested_action: "fix_format",
    edit_blocker: null,
    draft,
    version: "3f9a0c1d2b4e5f60",
    system_variables: null,
  });
  const paused = row({ name: "pausada", status: "PAUSED", edit_blocker: null, draft, version: "aaaaaaaaaaaaaaaa", system_variables: null });
  const approved = row({ name: "aprobada", status: "APPROVED", edit_blocker: null, draft, version: "bbbbbbbbbbbbbbbb", system_variables: null });
  const inReview = row({ name: "en_revision", status: "PENDING", edit_blocker: "status", draft: null, version: "cccccccccccccccc", system_variables: null });
  const withImage = row({ name: "con_imagen", status: "REJECTED", edit_blocker: "media_header", draft: null, version: "dddddddddddddddd", system_variables: null });
  const all = (items: TemplateRow[]): TemplateList => ({ items, approved: 1, rejected: 2, pending: 1 });

  async function setup(props: { manage?: boolean; list?: TemplateList; onChanged?: () => void } = {}) {
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();
    const onChanged = props.onChanged ?? vi.fn();
    const ui = (list: TemplateList | null, error: string | null = null) => (
      <LocaleProvider locale="es">
        <TemplatesSection refId="demo" manage={props.manage ?? true} error={error} list={list} onChanged={onChanged} />
      </LocaleProvider>
    );
    const view = render(ui(props.list ?? all([editable, paused, approved, inReview, withImage])));
    return { user, onChanged, rerender: (list: TemplateList | null, error: string | null = null) => view.rerender(ui(list, error)) };
  }

  const body = () => screen.getByLabelText("Texto del mensaje") as HTMLTextAreaElement;

  it("«Editar» sale en rechazadas, pausadas y aprobadas que se pueden gestionar, y no en las bloqueadas (1.1, 2.1, 3.1)", async () => {
    await setup();
    expect(screen.getByRole("button", { name: /^Editar: aviso_pago/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Editar: pausada/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Editar: aprobada/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Editar: en_revision/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Editar: con_imagen/ })).toBeNull();
  });

  it("quien solo puede ver el canal no ve «Editar» (8.3)", async () => {
    await setup({ manage: false });
    expect(screen.queryByRole("button", { name: /^Editar/ })).toBeNull();
  });

  it("una plantilla bloqueada dice en una línea por qué y dónde se edita (3.2)", async () => {
    const { user } = await setup();
    await user.click(screen.getByRole("button", { name: "con_imagen" }));
    const dialog = await screen.findByRole("dialog", { name: "con_imagen" });
    expect(dialog).toHaveTextContent("Lleva una imagen, un vídeo o un documento en el encabezado");
    expect(dialog).toHaveTextContent("se edita en WhatsApp Manager");
    expect(within(dialog).queryByRole("button", { name: "Editar" })).toBeNull();
  });

  it("al abrir, el editor sale con el borrador, el nombre y el idioma como título y lo que hay que arreglar a la vista (1.2, 1.3)", async () => {
    const { user } = await setup();
    await user.click(screen.getByRole("button", { name: /^Editar: aviso_pago/ }));
    const dialog = await screen.findByRole("dialog", { name: "Editar plantilla" });
    expect(within(dialog).getByTestId("template-identity")).toHaveTextContent("aviso_pago");
    expect(within(dialog).getByTestId("template-identity")).toHaveTextContent("Español de Chile");
    expect(within(dialog).queryByLabelText("Nombre")).toBeNull();
    expect(body().value).toBe("Hola {{nombre}}, tu pago vence {{fecha}}");
    expect(dialog).toHaveTextContent("Corrige el formato");
    expect(dialog).toHaveTextContent("it has a variable at the end of the message.");
  });

  it("también se abre desde el detalle", async () => {
    const { user } = await setup();
    await user.click(screen.getByRole("button", { name: "pausada" }));
    const detail = await screen.findByRole("dialog", { name: "pausada" });
    await user.click(within(detail).getByRole("button", { name: "Editar" }));
    expect(await screen.findByRole("dialog", { name: "Editar plantilla" })).toBeInTheDocument();
  });

  it("en una aprobada no ofrece cambiar la categoría (2.3)", async () => {
    const { user } = await setup();
    await user.click(screen.getByRole("button", { name: /^Editar: aprobada/ }));
    const dialog = await screen.findByRole("dialog", { name: "Editar plantilla" });
    expect(within(dialog).queryAllByRole("radio")).toHaveLength(0);
  });

  it("guarda con la huella y el borrador, y con éxito avisa y refresca la lista (1.5, 6.1)", async () => {
    const { toast } = await import("sonner");
    editTemplateAction.mockReset();
    editTemplateAction.mockResolvedValue({ ok: true, data: { name: "aviso_pago", language: "es_CL", changed: true, status: "PENDING", category: "UTILITY" } });
    const { user, onChanged } = await setup();
    await user.click(screen.getByRole("button", { name: /^Editar: aviso_pago/ }));
    await screen.findByRole("dialog", { name: "Editar plantilla" });
    fireEvent.change(body(), { target: { value: "Hola {{nombre}}, tu pago vence {{fecha}}. Gracias." } });
    await user.click(screen.getByRole("button", { name: "Enviar a Meta para revisión" }));
    await waitFor(() => expect(editTemplateAction).toHaveBeenCalledTimes(1));
    expect(editTemplateAction.mock.calls[0]?.[0]).toMatchObject({
      ref: "demo",
      name: "aviso_pago",
      language: "es_CL",
      version: "3f9a0c1d2b4e5f60",
      confirm: false,
      category: "UTILITY",
      body_text: "Hola {{nombre}}, tu pago vence {{fecha}}. Gracias.",
      examples: { nombre: "Ana", fecha: "el lunes" },
      buttons: [{ type: "QUICK_REPLY", label: "Pagar" }],
    });
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(toast.success).toHaveBeenCalledWith("Cambios enviados a Meta. Estado: En revisión.");
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Editar plantilla" })).toBeNull());
  });

  it("si la plantilla cambió mientras tanto, lo dice y ofrece recargar con la versión nueva (7.1)", async () => {
    editTemplateAction.mockReset();
    editTemplateAction.mockResolvedValue({ ok: false, status: 409, message: "conflict", code: "template_changed", info: {} });
    const { user, onChanged, rerender } = await setup();
    await user.click(screen.getByRole("button", { name: /^Editar: aviso_pago/ }));
    await screen.findByRole("dialog", { name: "Editar plantilla" });
    fireEvent.change(body(), { target: { value: "Hola {{nombre}}, tu pago vence {{fecha}}. Gracias." } });
    await user.click(screen.getByRole("button", { name: "Enviar a Meta para revisión" }));
    expect(await screen.findByText(/Alguien cambió esta plantilla mientras la editabas/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Recargar" }));
    expect(onChanged).toHaveBeenCalled();
    const fresh = { ...editable, version: "eeeeeeeeeeeeeeee", draft: { ...draft, body_text: "Hola {{nombre}}, tu pago es el {{fecha}}. Te esperamos." } };
    rerender(all([fresh, paused, approved, inReview, withImage]));
    await waitFor(() => expect(body().value).toBe("Hola {{nombre}}, tu pago es el {{fecha}}. Te esperamos."));
    expect(screen.queryByText(/Alguien cambió esta plantilla/)).toBeNull();
  });

  async function conflict(user: Awaited<ReturnType<typeof setup>>["user"]) {
    editTemplateAction.mockReset();
    editTemplateAction.mockResolvedValue({ ok: false, status: 409, message: "conflict", code: "template_changed", info: {} });
    await user.click(screen.getByRole("button", { name: /^Editar: aviso_pago/ }));
    await screen.findByRole("dialog", { name: "Editar plantilla" });
    fireEvent.change(body(), { target: { value: "Hola {{nombre}}, tu pago vence {{fecha}}. Gracias." } });
    await user.click(screen.getByRole("button", { name: "Enviar a Meta para revisión" }));
    return screen.findByRole("button", { name: "Recargar" });
  }

  it("si la lista no vuelve al recargar, lo dice en el editor, conserva lo escrito y deja volver a intentarlo (7.1)", async () => {
    const { user, rerender } = await setup();
    await user.click(await conflict(user));
    rerender(null, "No se pudo conectar con el servidor.");
    const dialog = screen.getByRole("dialog", { name: "Editar plantilla" });
    expect(await within(dialog).findByText("No se pudo recargar la plantilla. Inténtalo de nuevo en un momento.")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Recargar" })).toBeEnabled();
    expect(body().value).toBe("Hola {{nombre}}, tu pago vence {{fecha}}. Gracias.");
  });

  it("si la plantilla ya no existe al recargar, el editor se cierra y lo dice (7.1)", async () => {
    const { toast } = await import("sonner");
    const { user, rerender } = await setup();
    await user.click(await conflict(user));
    rerender(all([paused, approved, inReview, withImage]));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Editar plantilla" })).toBeNull());
    expect(toast.error).toHaveBeenCalledWith("Esta plantilla ya no existe en ese idioma.");
  });

  it("la lista, el detalle y el editor con su aviso de conflicto pasan axe", async () => {
    editTemplateAction.mockReset();
    editTemplateAction.mockResolvedValue({ ok: false, status: 409, message: "conflict", code: "template_changed", info: {} });
    const { user } = await setup();
    expect(await axeViolations()).toEqual([]);
    await user.click(screen.getByRole("button", { name: "con_imagen" }));
    await screen.findByRole("dialog", { name: "con_imagen" });
    expect(await axeViolations()).toEqual([]);
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "con_imagen" })).toBeNull());
    await user.click(screen.getByRole("button", { name: /^Editar: aviso_pago/ }));
    await screen.findByRole("dialog", { name: "Editar plantilla" });
    fireEvent.change(body(), { target: { value: "Hola {{nombre}}, tu pago vence {{fecha}}. Gracias." } });
    await user.click(screen.getByRole("button", { name: "Enviar a Meta para revisión" }));
    await screen.findByRole("button", { name: "Recargar" });
    expect(await axeViolations()).toEqual([]);
  });

  it("en una aprobada, el servidor pide confirmar: la consola dice las tres cosas y reenvía con confirm (2.2)", async () => {
    editTemplateAction.mockReset();
    editTemplateAction
      .mockResolvedValueOnce({ ok: false, status: 409, message: "confirm", code: "confirmation_required", info: { reasons: [{ kind: "approved" }, { kind: "queued_sends", count: 2 }] } })
      .mockResolvedValueOnce({ ok: true, data: { name: "aprobada", language: "es", changed: true, status: "PENDING", category: "UTILITY" } });
    const { user, onChanged } = await setup();
    await user.click(screen.getByRole("button", { name: /^Editar: aprobada/ }));
    await screen.findByRole("dialog", { name: "Editar plantilla" });
    fireEvent.change(body(), { target: { value: "Hola {{nombre}}, tu pago vence {{fecha}}. Gracias." } });
    await user.click(screen.getByRole("button", { name: "Enviar a Meta para revisión" }));
    const confirm = await screen.findByRole("dialog", { name: "Antes de mandarla a Meta" });
    expect(confirm).toHaveTextContent("vuelve a revisión");
    expect(confirm).toHaveTextContent("Auphere puede dejar de mandarla hasta que Meta la apruebe otra vez");
    expect(confirm).toHaveTextContent("Meta limita cuántas veces se edita una plantilla aprobada");
    expect(confirm).toHaveTextContent("hay 2 envíos en cola");
    await user.click(within(confirm).getByRole("button", { name: "Guardar y mandar a revisión" }));
    await waitFor(() => expect(editTemplateAction).toHaveBeenCalledTimes(2));
    expect(editTemplateAction.mock.calls[0]?.[0]).toMatchObject({ confirm: false });
    expect(editTemplateAction.mock.calls[0]?.[0]).not.toHaveProperty("category");
    expect(editTemplateAction.mock.calls[1]?.[0]).toMatchObject({ confirm: true, name: "aprobada", version: "bbbbbbbbbbbbbbbb" });
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("si la acción falla sin respuesta, lo dice y conserva lo escrito", async () => {
    editTemplateAction.mockReset();
    editTemplateAction.mockRejectedValue(new Error("network"));
    const { user } = await setup();
    await user.click(screen.getByRole("button", { name: /^Editar: aviso_pago/ }));
    await screen.findByRole("dialog", { name: "Editar plantilla" });
    fireEvent.change(body(), { target: { value: "Hola {{nombre}}, tu pago vence {{fecha}}. Gracias." } });
    await user.click(screen.getByRole("button", { name: "Enviar a Meta para revisión" }));
    expect(await screen.findByText("No se pudo guardar. Inténtalo de nuevo en un momento.")).toBeInTheDocument();
    expect(body().value).toBe("Hola {{nombre}}, tu pago vence {{fecha}}. Gracias.");
  });

  it("si Meta rechaza la edición, enseña su motivo y conserva lo escrito (1.6)", async () => {
    editTemplateAction.mockReset();
    editTemplateAction.mockResolvedValue({
      ok: false,
      status: 422,
      message: "meta",
      code: "meta_rejected",
      info: { meta_code: 100, meta_subcode: null, user_message: "El texto tiene demasiadas variables." },
    });
    const { user } = await setup();
    await user.click(screen.getByRole("button", { name: /^Editar: aviso_pago/ }));
    await screen.findByRole("dialog", { name: "Editar plantilla" });
    fireEvent.change(body(), { target: { value: "Hola {{nombre}}, tu pago vence {{fecha}}. Gracias." } });
    await user.click(screen.getByRole("button", { name: "Enviar a Meta para revisión" }));
    expect(await screen.findByText("Meta no aceptó el cambio: El texto tiene demasiadas variables.")).toBeInTheDocument();
    expect(body().value).toBe("Hola {{nombre}}, tu pago vence {{fecha}}. Gracias.");
  });
});
