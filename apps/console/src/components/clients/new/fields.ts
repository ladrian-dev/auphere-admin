import type { MessageKey } from "@/i18n/messages";

/**
 * Cómo se enseña cada campo del negocio (spec 019, iteración 1 · revisión UX).
 *
 * El paso 2 pintaba una lista plana de cajas iguales a ancho completo, sin
 * ejemplo y sin decir para qué sirve ninguna. Medido sobre la clínica
 * estética: **nueve campos, cero ayudas**. Un teléfono de nueve dígitos en
 * una caja de 800 px, y «Teléfono de referencia (cirugía)» sin decir si lleva
 * prefijo ni de qué país.
 *
 * Tres decisiones, y cada una ataca una fricción distinta:
 *
 * - **Cada campo dice para qué lo usa el agente.** No es decoración: es lo
 *   único que permite al partner juzgar si un campo importa. Sin eso, ante la
 *   duda, se escribe cualquier cosa — y lo que se escribe aquí lo dice el
 *   agente por teléfono.
 * - **Cada campo enseña un ejemplo real**, con el formato dentro. Un ejemplo
 *   ahorra la pregunta que el formato en la etiqueta —«(E.164)»— no contesta.
 * - **El ancho sigue al contenido, y los campos se agrupan.** Un teléfono no
 *   necesita el ancho de la pantalla, y nueve cosas sueltas se leen mejor
 *   como tres grupos de tres.
 *
 * Lo que no está aquí cae en el grupo por defecto a ancho entero: una
 * plantilla nueva no se queda sin pintar, solo sin ayuda — y eso se ve.
 */

export type Grupo = "negocio" | "quien" | "urgencias" | "contacto" | "condiciones";
export type Ancho = "media" | "entera";

type Meta = { grupo: Grupo; ancho: Ancho };

/** El orden en el que se pintan los grupos. */
export const GRUPOS: Grupo[] = ["negocio", "quien", "urgencias", "contacto", "condiciones"];

export const GRUPO_TITULO: Record<Grupo, MessageKey> = {
  negocio: "wizard.group.negocio",
  quien: "wizard.group.quien",
  urgencias: "wizard.group.urgencias",
  contacto: "wizard.group.contacto",
  condiciones: "wizard.group.condiciones",
};

const CAMPOS: Record<string, Meta> = {
  "tenant.address": { grupo: "negocio", ancho: "entera" },
  "tenant.business_hours_label": { grupo: "negocio", ancho: "entera" },
  "tenant.saturday_label": { grupo: "negocio", ancho: "media" },

  "clinical.titular_name": { grupo: "quien", ancho: "media" },
  "clinical.titular_credential": { grupo: "quien", ancho: "media" },
  "policies.admin_access.admin_phones": { grupo: "quien", ancho: "entera" },
  "policies.wholesale.contact_name": { grupo: "quien", ancho: "media" },
  "policies.wholesale.contact_phone": { grupo: "quien", ancho: "media" },

  "tenant.surgery_referral_hospital": { grupo: "urgencias", ancho: "media" },
  "tenant.surgery_referral_phone": { grupo: "urgencias", ancho: "media" },

  "tenant.instagram_handle": { grupo: "contacto", ancho: "media" },
  "tenant.front_desk_phone_label": { grupo: "contacto", ancho: "media" },

  "tenant.consultation_price_label": { grupo: "condiciones", ancho: "media" },
  "tenant.pricing_table_label": { grupo: "condiciones", ancho: "entera" },
  "tenant.payment_methods_label": { grupo: "condiciones", ancho: "entera" },
  "policies.store.shipping_info": { grupo: "condiciones", ancho: "entera" },
  "policies.store.returns_info": { grupo: "condiciones", ancho: "entera" },
  "policies.store.currency": { grupo: "condiciones", ancho: "media" },
};

const POR_DEFECTO: Meta = { grupo: "negocio", ancho: "entera" };

export function metaDe(key: string): Meta {
  return CAMPOS[key] ?? POR_DEFECTO;
}

/**
 * Los campos repartidos en grupos, **solo si agrupar dice algo**.
 *
 * Con dos campos —que es lo que pide diez de las trece plantillas— un título
 * encima de cada uno es ruido puro. Los títulos aparecen cuando hay bastantes
 * para perderse: cinco, que es donde la lista deja de leerse de un vistazo.
 */
export function agrupar<T extends { key: string }>(
  campos: T[],
): { agrupado: boolean; grupos: Array<{ grupo: Grupo; campos: T[] }> } {
  const porGrupo = new Map<Grupo, T[]>();
  for (const campo of campos) {
    const { grupo } = metaDe(campo.key);
    porGrupo.set(grupo, [...(porGrupo.get(grupo) ?? []), campo]);
  }
  const grupos = GRUPOS.filter((g) => porGrupo.has(g)).map((grupo) => ({
    grupo,
    campos: porGrupo.get(grupo)!,
  }));
  return { agrupado: campos.length >= 5 && grupos.length > 1, grupos };
}

/** `ph.<clave>.hint` y `ph.<clave>.eg`, que pueden no existir. */
export function hintKey(key: string): MessageKey {
  return `ph.${key}.hint` as MessageKey;
}
export function egKey(key: string): MessageKey {
  return `ph.${key}.eg` as MessageKey;
}
