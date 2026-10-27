import type { MessageKey } from "@/i18n/messages";
import type {
  Attention,
  AttentionCode,
  Bag,
  ClientAction,
  ClientFilter,
  Lifecycle,
  MissingSection,
  VisibleState,
} from "@/lib/backend/client-records";

/**
 * Spec 047 (T065, T067) — lo que la lista y el Panel del cliente pintan, sin
 * React. La API decide (la regla de atención, el estado visible, los días y lo
 * permitido); aquí solo se ponen las palabras y los enlaces.
 */

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

const COUNTED: ReadonlySet<AttentionCode> = new Set([
  "channel_problem",
  "integration_reauth",
  "agent_cap",
  "agent_without_channel",
]);

/** «Pausado · cliente archivado», «Atendiendo»… de `visible_state`. */
export function agentStateText(t: T, state: VisibleState): string {
  if (state.code === "paused") {
    const reason = state.pause_reason ? t(`clients.v2.pause.${state.pause_reason}` as MessageKey) : t("clients.v2.pause.manual");
    return t("clients.v2.agent.paused", { reason });
  }
  return t(`clients.v2.agent.${state.code}` as MessageKey);
}

/** El motivo de un cliente: el más grave, con su cuenta o sus días. */
export function reasonText(t: T, code: AttentionCode, count: number, bag: Bag | null): string {
  if (code === "low_balance") {
    return bag?.days_left != null ? t("clients.v2.attention.low_balance.days", { days: Math.round(bag.days_left) }) : t("clients.v2.attention.low_balance");
  }
  if (COUNTED.has(code)) {
    return t(`clients.v2.attention.${code}.${count === 1 ? "one" : "other"}` as MessageKey, { n: count });
  }
  return t(`clients.v2.attention.${code}` as MessageKey);
}

export type StateView = { label: string; tone: "danger" | "warn" | "muted" | "positive"; more: string[] };

/** La columna «Estado»: archivado o en pausa, o el motivo más grave, o «Todo en orden». */
export function stateView(t: T, lifecycle: Lifecycle, attention: Attention | null, bag: Bag | null): StateView {
  if (lifecycle === "archived") return { label: t("clients.v2.lifecycle.archived"), tone: "muted", more: [] };
  if (lifecycle === "paused") return { label: t("clients.v2.lifecycle.paused"), tone: "warn", more: [] };
  const [top, ...rest] = attention?.reasons ?? [];
  if (!top) return { label: t("clients.v2.ok"), tone: "positive", more: [] };
  const tone = top.code === "no_balance" || top.code === "channel_problem" ? "danger" : "warn";
  return {
    label: reasonText(t, top.code, top.count, bag),
    tone,
    more: rest.map((r) => reasonText(t, r.code, r.count, bag)),
  };
}

/** Los días, redondeados como los dice el Panel («unos 4 días»). */
export function roundDays(days: number | null): number | null {
  return days == null ? null : Math.max(0, Math.round(days));
}

export function filterHref(filter: ClientFilter, q: string): string {
  const params = new URLSearchParams();
  if (filter !== "all") params.set("filter", filter);
  if (q.trim()) params.set("q", q.trim());
  const s = params.toString();
  return s ? `/clients?${s}` : "/clients";
}

export const FILTERS: readonly ClientFilter[] = ["all", "attention", "active", "archived"];

export function parseFilter(raw: string | undefined): ClientFilter {
  return (FILTERS as readonly string[]).includes(raw ?? "") ? (raw as ClientFilter) : "all";
}

/** Dónde lleva cada acción del menú que es un enlace. */
export function actionHref(action: ClientAction, ref: string): string | null {
  const r = encodeURIComponent(ref);
  switch (action) {
    case "assign_balance":
      return `/usage?client=${r}&assign=1`;
    case "request_balance":
      return `/usage?client=${r}&request=1`;
    case "new_agent":
      return `/clients/${r}/agents?new=1`;
    default:
      return null;
  }
}

/** El orden del menú ⋯ (requisito 7.6): lo que la API permite, en este orden. */
export const MENU_ORDER: readonly ClientAction[] = ["edit", "assign_balance", "request_balance", "new_agent", "archive", "restore", "delete"];

export function menuActions(allowed: readonly ClientAction[]): ClientAction[] {
  return MENU_ORDER.filter((a) => allowed.includes(a));
}

/** La sección de Negocio donde se arregla lo que falta. */
export function missingHref(ref: string, section: MissingSection): string {
  return `/clients/${encodeURIComponent(ref)}/business#${section}`;
}

/** Los códigos de error de la API que la consola sabe decir. */
const KNOWN_ERRORS = new Set([
  "archive_first",
  "name_mismatch",
  "legal_retention",
  "already_archived",
  "not_archived",
  "revision_conflict",
  "invalid_timezone",
  "bag_currency_locked",
]);

export function errorText(t: T, code: string | null | undefined): string {
  return code && KNOWN_ERRORS.has(code) ? t(`clients.v2.error.${code}` as MessageKey) : t("clients.v2.error.generic");
}
