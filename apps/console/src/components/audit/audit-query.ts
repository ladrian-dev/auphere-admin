/**
 * Spec 029: the audit filters as they live in the URL, and the API query
 * they become. Kept out of the "use client" filter bar on purpose: a value
 * exported from a client module reaches a server component as a reference,
 * not as the value.
 */
export const PERIODS = [7, 30, 90] as const;

export type AuditFilterState = { client: string; actor: string; category: string; days: string; after: string; before: string };

const DAY = /^\d{4}-\d{2}-\d{2}$/;

export function readFilters(sp: Partial<Record<keyof AuditFilterState | "person", string>>): AuditFilterState {
  return {
    client: sp.client ?? "",
    // Spec 047 (49.1): `person` en la URL, como en la API; `actor` sigue valiendo.
    actor: sp.person ?? sp.actor ?? "",
    category: sp.category ?? "",
    days: sp.days === "custom" || PERIODS.some((d) => String(d) === sp.days) ? (sp.days ?? "") : "",
    after: sp.after && DAY.test(sp.after) ? sp.after : "",
    before: sp.before && DAY.test(sp.before) ? sp.before : "",
  };
}

/**
 * Spec 047 (49.1): the API takes the period (`days=7|30|90`) and the person
 * (`person`) itself; custom dates are whole UTC days. «Todo» sends no period.
 * `now` is kept for callers that still pass it.
 */
export function auditQuery(state: AuditFilterState, now?: Date): Record<string, string> {
  void now;
  const custom = state.days === "custom";
  const days = PERIODS.some((d) => String(d) === state.days) ? state.days : "";
  const after = custom && state.after ? `${state.after}T00:00:00Z` : "";
  const before = custom && state.before ? `${state.before}T23:59:59Z` : "";
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries({ client: state.client, person: state.actor, category: state.category, days, after, before })) if (v) out[k] = v;
  return out;
}

/**
 * «{n} más como esta»: la consulta que trae las filas que la API juntó en una,
 * sin juntar (`group=false`): la misma persona, acción y cliente, ese día (UTC).
 */
export function moreLikeThisQuery(item: { actor: string; action: string; external_client_ref: string | null; at: string }): Record<string, string> {
  const day = item.at.slice(0, 10);
  const out: Record<string, string> = { group: "false", person: item.actor, action: item.action, after: `${day}T00:00:00Z`, before: `${day}T23:59:59Z`, limit: "200" };
  if (item.external_client_ref) out.client = item.external_client_ref;
  return out;
}
