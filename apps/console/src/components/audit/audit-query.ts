/**
 * Spec 029: the audit filters as they live in the URL, and the API query
 * they become. Kept out of the "use client" filter bar on purpose: a value
 * exported from a client module reaches a server component as a reference,
 * not as the value.
 */
export const PERIODS = [7, 30, 90] as const;

export type AuditFilterState = { client: string; actor: string; category: string; days: string; after: string; before: string };

const DAY = /^\d{4}-\d{2}-\d{2}$/;

export function readFilters(sp: Partial<Record<keyof AuditFilterState, string>>): AuditFilterState {
  return {
    client: sp.client ?? "",
    actor: sp.actor ?? "",
    category: sp.category ?? "",
    days: sp.days === "custom" || PERIODS.some((d) => String(d) === sp.days) ? (sp.days ?? "") : "",
    after: sp.after && DAY.test(sp.after) ? sp.after : "",
    before: sp.before && DAY.test(sp.before) ? sp.before : "",
  };
}

/** A period in days counts back from `now`; custom dates are whole UTC days. */
export function auditQuery(state: AuditFilterState, now: Date): Record<string, string> {
  const days = Number(state.days);
  const custom = state.days === "custom";
  const after = days > 0 ? new Date(now.getTime() - days * 86_400_000).toISOString() : custom && state.after ? `${state.after}T00:00:00Z` : "";
  const before = custom && state.before ? `${state.before}T23:59:59Z` : "";
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries({ client: state.client, actor: state.actor, category: state.category, after, before })) if (v) out[k] = v;
  return out;
}
