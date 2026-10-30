import type { MessageKey } from "@/i18n/messages";
import { messages } from "@/i18n/messages";
import type { AgentConnector, ConnectorPermission, SettingsSchema } from "@/lib/backend/agent-connectors-types";
import type { AgentSpec, SpecSkill } from "@/lib/backend/builder-types";

/**
 * Spec 047 (historia 21; T129) — lo que la sección Conectores de un agente y la
 * página de cada conexión deciden sin pintar nada: en qué estado está cada fila,
 * qué acciones tiene, cómo se filtra el catálogo y cómo se leen y se escriben
 * los ajustes declarados en el catálogo (36.2). Puro: lo prueban los tests sin
 * montar la pantalla.
 */

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

/** Una conexión con la que se puede trabajar ahora mismo (`services/activations.LIVE`). */
export function isLive(status: string | null | undefined): boolean {
  return status === "connected" || status === "partial";
}

/** Rota: hay que volver a autorizar para que los agentes la usen. */
export function isBroken(status: string | null | undefined): boolean {
  return status === "needs_reauth" || status === "error" || status === "revoked" || status === "expired";
}

/**
 * El estado de una fila: sin conectar, conectado (con o sin uso en este agente)
 * o con la conexión del cliente en otro estado (rota, pendiente, en pausa…).
 */
export type RowState = "not_connected" | "on" | "off" | "other";

export function rowState(c: AgentConnector): RowState {
  if (!c.connection || c.connection.status === "disconnected") return "not_connected";
  if (!isLive(c.connection.status)) return "other";
  return c.activation ? "on" : "off";
}

export type RowActionKind = "connect" | "reconnect" | "page" | "settings" | "remove";

/**
 * Las acciones de una fila, la principal primero (prototipo §9, hueco H10):
 * sin conectar —o conectado al cliente y sin usar aquí— «Conectar»; conectado,
 * «Ajustes» (el permiso, los ajustes del catálogo y su página; 63.3) y
 * «Quitar»; roto, «Reconectar» y su página. El permiso no está en la fila.
 */
export function rowActions(c: AgentConnector, canWrite: boolean): RowActionKind[] {
  const state = rowState(c);
  const page: RowActionKind[] = c.connection ? ["page"] : [];
  if (!canWrite) return page;
  switch (state) {
    case "not_connected":
    case "off":
      return ["connect"];
    case "other":
      // Rota o a medio autorizar: volver a autorizar. En pausa se reanuda desde su página de cliente.
      return c.connection?.status === "paused" ? page : [isBroken(c.connection?.status) ? "reconnect" : "connect", ...page];
    case "on":
      return ["settings", "remove"];
  }
}

const NAMED_CATEGORIES = new Set(["booking", "calendar", "billing", "catalog", "ecommerce", "messaging", "docs", "crm"]);
/** Una categoría que la consola no sabe nombrar cae en «El resto», como en Conectores del cliente. */
export const OTHER_CATEGORY = "other";

export function categoryOf(c: Pick<AgentConnector, "category">): string {
  return NAMED_CATEGORIES.has(c.category) ? c.category : OTHER_CATEGORY;
}

export function categoryLabel(t: T, key: string): string {
  return key === OTHER_CATEGORY ? t("catalog.rest") : t(`int.cat.${key}` as MessageKey);
}

/** Las categorías en el orden en que aparecen, sin repetir. */
export function categoriesOf(list: readonly AgentConnector[]): string[] {
  const out: string[] = [];
  for (const c of list) {
    const key = categoryOf(c);
    if (!out.includes(key)) out.push(key);
  }
  return out;
}

/** «Conectados» en el filtro segmentado: los que usa este agente. */
export const CONNECTED_FILTER = "connected";

/**
 * El catálogo filtrado por nombre (o slug) y por categoría —o por
 * «Conectados», los que usa este agente—, sin cambiar el orden que recibe.
 */
export function filterConnectors(list: readonly AgentConnector[], filter: { q: string; category: string | null }): AgentConnector[] {
  const needle = filter.q.trim().toLowerCase();
  return list.filter((c) => {
    if (filter.category === CONNECTED_FILTER) {
      if (rowState(c) !== "on") return false;
    } else if (filter.category && categoryOf(c) !== filter.category) return false;
    if (needle && !`${c.name} ${c.slug}`.toLowerCase().includes(needle)) return false;
    return true;
  });
}

/** Los números del filtro segmentado (H10): «Todos», «Conectados» y cada categoría. */
export function filterCounts(list: readonly AgentConnector[]): { all: number; connected: number; categories: Record<string, number> } {
  const categories: Record<string, number> = {};
  let connected = 0;
  for (const c of list) {
    const key = categoryOf(c);
    categories[key] = (categories[key] ?? 0) + 1;
    if (rowState(c) === "on") connected += 1;
  }
  return { all: list.length, connected, categories };
}

/**
 * El orden de la pestaña (62.5; prototipo §9): primero lo que piden las
 * habilidades del agente, luego lo que ya usa, y después el resto; dentro de
 * cada grupo, el orden de la API.
 */
export function orderConnectors(list: readonly AgentConnector[]): AgentConnector[] {
  const rank = (c: AgentConnector) => (c.needed ? 0 : rowState(c) === "on" ? 1 : 2);
  return list
    .map((c, i) => ({ c, i }))
    .sort((a, b) => rank(a.c) - rank(b.c) || a.i - b.i)
    .map(({ c }) => c);
}

export function permissionLabel(t: T, p: ConnectorPermission): string {
  return t(`agentConn.permission.${p}` as MessageKey);
}

export function authKindLabel(t: T, kind: string): string {
  const key = `agentConn.auth.${kind}` as MessageKey;
  return key in messages ? t(key) : t("agentConn.auth.other");
}

/** Para qué sirve el conector, si la consola lo tiene escrito (`connectors.desc.{slug}`). */
export function descriptionKey(slug: string): MessageKey | null {
  const key = `connectors.desc.${slug}` as MessageKey;
  return key in messages ? key : null;
}

/** La página de una conexión. Con el agente, la página sabe volver a él. */
export function connectionHref(ref: string, connectionId: string, agentId?: string): string {
  const base = `/clients/${encodeURIComponent(ref)}/integrations/${encodeURIComponent(connectionId)}`;
  return agentId ? `${base}?agent=${encodeURIComponent(agentId)}` : base;
}

/** La sección Conectores en la pantalla de un agente. */
export function agentConnectorsHref(ref: string, agentId: string): string {
  return `/clients/${encodeURIComponent(ref)}/agents/${encodeURIComponent(agentId)}?tab=integrations`;
}

/**
 * Las habilidades del borrador que declaran este conector: lo que se puede decir
 * antes de quitarlo (35.7). La lista de verdad la devuelve la API al quitarlo.
 */
export function skillsUsing(spec: AgentSpec | null | undefined, slug: string): SpecSkill[] {
  const skills = (spec?.skills ?? []) as SpecSkill[];
  return skills.filter((s) => s?.integration === slug);
}

// ── Los ajustes declarados en el catálogo (36.2) ─────────────────────────────

export type SettingField = {
  /** `reminders.hour_local` */
  path: string;
  kind: "text" | "url" | "integer" | "number" | "boolean";
  /** El grupo al que pertenece (`reminders`), para pintarlo junto. */
  group: string | null;
  required: boolean;
  min?: number;
  max?: number;
  pattern?: string;
  title?: string;
};

/** Los campos de un esquema de ajustes, aplanados (hasta un nivel de grupo). */
export function settingFields(schema: SettingsSchema | null | undefined): SettingField[] {
  const out: SettingField[] = [];
  const walk = (node: SettingsSchema, prefix: string | null, depth: number) => {
    const required = new Set(node.required ?? []);
    for (const [name, prop] of Object.entries(node.properties ?? {})) {
      const path = prefix ? `${prefix}.${name}` : name;
      if (prop.type === "object" && prop.properties && depth < 2) {
        walk(prop, path, depth + 1);
        continue;
      }
      const kind: SettingField["kind"] =
        prop.type === "boolean"
          ? "boolean"
          : prop.type === "integer"
            ? "integer"
            : prop.type === "number"
              ? "number"
              : prop.format === "uri" || prop.pattern === "^https://"
                ? "url"
                : "text";
      out.push({
        path,
        kind,
        group: prefix,
        required: required.has(name),
        ...(prop.minimum !== undefined ? { min: prop.minimum } : {}),
        ...(prop.maximum !== undefined ? { max: prop.maximum } : {}),
        ...(prop.pattern ? { pattern: prop.pattern } : {}),
        ...(prop.title ? { title: prop.title } : {}),
      });
    }
  };
  if (schema) walk(schema, null, 0);
  return out;
}

function humanize(key: string): string {
  const words = key.replace(/[._]+/g, " ").trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : key;
}

/** El nombre de un ajuste: el de la consola, el `title` del esquema o su clave legible. */
export function settingLabel(t: T, slug: string, path: string, title?: string): string {
  const key = `agentConn.setting.${slug}.${path}` as MessageKey;
  if (key in messages) return t(key);
  return title ?? humanize(path.split(".").pop() ?? path);
}

function read(settings: Record<string, unknown>, path: string): unknown {
  let node: unknown = settings;
  for (const part of path.split(".")) {
    if (!node || typeof node !== "object") return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return node;
}

/** Lo guardado, como lo edita el formulario: texto para los campos, `true`/`false` para las casillas. */
export function settingValues(fields: readonly SettingField[], settings: Record<string, unknown>): Record<string, string | boolean> {
  const out: Record<string, string | boolean> = {};
  for (const f of fields) {
    const v = read(settings, f.path);
    out[f.path] = f.kind === "boolean" ? v === true : v === undefined || v === null ? "" : String(v);
  }
  return out;
}

export type SettingProblem = "required" | "integer" | "https" | "invalid";

/** Lo que el formulario ve antes de mandar: la API vuelve a validar con el esquema. */
export function settingProblems(fields: readonly SettingField[], values: Record<string, string | boolean>): Record<string, SettingProblem> {
  const out: Record<string, SettingProblem> = {};
  for (const f of fields) {
    const raw = values[f.path];
    if (f.kind === "boolean") continue;
    const text = typeof raw === "string" ? raw.trim() : "";
    if (!text) {
      if (f.required) out[f.path] = "required";
      continue;
    }
    if (f.kind === "integer" || f.kind === "number") {
      const n = Number(text.replace(",", "."));
      if (!Number.isFinite(n) || (f.kind === "integer" && !Number.isInteger(n)) || (f.min !== undefined && n < f.min) || (f.max !== undefined && n > f.max)) {
        out[f.path] = "integer";
      }
      continue;
    }
    if (f.kind === "url" && !/^https:\/\//i.test(text)) {
      out[f.path] = "https";
      continue;
    }
    if (f.pattern) {
      try {
        if (!new RegExp(f.pattern).test(text)) out[f.path] = "invalid";
      } catch {
        // Un patrón que el navegador no entiende lo decide la API.
      }
    }
  }
  return out;
}

/**
 * Los ajustes que se mandan: los campos vacíos no viajan (la API no los
 * acepta vacíos) y los grupos se rehacen (`reminders.hour_local` →
 * `{reminders: {hour_local}}`).
 */
export function settingsFromValues(fields: readonly SettingField[], values: Record<string, string | boolean>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of fields) {
    const raw = values[f.path];
    let value: unknown;
    if (f.kind === "boolean") value = raw === true;
    else {
      const text = typeof raw === "string" ? raw.trim() : "";
      if (!text) continue;
      value = f.kind === "integer" || f.kind === "number" ? Number(text.replace(",", ".")) : text;
    }
    const parts = f.path.split(".");
    let node = out;
    for (const part of parts.slice(0, -1)) node = (node[part] ??= {}) as Record<string, unknown>;
    node[parts[parts.length - 1]!] = value;
  }
  return out;
}

/** Los campos que la API marcó en `invalid_settings` (`{field, message}`); el mensaje lo escribe la consola. */
export function apiSettingProblems(info: Record<string, unknown> | undefined): Record<string, SettingProblem> {
  const out: Record<string, SettingProblem> = {};
  const errors = info?.errors;
  if (!Array.isArray(errors)) return out;
  for (const e of errors) {
    const field = e && typeof e === "object" ? (e as { field?: unknown }).field : null;
    if (typeof field === "string" && field) out[field] = "invalid";
  }
  return out;
}

/** «Dirección de la tienda: https://…» para leer los ajustes de un agente de un vistazo. */
export function settingsSummary(t: T, slug: string, fields: readonly SettingField[], settings: Record<string, unknown>): string[] {
  const out: string[] = [];
  for (const f of fields) {
    const v = read(settings, f.path);
    if (v === undefined || v === null || v === "") continue;
    const text = typeof v === "boolean" ? t(v ? "agentConn.settings.yes" : "agentConn.settings.no") : String(v);
    out.push(`${settingLabel(t, slug, f.path, f.title)}: ${text}`);
  }
  return out;
}
