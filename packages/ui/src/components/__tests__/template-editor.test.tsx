import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { TemplateDraft } from "../../lib/template-rules";
import { axeViolations } from "../../test/axe";
import { TemplateEditor, type TemplateEditorLabels, type TemplateEditorProps } from "../template-editor";

/**
 * El editor de plantillas de WhatsApp (spec 075, R9): uno solo para la consola
 * y para el panel. Los textos le llegan de fuera (`labels`) y lo escrito sale
 * por `onSubmit`; no sabe de acciones de servidor ni de rutas.
 */

const LABELS: TemplateEditorLabels = {
  purpose: "¿Para qué es?",
  category: (c) => ({ UTILITY: "Utilidad", MARKETING: "Marketing", AUTHENTICATION: "Autenticación" })[c] ?? c,
  categoryHelp: (c) =>
    ({ UTILITY: "Avisos de algo ya pedido.", MARKETING: "Promociones.", AUTHENTICATION: "Códigos de un solo uso." })[c] ?? "",
  name: "Nombre",
  nameExample: "aviso_de_pago",
  nameHelp: "Solo lo ves tú.",
  language: "Idioma",
  message: "Mensaje",
  header: "Encabezado (opcional)",
  body: "Texto del mensaje",
  bodyHelp: "Lo que va entre llaves dobles se rellena al enviar.",
  bodyExample: "Hola {{nombre}}, tu pedido ya va.",
  counter: (n, max) => `${n} de ${max}`,
  insertVariable: "Insertar variable",
  otherVariable: "otra variable",
  addVariable: "Insertar",
  examples: "Ejemplos para Meta",
  examplesHelp: "Un ejemplo de cada variable.",
  example: (name) => `Ejemplo de ${name}`,
  footer: "Pie (opcional)",
  buttons: "Botones (opcional)",
  buttonsHelp: "Hasta tres.",
  buttonKind: (k) => ({ QUICK_REPLY: "Respuesta rápida", URL: "Enlace", PHONE_NUMBER: "Llamar" })[k],
  buttonType: (n) => `Tipo del botón ${n}`,
  buttonLabel: (n) => `Texto del botón ${n}`,
  buttonLabelPlaceholder: "Texto del botón",
  buttonUrl: (n) => `Dirección web del botón ${n}`,
  buttonPhone: (n) => `Teléfono del botón ${n}`,
  buttonRemove: (n) => `Quitar el botón ${n}`,
  addButton: "Añadir botón",
  buttonIssue: (issue) => `Botón: ${issue}`,
  bodyIssue: (issue) => `Texto: ${issue.code}`,
  preview: "Así lo verá el cliente",
  previewEmpty: "Escribe el mensaje para verlo aquí.",
  errorTitle: "No se pudo guardar la plantilla",
  ready: "Lista para enviar a Meta.",
  missing: (pieces) => `Falta ${pieces.join(", ")}.`,
  cancel: "Cancelar",
  submit: "Enviar a Meta para revisión",
  systemVariables: {
    title: "Auphere manda esta plantilla por su nombre",
    help: (mode) => (mode === "exact" ? "Tiene que llevar estas variables, ni más ni menos:" : "Solo puede llevar estas variables:"),
    missing: (names) => `Falta ${names.map((n) => `{{${n}}}`).join(", ")}.`,
    extra: (names) => `Sobra ${names.map((n) => `{{${n}}}`).join(", ")}.`,
  },
  otp: {
    legend: "Código de verificación",
    intro: "Meta escribe el mensaje; aquí se eligen el botón, la caducidad y el aviso.",
    button: "Texto del botón",
    buttonDefault: "Copiar código",
    buttonHelp: "Hasta 25 caracteres.",
    minutes: "Caduca en (min)",
    minutesHelp: "De 1 a 90. Vacío: no dice cuándo caduca.",
    security: "Aviso de seguridad",
    securityHelp: "Añade «Por tu seguridad, no lo compartas.»",
    previewSpanish: "Vista previa en español",
    previewOther: (lang) => `Meta pone el texto fijo en ${lang}, el idioma de la plantilla.`,
  },
  confirm: {
    title: "Antes de mandarla a Meta",
    confirm: "Guardar y mandar a revisión",
    cancel: "Volver al editor",
    reason: (r) =>
      r.kind === "approved"
        ? "Está aprobada: vuelve a revisión, Auphere deja de mandarla hasta que Meta la apruebe otra vez, y Meta limita cuántas veces se edita."
        : r.kind === "queued_sends"
          ? `Hay ${r.count} envíos en cola que fallarán.`
          : "Meta pide confirmarlo.",
  },
};

const REJECTED: TemplateDraft = {
  name: "aviso_pago",
  language: "es_CL",
  category: "UTILITY",
  header: "",
  body: "Hola {{nombre}}, tu pago vence hoy.",
  footer: "",
  buttons: [{ type: "QUICK_REPLY", label: "Pagar" }],
  examples: { nombre: "Ana" },
};

type Submit = TemplateEditorProps["onSubmit"];

function mount(
  over: Partial<Omit<TemplateEditorProps, "onSubmit" | "onCancel">> = {},
  onSubmit = vi.fn<Submit>(async () => ({ kind: "done" })),
) {
  const onCancel = vi.fn();
  render(<TemplateEditor mode="create" labels={LABELS} {...over} onSubmit={onSubmit} onCancel={onCancel} />);
  return { onSubmit, onCancel };
}

const body = () => screen.getByLabelText("Texto del mensaje") as HTMLTextAreaElement;
const send = () => screen.getByRole("button", { name: "Enviar a Meta para revisión" });

describe("TemplateEditor al crear", () => {
  it("pide nombre e idioma y ofrece las tres categorías que se pueden crear (10.2)", () => {
    mount();
    expect(screen.getByLabelText("Nombre")).toBeInTheDocument();
    expect(screen.getByLabelText("Idioma")).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(3);
    expect(screen.getByRole("radio", { name: /Autenticación/ })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: /Utilidad/ })).toBeChecked();
  });

  it("onSubmit recibe el borrador limpio, sin mandar nada mientras falte algo", async () => {
    const { onSubmit } = mount();
    fireEvent.click(send());
    expect(onSubmit).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "Aviso de pago_" } });
    fireEvent.change(body(), { target: { value: "Hola {{nombre}}, recibimos tu pago." } });
    fireEvent.change(screen.getByLabelText("Ejemplo de nombre"), { target: { value: " Camila " } });
    fireEvent.click(send());
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(
      {
        name: "aviso_de_pago",
        language: "es",
        category: "UTILITY",
        header_text: undefined,
        body_text: "Hola {{nombre}}, recibimos tu pago.",
        footer_text: undefined,
        buttons: [],
        examples: { nombre: "Camila" },
      },
      { confirm: false },
    );
  });
});

describe("TemplateEditor al editar (spec 075, 1.3, 2.3)", () => {
  it("el nombre y el idioma salen como título, no como campos", () => {
    mount({ mode: "edit", initial: REJECTED });
    expect(screen.queryByLabelText("Nombre")).toBeNull();
    expect(screen.queryByLabelText("Idioma")).toBeNull();
    // Ningún selector de idioma (el del tipo de botón sí existe).
    expect(screen.queryByRole("option", { name: "Español de Chile" })).toBeNull();
    const identity = screen.getByTestId("template-identity");
    expect(identity).toHaveTextContent("aviso_pago");
    expect(identity).toHaveTextContent("Español de Chile");
    // El contenido actual, listo para cambiarlo.
    expect(body().value).toBe("Hola {{nombre}}, tu pago vence hoy.");
    expect(screen.getByLabelText("Ejemplo de nombre")).toHaveValue("Ana");
  });

  it("en una rechazada o pausada deja cambiar la categoría", () => {
    mount({ mode: "edit", initial: REJECTED });
    expect(screen.getAllByRole("radio")).toHaveLength(2);
  });

  it("con la categoría bloqueada, el control de categoría no existe (no está desactivado)", () => {
    mount({ mode: "edit", initial: REJECTED, categoryLocked: true });
    expect(screen.queryAllByRole("radio")).toHaveLength(0);
    expect(screen.queryByText("¿Para qué es?")).toBeNull();
  });

  it("onSubmit recibe el borrador con el nombre y el idioma de la plantilla", async () => {
    const { onSubmit } = mount({ mode: "edit", initial: REJECTED, categoryLocked: true });
    fireEvent.change(body(), { target: { value: "Hola {{nombre}}, tu pago vence hoy. Gracias." } });
    fireEvent.click(send());
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0]?.[0]).toEqual({
      name: "aviso_pago",
      language: "es_CL",
      category: "UTILITY",
      header_text: undefined,
      body_text: "Hola {{nombre}}, tu pago vence hoy. Gracias.",
      footer_text: undefined,
      buttons: [{ type: "QUICK_REPLY", label: "Pagar", url: undefined, phone_number: undefined }],
      examples: { nombre: "Ana" },
    });
    expect(onSubmit.mock.calls[0]?.[1]).toEqual({ confirm: false });
  });

  it("enseña el error del servidor sin perder lo escrito", () => {
    mount({ mode: "edit", initial: REJECTED, serverError: "Meta dice que el texto es engañoso." });
    const alert = screen.getByText("No se pudo guardar la plantilla").closest("[role=alert]") as HTMLElement;
    expect(within(alert).getByText("Meta dice que el texto es engañoso.")).toBeInTheDocument();
    expect(body().value).toBe("Hola {{nombre}}, tu pago vence hoy.");
  });

  it("con systemVariables lista las variables que tiene que llevar (4.1)", () => {
    mount({
      mode: "edit",
      initial: { ...REJECTED, name: "reserva_recordatorio", language: "es" },
      systemVariables: { mode: "exact", variables: ["nombre", "negocio", "cuando"] },
    });
    const box = screen.getByTestId("template-system-variables");
    expect(box).toHaveTextContent("Auphere manda esta plantilla por su nombre");
    for (const v of ["{{nombre}}", "{{negocio}}", "{{cuando}}"]) expect(within(box).getByText(v)).toBeInTheDocument();
  });

  it("Cancelar avisa a quien lo abrió", () => {
    const { onCancel } = mount({ mode: "edit", initial: REJECTED });
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(onCancel).toHaveBeenCalled();
  });
});

describe("TemplateEditor pide confirmar cuando el servidor lo pide (spec 075, 2.2, 5.1)", () => {
  const APPROVED: TemplateDraft = { ...REJECTED, name: "recordatorio_cita", language: "es" };

  function edited() {
    fireEvent.change(body(), { target: { value: "Hola {{nombre}}, tu pago vence mañana." } });
    fireEvent.click(send());
  }

  it("abre la confirmación con una frase por razón y, al confirmar, vuelve a mandar con confirm: true", async () => {
    const onSubmit = vi.fn<Submit>(async (_draft, { confirm }) =>
      confirm ? { kind: "done" } : { kind: "confirmation_required", reasons: [{ kind: "approved" }, { kind: "queued_sends", count: 3 }] },
    );
    mount({ mode: "edit", initial: APPROVED, categoryLocked: true }, onSubmit);
    edited();
    const dialog = await screen.findByRole("dialog", { name: "Antes de mandarla a Meta" });
    // approved: vuelve a revisión, Auphere puede dejar de mandarla y Meta limita las ediciones.
    expect(dialog).toHaveTextContent("vuelve a revisión");
    expect(dialog).toHaveTextContent("Auphere deja de mandarla hasta que Meta la apruebe otra vez");
    expect(dialog).toHaveTextContent("Meta limita cuántas veces se edita");
    // queued_sends: con su número.
    expect(dialog).toHaveTextContent("Hay 3 envíos en cola que fallarán.");
    expect(onSubmit).toHaveBeenCalledTimes(1);
    fireEvent.click(within(dialog).getByRole("button", { name: "Guardar y mandar a revisión" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(2));
    expect(onSubmit.mock.calls[1]?.[0]).toEqual(onSubmit.mock.calls[0]?.[0]);
    expect(onSubmit.mock.calls[1]?.[1]).toEqual({ confirm: true });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Antes de mandarla a Meta" })).toBeNull());
  });

  it("una razón que no conoce también tiene su frase", async () => {
    const onSubmit = vi.fn<Submit>(async () => ({ kind: "confirmation_required", reasons: [{ kind: "something_new" }] }));
    mount({ mode: "edit", initial: APPROVED, categoryLocked: true }, onSubmit);
    edited();
    expect(await screen.findByRole("dialog", { name: "Antes de mandarla a Meta" })).toHaveTextContent("Meta pide confirmarlo.");
  });

  it("volver al editor no manda nada y conserva lo escrito", async () => {
    const onSubmit = vi.fn<Submit>(async () => ({ kind: "confirmation_required", reasons: [{ kind: "approved" }] }));
    mount({ mode: "edit", initial: APPROVED, categoryLocked: true }, onSubmit);
    edited();
    const dialog = await screen.findByRole("dialog", { name: "Antes de mandarla a Meta" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Volver al editor" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Antes de mandarla a Meta" })).toBeNull());
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(body().value).toBe("Hola {{nombre}}, tu pago vence mañana.");
  });
});

describe("TemplateEditor con una plantilla que Auphere manda por su nombre (spec 075, 4.1–4.3)", () => {
  const RESERVA: TemplateDraft = {
    ...REJECTED,
    name: "reserva_recordatorio",
    language: "es",
    buttons: [],
    body: "Hola {{nombre}}, te esperamos en {{negocio}} el {{cuando}}. Gracias.",
    examples: { nombre: "Ana", negocio: "Spa Jemma", cuando: "el jueves" },
  };
  const exact = { mode: "exact" as const, variables: ["nombre", "negocio", "cuando"] };

  it("avisa al escribir si falta una variable o sobra otra, y no deja guardar", async () => {
    const { onSubmit } = mount({ mode: "edit", initial: RESERVA, systemVariables: exact });
    const box = screen.getByTestId("template-system-variables");
    expect(within(box).queryByRole("alert")).toBeNull();

    fireEvent.change(body(), { target: { value: "Hola {{nombre}}, te esperamos {{cuando}}. Gracias {{otra}} y adiós." } });
    const alert = within(box).getByRole("alert");
    expect(alert).toHaveTextContent("Falta {{negocio}}.");
    expect(alert).toHaveTextContent("Sobra {{otra}}.");

    fireEvent.click(send());
    await new Promise((r) => setTimeout(r, 0));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText(/Falta .*system_variables/)).toBeInTheDocument();
  });

  it("las variables que lleva se ofrecen para insertar, y no otras", () => {
    mount({ mode: "edit", initial: RESERVA, systemVariables: exact });
    const group = screen.getByRole("group", { name: "Insertar variable" });
    expect(within(group).getByRole("button", { name: "{{negocio}}" })).toBeInTheDocument();
    expect(within(group).queryByRole("button", { name: "{{pedido}}" })).toBeNull();
    expect(within(group).queryByLabelText("otra variable")).toBeNull();
  });

  it("subset_keep: no puede perder una que ya lleva ni ganar una que Auphere no manda", () => {
    mount({
      mode: "edit",
      initial: { ...RESERVA, name: "recordatorio_pago_vencido", body: "Hola {{cliente}}, debes {{monto}}. Gracias.", examples: { cliente: "Ana", monto: "10" } },
      systemVariables: { mode: "subset_keep", variables: ["cliente", "negocio", "monto", "fecha"] },
    });
    fireEvent.change(body(), { target: { value: "Hola {{cliente}}, vence el {{fecha}}. Tu {{iban}} sigue igual." } });
    const alert = within(screen.getByTestId("template-system-variables")).getByRole("alert");
    expect(alert).toHaveTextContent("Falta {{monto}}.");
    expect(alert).toHaveTextContent("Sobra {{iban}}.");
  });

  it("lo que el servidor dice de las variables también se ve, hasta que se cambia el texto", async () => {
    const onSubmit = vi.fn<Submit>(async () => ({ kind: "system_variables", missing: ["cuando"], extra: [] }));
    mount({ mode: "edit", initial: RESERVA, systemVariables: { mode: "exact", variables: ["nombre", "negocio", "cuando"] } }, onSubmit);
    fireEvent.click(send());
    const box = screen.getByTestId("template-system-variables");
    expect(await within(box).findByRole("alert")).toHaveTextContent("Falta {{cuando}}.");
    fireEvent.change(body(), { target: { value: `${RESERVA.body} ` } });
    expect(within(box).queryByRole("alert")).toBeNull();
  });
});

describe("TemplateEditor es accesible (spec 075, T031)", () => {
  const FULL: TemplateDraft = {
    ...REJECTED,
    header: "Tu pago",
    footer: "Auphere",
    buttons: [
      { type: "QUICK_REPLY", label: "" },
      { type: "URL", label: "Ver", url: "http://sin-https" },
      { type: "PHONE_NUMBER", label: "Llamar", phone_number: "123" },
    ],
  };

  it("pasa axe al crear, vacío y tras intentar enviar", async () => {
    mount();
    expect(await axeViolations()).toEqual([]);
    fireEvent.click(send());
    expect(await axeViolations()).toEqual([]);
  });

  it("pasa axe al editar, con variables de Auphere, botones con fallos, avisos del texto y error del servidor", async () => {
    mount({
      mode: "edit",
      initial: { ...FULL, body: "{{nombre}} tu pago {{fecha}}" },
      systemVariables: { mode: "exact", variables: ["nombre", "negocio"] },
      serverError: "Meta no aceptó el cambio.",
    });
    fireEvent.click(send());
    expect(await axeViolations()).toEqual([]);
  });

  it("los fallos del texto y de las variables de Auphere describen el campo del texto", () => {
    mount({
      mode: "edit",
      initial: { ...REJECTED, body: "{{nombre}} tu pago" },
      systemVariables: { mode: "exact", variables: ["nombre", "negocio"] },
    });
    expect(body()).toHaveAccessibleDescription(/Texto: starts_with_variable/);
    expect(body()).toHaveAccessibleDescription(/Falta \{\{negocio\}\}\./);
  });

  it("un botón mal escrito marca su campo y, al enviar, recibe el foco", async () => {
    const { onSubmit } = mount({
      mode: "edit",
      initial: { ...REJECTED, buttons: [{ type: "URL", label: "Ver", url: "http://sin-https" }] },
    });
    const url = screen.getByLabelText("Dirección web del botón 1");
    expect(url).toHaveAttribute("aria-invalid", "true");
    expect(url).toHaveAccessibleDescription("Botón: url_invalid");
    fireEvent.click(send());
    await new Promise((r) => requestAnimationFrame(() => r(null)));
    expect(url).toHaveFocus();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("la confirmación se anuncia con sus razones al abrirse", async () => {
    const onSubmit = vi.fn<Submit>(async () => ({ kind: "confirmation_required", reasons: [{ kind: "approved" }, { kind: "queued_sends", count: 2 }] }));
    mount({ mode: "edit", initial: REJECTED, categoryLocked: true }, onSubmit);
    fireEvent.click(send());
    const dialog = await screen.findByRole("dialog", { name: "Antes de mandarla a Meta" });
    expect(dialog).toHaveAccessibleDescription(/vuelve a revisión.*Hay 2 envíos en cola que fallarán\./);
  });

  it("pasa axe con la confirmación abierta", async () => {
    const onSubmit = vi.fn<Submit>(async () => ({ kind: "confirmation_required", reasons: [{ kind: "approved" }] }));
    mount({ mode: "edit", initial: REJECTED, categoryLocked: true }, onSubmit);
    fireEvent.click(send());
    await screen.findByRole("dialog", { name: "Antes de mandarla a Meta" });
    expect(await axeViolations()).toEqual([]);
  });
});

describe("TemplateEditor con Autenticación: el mismo editor para todo (spec 075, requisito 10)", () => {
  const preview = () => screen.getByLabelText("Así lo verá el cliente");
  const auth = () => fireEvent.click(screen.getByRole("radio", { name: /Autenticación/ }));

  it("al elegirla pide el botón, la caducidad y el aviso en lugar del mensaje y los botones (10.2)", () => {
    mount();
    auth();
    expect(screen.queryByLabelText("Texto del mensaje")).toBeNull();
    expect(screen.queryByRole("button", { name: "Añadir botón" })).toBeNull();
    expect(screen.getByLabelText("Texto del botón")).toHaveValue("Copiar código");
    expect(screen.getByLabelText("Caduca en (min)")).toHaveValue(10);
    expect(screen.getByLabelText(/Aviso de seguridad/)).toBeChecked();
  });

  it("la vista previa es el texto fijo de Meta y sigue los campos (10.2)", () => {
    mount();
    auth();
    expect(preview()).toHaveTextContent("Vista previa en español");
    expect(preview()).toHaveTextContent("123456 es tu código de verificación. Por tu seguridad, no lo compartas.");
    expect(preview()).toHaveTextContent("Este código caduca en 10 minutos.");
    expect(preview()).toHaveTextContent("Copiar código");
    fireEvent.click(screen.getByLabelText(/Aviso de seguridad/));
    expect(preview()).not.toHaveTextContent("Por tu seguridad");
    fireEvent.change(screen.getByLabelText("Caduca en (min)"), { target: { value: "" } });
    expect(preview()).not.toHaveTextContent("caduca");
    fireEvent.change(screen.getByLabelText("Texto del botón"), { target: { value: "Copiar" } });
    expect(preview()).toHaveTextContent("Copiar");
  });

  it("solo enseña el texto fijo en español para una plantilla en español; si no, lo dice (10.3)", () => {
    mount();
    auth();
    fireEvent.change(screen.getByLabelText("Idioma"), { target: { value: "en" } });
    expect(preview()).not.toHaveTextContent("es tu código de verificación");
    expect(preview()).toHaveTextContent("Meta pone el texto fijo en English, el idioma de la plantilla.");
    fireEvent.change(screen.getByLabelText("Idioma"), { target: { value: "es_MX" } });
    expect(preview()).toHaveTextContent("123456 es tu código de verificación.");
  });

  it("una caducidad fuera de 1 a 90 marca el campo, se dice qué falta y no se envía", () => {
    const { onSubmit } = mount();
    auth();
    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "codigo" } });
    fireEvent.change(screen.getByLabelText("Caduca en (min)"), { target: { value: "120" } });
    expect(screen.getByLabelText("Caduca en (min)")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Falta otp_minutes.")).toBeInTheDocument();
    fireEvent.click(send());
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("envía el nombre, el idioma, la categoría y otp_*, nunca un cuerpo", async () => {
    const { onSubmit } = mount();
    auth();
    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "tecfin codigo" } });
    fireEvent.click(send());
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0]?.[0]).toStrictEqual({
      name: "tecfin_codigo",
      language: "es",
      category: "AUTHENTICATION",
      otp_button_text: "Copiar código",
      otp_expiration_minutes: 10,
      otp_security_recommendation: true,
    });
    expect(onSubmit.mock.calls[0]?.[1]).toEqual({ confirm: false });
  });

  it("«Duplicar» de una de autenticación empieza en Autenticación con sus valores, y con el botón por defecto si venía vacío (10.4)", () => {
    mount({
      initial: {
        name: "codigo_v2",
        language: "es",
        category: "AUTHENTICATION",
        header: "",
        body: "",
        footer: "",
        buttons: [],
        examples: {},
        otp: { buttonText: "", minutes: "5", security: false },
      },
    });
    expect(screen.getByRole("radio", { name: /Autenticación/ })).toBeChecked();
    expect(screen.getByLabelText("Nombre")).toHaveValue("codigo_v2");
    expect(screen.getByLabelText("Texto del botón")).toHaveValue("Copiar código");
    expect(screen.getByLabelText("Caduca en (min)")).toHaveValue(5);
    expect(screen.getByLabelText(/Aviso de seguridad/)).not.toBeChecked();
  });

  it("al editar no ofrece Autenticación (1.4, 3.2)", () => {
    mount({ mode: "edit", initial: REJECTED });
    expect(screen.getAllByRole("radio")).toHaveLength(2);
    expect(screen.queryByRole("radio", { name: /Autenticación/ })).toBeNull();
  });

  it("pasa axe con Autenticación elegida, vacía y tras intentar enviar", async () => {
    mount();
    auth();
    expect(await axeViolations()).toEqual([]);
    fireEvent.change(screen.getByLabelText("Texto del botón"), { target: { value: "" } });
    fireEvent.click(send());
    expect(await axeViolations()).toEqual([]);
  });
});
