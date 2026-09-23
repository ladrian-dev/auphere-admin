import type { MessageKey } from "@/i18n/messages";

type Failed = { ok: false; status: number; message: string; code?: string | null };
type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

/**
 * What to tell a person when a server action fails. ``message`` is the
 * backend's detail — good for a log, not for a partner — so a 403 says
 * "you cannot do this", anything that looks like our fault says "try
 * again", and only a plain 4xx (a validation the endpoint phrased for
 * humans) passes through.
 */
export function actionErrorText(res: Failed, t: T): string {
  if (res.status === 401 || res.status === 403) return t("common.forbidden");
  if (res.status === 0 || res.status >= 500) return t("common.error.backend");
  return res.message || t("common.error.backend");
}
