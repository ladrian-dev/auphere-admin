import type { MessageKey } from "@/i18n/messages";

type Failed = { ok: false; status: number; message: string; code?: string | null };
type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

/**
 * Codes whose sentence the console writes, whatever the status (spec 047,
 * amendment of 2026-10-30; `contracts/console-api.md` §11). They reach the
 * screens of before that still use this function: the draft save bar
 * (`structured_agent`) and the old ways of starting an agent from a template
 * (`seed_template_retired`).
 */
const WORDED: Readonly<Record<string, MessageKey>> = {
  structured_agent: "common.error.structured_agent",
  seed_template_retired: "common.error.seed_template_retired",
  facts_unavailable: "common.error.facts_unavailable",
};

/**
 * What to tell a person when a server action fails. ``message`` is the
 * backend's detail — good for a log, not for a partner — so a 403 says
 * "you cannot do this", anything that looks like our fault says "try
 * again", and only a plain 4xx (a validation the endpoint phrased for
 * humans) passes through. A code the console has words for wins.
 */
export function actionErrorText(res: Failed, t: T): string {
  const worded = res.code ? WORDED[res.code] : undefined;
  if (worded) return t(worded);
  if (res.status === 401 || res.status === 403) return t("common.forbidden");
  if (res.status === 0 || res.status >= 500) return t("common.error.backend");
  return res.message || t("common.error.backend");
}
