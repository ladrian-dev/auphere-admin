import type { TemplateEditFailure, TemplateEditorLabels } from "@nexus/ui";

/**
 * The panel's words for `TemplateEditor` (spec 075, R9). The editor is the
 * console's, from `@nexus/ui`; the panel speaks Spanish only.
 */

const CATEGORY: Record<string, string> = { UTILITY: "Utilidad", MARKETING: "Marketing", AUTHENTICATION: "Autenticación" };
const CATEGORY_HELP: Record<string, string> = {
  UTILITY: "Avisos de algo que el cliente ya pidió o pagó, como pedidos, pagos o citas. Meta la aprueba antes y cuesta menos.",
  MARKETING: "Promociones, ofertas y novedades. Solo para quien aceptó recibirlas.",
  AUTHENTICATION: "Códigos de verificación para entrar a una cuenta.",
};
const MISSING: Record<string, string> = {
  name: "el nombre",
  body: "el texto del mensaje",
  examples: "un ejemplo de cada variable",
  body_rules: "corregir el texto del mensaje",
  buttons: "completar los botones",
  system_variables: "ajustar las variables que manda Auphere",
  otp_button: "el texto del botón (hasta 25 caracteres)",
  otp_minutes: "una caducidad de 1 a 90 minutos",
};
const BODY_ISSUE: Record<string, string> = {
  starts_with_variable: "El mensaje no puede empezar con una variable. Pon una palabra antes, por ejemplo Hola.",
  ends_with_variable: "El mensaje no puede terminar con una variable. Añade una frase después.",
  adjacent_variables: "Dos variables seguidas no se aceptan. Pon alguna palabra entre ellas.",
  mixed_formats: "Usa variables con nombre o numeradas, pero no las dos a la vez.",
};
const BUTTON_ISSUE: Record<string, string> = {
  label_missing: "Escribe el texto del botón.",
  url_invalid: "La dirección tiene que empezar por https://.",
  phone_invalid: "Escribe el teléfono con el prefijo del país, por ejemplo +56 9 1234 5678.",
};
const BUTTON_KIND: Record<string, string> = { QUICK_REPLY: "Respuesta rápida", URL: "Enlace", PHONE_NUMBER: "Llamar" };

const vars = (names: string[]) => names.map((n) => `{{${n}}}`).join(", ");

export const TEMPLATE_EDITOR_LABELS_ES: TemplateEditorLabels = {
  purpose: "¿Para qué es?",
  category: (c) => CATEGORY[c] ?? c,
  categoryHelp: (c) => CATEGORY_HELP[c] ?? "",
  name: "Nombre",
  nameExample: "aviso_de_pago",
  nameHelp: "Solo lo ves tú. Se guarda en minúsculas y con guion bajo en lugar de espacios.",
  language: "Idioma",
  message: "Mensaje",
  header: "Encabezado (opcional)",
  body: "Texto del mensaje",
  bodyHelp: "Lo que va entre llaves dobles se rellena al enviar, por ejemplo {{nombre}}. Usa minúsculas y guion bajo.",
  bodyExample: "Hola {{nombre}}, tu pedido {{pedido}} ya va en camino. Gracias por tu compra.",
  counter: (n, max) => `${n} de ${max}`,
  insertVariable: "Insertar variable",
  otherVariable: "otra variable",
  addVariable: "Insertar",
  examples: "Ejemplos para Meta",
  examplesHelp: "Meta revisa la plantilla con un ejemplo de cada variable. Pon un valor realista, no el nombre de la variable.",
  example: (name) => `Ejemplo de ${name}`,
  footer: "Pie (opcional)",
  buttons: "Botones (opcional)",
  buttonsHelp: "Hasta tres. Respuesta rápida devuelve un toque al negocio, Enlace abre una web y Llamar marca un número.",
  buttonKind: (k) => BUTTON_KIND[k] ?? k,
  buttonType: (n) => `Tipo del botón ${n}`,
  buttonLabel: (n) => `Texto del botón ${n}`,
  buttonLabelPlaceholder: "Texto del botón",
  buttonUrl: (n) => `Dirección web del botón ${n}`,
  buttonPhone: (n) => `Teléfono del botón ${n}`,
  buttonRemove: (n) => `Quitar el botón ${n}`,
  addButton: "Añadir botón",
  buttonIssue: (issue) => BUTTON_ISSUE[issue] ?? issue,
  bodyIssue: (issue) => {
    if (issue.code === "bad_variable") return `«${issue.text}» no es una variable válida. Usa minúsculas, números y guion bajo.`;
    if (issue.code === "positional_gap") return `Falta la variable número ${issue.missing}. Las numeradas van seguidas desde la 1.`;
    return BODY_ISSUE[issue.code] ?? issue.code;
  },
  preview: "Así lo verá el cliente",
  previewEmpty: "Escribe el mensaje para verlo aquí.",
  errorTitle: "No se pudo guardar la plantilla",
  ready: "Lista para enviar a Meta.",
  missing: (pieces) => `Falta ${pieces.map((p) => MISSING[p] ?? p).join(", ")}.`,
  cancel: "Cancelar",
  submit: "Enviar a Meta para revisión",
  otp: {
    legend: "Código de verificación",
    intro: "Meta fija el texto de las plantillas de autenticación. Solo se eligen el botón, la caducidad y el aviso de seguridad.",
    button: "Texto del botón",
    buttonDefault: "Copiar código",
    buttonHelp: "Hasta 25 caracteres. Al tocarlo, copia el código.",
    minutes: "Caduca en (min)",
    minutesHelp: "De 1 a 90. Vacío: no dice cuándo caduca.",
    security: "Aviso de seguridad",
    securityHelp: "Añade «Por tu seguridad, no lo compartas.»",
    previewSpanish: "Vista previa en español",
    previewOther: (lang) => `Meta pone el texto fijo en ${lang}, el idioma de la plantilla. Aquí solo se previsualiza en español.`,
  },
  systemVariables: {
    title: "Auphere manda esta plantilla por su nombre",
    help: (mode) =>
      mode === "exact"
        ? "Reservas la manda con estas variables: tiene que llevarlas todas y ninguna más."
        : "Los recordatorios de cobro la mandan con estas variables: no puede llevar otras ni perder las que ya tiene.",
    missing: (names) => `Falta ${vars(names)}.`,
    extra: (names) => `Auphere no manda ${vars(names)}.`,
  },
  confirm: {
    title: "Antes de mandarla a Meta",
    confirm: "Guardar y mandar a revisión",
    cancel: "Seguir editando",
    reason: (r) => {
      if (r.kind === "approved") {
        return "Está aprobada: al guardar vuelve a revisión, Auphere puede dejar de mandarla hasta que Meta la apruebe otra vez, y Meta limita cuántas veces se edita una plantilla aprobada.";
      }
      if (r.kind === "queued_sends") {
        return r.count === 1
          ? "Cambias sus variables y hay 1 envío en cola preparado con las de antes: fallará."
          : `Cambias sus variables y hay ${r.count ?? 0} envíos en cola preparados con las de antes: fallarán.`;
      }
      return "Meta o Auphere piden confirmarlo antes de guardar.";
    },
  },
};

const BLOCKER: Record<string, string> = {
  status: "Meta no deja editarla mientras está en revisión, en apelación o desactivada.",
  authentication: "Es de autenticación y Meta fija su formato: se edita en WhatsApp Manager.",
  media_header:
    "Lleva una imagen, un vídeo o un documento en el encabezado, que este editor no maneja: se edita en WhatsApp Manager.",
  header_variable: "El encabezado lleva una variable, que este editor no maneja: se edita en WhatsApp Manager.",
  unsupported_button:
    "Lleva un botón de código, de catálogo o de formulario, que este editor no maneja: se edita en WhatsApp Manager.",
  url_variable:
    "Un botón de enlace lleva una variable en la dirección, que este editor no maneja: se edita en WhatsApp Manager.",
  too_many_buttons: "Lleva más de tres botones, más de los que deja este editor: se edita en WhatsApp Manager.",
  unsupported_component:
    "Lleva una parte que este editor no sabe pintar, como un carrusel o una oferta por tiempo limitado: se edita en WhatsApp Manager.",
};

/** Spec 075 (3.2): why a template cannot be edited here, in one sentence. */
export function blockerSentence(blocker: string | null | undefined): string {
  return BLOCKER[blocker ?? ""] ?? "Tiene algo que este editor no sabe editar: se edita en WhatsApp Manager.";
}

/** The sentence for a failed edit: Meta's own words when it gave them, ours otherwise. */
export function editFailureSentence(failure: TemplateEditFailure): string {
  switch (failure.kind) {
    case "template_changed":
      return "Alguien cambió esta plantilla mientras la editabas, aquí o en WhatsApp Manager. Tus cambios no se han guardado: recarga para ver la versión actual.";
    case "template_not_found":
      return "Esta plantilla ya no existe en ese idioma. Recarga la lista.";
    case "not_editable":
      return blockerSentence(failure.blocker);
    case "category_locked":
      return "Una plantilla aprobada no puede cambiar de categoría.";
    case "missing_examples":
      return `Falta un ejemplo para ${vars(failure.variables)}.`;
    case "system_variables":
      return [
        failure.missing.length ? `Falta ${vars(failure.missing)}.` : null,
        failure.extra.length ? `Auphere no manda ${vars(failure.extra)}.` : null,
      ]
        .filter(Boolean)
        .join(" ");
    case "meta_rejected":
      // The edit limit of an approved template has no code we have seen (research R2, C2).
      return failure.userMessage
        ? `Meta no aceptó el cambio: ${failure.userMessage}`
        : "Meta no aceptó el cambio y la plantilla sigue como estaba.";
    case "whatsapp_not_connected":
      return "Este cliente no tiene WhatsApp conectado con Meta.";
    case "forbidden":
      return "No tienes permiso para editar plantillas.";
    default:
      return "No se pudo guardar. Inténtalo de nuevo en un momento.";
  }
}
