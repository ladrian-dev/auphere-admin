import type { AuditEntry } from "@/lib/backend";

/**
 * Spec 029: the audit as a table the partner reads, not a log it decodes.
 *
 * Two things happen here, both pure so they are tested without a browser:
 *
 * - **When, in words.** «Hoy, 09:12», «Ayer, 20:32» or «1 oct, 15:38», in
 *   the viewer's time zone.
 * - **Repeats folded.** Consecutive rows with the same person, action and
 *   client on the same day become one row with «N más como esta». Turning
 *   16 capabilities on in a row is one decision, and 16 identical lines
 *   pushed everything else off the screen.
 */
export type AuditRow = { item: AuditEntry; repeats: AuditEntry[] };

export type DayWords = { today: string; yesterday: string };

/** `YYYY-MM-DD` of an instant in a time zone. */
export function dayKey(at: string | Date, timeZone: string): string {
  const d = typeof at === "string" ? new Date(at) : at;
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

/** «Hoy, 09:12», «Ayer, 20:32», «1 oct, 15:38», or with the year when it is another one. */
export function whenLabel(at: string, now: Date, timeZone: string, locale: string, words: DayWords): string {
  const d = new Date(at);
  const key = dayKey(d, timeZone);
  const today = dayKey(now, timeZone);
  const time = new Intl.DateTimeFormat(locale, { timeZone, hour: "2-digit", minute: "2-digit" }).format(d);
  if (key === today) return `${words.today}, ${time}`;
  if (key === dayKey(new Date(now.getTime() - 86_400_000), timeZone)) return `${words.yesterday}, ${time}`;
  const sameYear = key.slice(0, 4) === today.slice(0, 4);
  const day = new Intl.DateTimeFormat(locale, { timeZone, day: "numeric", month: "short", ...(sameYear ? {} : { year: "numeric" }) })
    .format(d)
    .replace(".", "");
  return `${day}, ${time}`;
}

/**
 * Spec 073 (1.2): el día de una fila de grupo. «Hoy», «Ayer» o «jueves 1 oct»;
 * con el año solo si es otro.
 */
export function dayLabel(at: string, now: Date, timeZone: string, locale: string, words: DayWords): string {
  const d = new Date(at);
  const key = dayKey(d, timeZone);
  const today = dayKey(now, timeZone);
  if (key === today) return words.today;
  if (key === dayKey(new Date(now.getTime() - 86_400_000), timeZone)) return words.yesterday;
  const sameYear = key.slice(0, 4) === today.slice(0, 4);
  // Por partes: con el año, Intl en español escribe «24 de dic de 2025».
  const parts = new Intl.DateTimeFormat(locale, { timeZone, weekday: "long", day: "numeric", month: "short", year: "numeric" }).formatToParts(d);
  const part = (type: Intl.DateTimeFormatPartTypes) => (parts.find((p) => p.type === type)?.value ?? "").replaceAll(".", "");
  return [part("weekday"), part("day"), part("month"), sameYear ? "" : part("year")].filter(Boolean).join(" ");
}

/** Spec 073 (1.2): la hora sola, «09:12», en la zona de quien mira. */
export function timeLabel(at: string, timeZone: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { timeZone, hour: "2-digit", minute: "2-digit" }).format(new Date(at));
}

/** Spec 073 (1.2): las filas, juntas por día y en su orden. */
export function groupByDay(items: AuditEntry[], timeZone: string): { key: string; items: AuditEntry[] }[] {
  const out: { key: string; items: AuditEntry[] }[] = [];
  for (const item of items) {
    const key = dayKey(item.at, timeZone);
    const last = out.at(-1);
    if (last && last.key === key) last.items.push(item);
    else out.push({ key, items: [item] });
  }
  return out;
}

function sameKind(a: AuditEntry, b: AuditEntry): boolean {
  return a.actor === b.actor && a.action === b.action && a.external_client_ref === b.external_client_ref;
}

export function foldRepeats(items: AuditEntry[], timeZone: string): AuditRow[] {
  const rows: AuditRow[] = [];
  for (const item of items) {
    const last = rows.at(-1);
    if (last && sameKind(last.item, item) && dayKey(last.item.at, timeZone) === dayKey(item.at, timeZone)) last.repeats.push(item);
    else rows.push({ item, repeats: [] });
  }
  return rows;
}

/**
 * The sentence without the person who opens it, so the row can show that
 * person by name and in bold. A sentence that does not open with them (the
 * agent asked for a review, a machine renewed itself) is shown whole.
 */
export function splitActor(summary: string, actor: string): { lead: boolean; rest: string } {
  if (actor && summary.startsWith(`${actor} `)) return { lead: true, rest: summary.slice(actor.length + 1) };
  return { lead: false, rest: summary };
}

/** «Owner Demo» → «OD»; «ana@x.com» → «A». */
export function initials(name: string): string {
  const base = name.includes("@") ? (name.split("@")[0] ?? "") : name;
  const [first, second] = base.split(/[\s._-]+/).filter(Boolean);
  if (!first) return "?";
  if (name.includes("@")) return first.charAt(0).toUpperCase();
  return (first.charAt(0) + (second?.charAt(0) ?? "")).toUpperCase();
}

/**
 * The name to show for the person who did it. The API speaks in emails
 * («Companion · ana@x.com» when the Companion acted for Ana); the team list
 * knows their names.
 */
export function actorName(actor: string, people: Record<string, string>, fromApi?: string | null): string {
  // Spec 073 (1.4): la API ya sabe el nombre, también de las personas de los clientes.
  if (fromApi) return fromApi;
  const companion = actor.match(/^Companion · (.+)$/);
  const email = companion?.[1];
  if (email) return `Companion · ${people[email] ?? email}`;
  return people[actor] ?? actor;
}
