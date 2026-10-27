import { DAYS, type Day, type Hours, type HoursBody, type Layout } from "@/lib/backend/business-sections";

/**
 * El modelo del editor del horario — spec 047 (T060, requisito 10). Puro: lo
 * prueban `hours-model.test.ts` y lo usa `hours-section.tsx`.
 *
 * - **Por bloques** (lunes a viernes, sábado, domingo) o **día por día**.
 * - Hasta {@link MAX_SHIFTS} turnos por día; un día sin turnos está cerrado.
 * - Un cierre igual o anterior a la apertura es del día siguiente: «Nocturno ·
 *   cierra al día siguiente». Las 00:00 o las 24:00 de cierre son medianoche, y
 *   de 00:00 a 24:00, abierto 24 horas (la misma regla que la API).
 * - Pasar de día por día a bloques usa los turnos del lunes de lunes a viernes:
 *   {@link blocksLoss} dice qué días se perderían, para pedir confirmación (10.6).
 */

export const MAX_SHIFTS = 6;
const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;
const CLOSE = /^(([01]\d|2[0-3]):[0-5]\d|24:00)$/;

export type DraftShift = { key: string; open: string; close: string };
export type HoursDraft = { layout: Layout; days: Record<Day, DraftShift[]> };
export type DraftProblem = { day: Day; code: "too_many_shifts" | "invalid_time" };

const toMin = (hhmm: string) => {
  const [h, m] = hhmm.split(":").map(Number);
  return (h ?? 0) * 60 + (m ?? 0);
};

/** «Nocturno · cierra al día siguiente». */
export function isOvernight(open: string, close: string): boolean {
  if (close === "24:00" || !HHMM.test(open) || !HHMM.test(close)) return false;
  const c = toMin(close);
  return c > 0 && c <= toMin(open);
}

let seq = 0;
export function newKey(): string {
  seq += 1;
  return `s${seq}`;
}

export function emptyDays(): Record<Day, DraftShift[]> {
  return { mon: [], tue: [], wed: [], thu: [], fri: [], sat: [], sun: [] };
}

export function draftFromHours(hours: Pick<Hours, "layout" | "days">): HoursDraft {
  const days = emptyDays();
  for (const d of DAYS) days[d] = (hours.days[d] ?? []).map((s) => ({ key: newKey(), open: s.open, close: s.close }));
  return { layout: hours.layout ?? "blocks", days };
}

const same = (a: readonly DraftShift[], b: readonly DraftShift[]) =>
  a.length === b.length && a.every((s, i) => s.open === b[i]?.open && s.close === b[i]?.close);

/** Los días de martes a viernes que no tienen los turnos del lunes. */
export function blocksLoss(draft: HoursDraft): Day[] {
  return (["tue", "wed", "thu", "fri"] as const).filter((d) => !same(draft.days[d], draft.days.mon));
}

/** «Por bloques»: de lunes a viernes, los turnos del lunes. */
export function toBlocks(draft: HoursDraft): HoursDraft {
  const copy = (list: DraftShift[]) => list.map((s) => ({ ...s, key: newKey() }));
  const days = { ...draft.days };
  for (const d of ["tue", "wed", "thu", "fri"] as const) days[d] = copy(draft.days.mon);
  return { layout: "blocks", days };
}

/** Una fila del editor: un bloque (varios días) o un día. */
export type Row = { key: "weekdays" | Day; days: Day[] };

export function blockRows(layout: Layout): Row[] {
  if (layout === "blocks") {
    return [
      { key: "weekdays", days: ["mon", "tue", "wed", "thu", "fri"] },
      { key: "sat", days: ["sat"] },
      { key: "sun", days: ["sun"] },
    ];
  }
  return DAYS.map((d) => ({ key: d, days: [d] }));
}

/** Los turnos de una fila en todos sus días (los bloques comparten turnos). */
export function setRow(draft: HoursDraft, row: Row, shifts: DraftShift[]): HoursDraft {
  const days = { ...draft.days };
  row.days.forEach((d, i) => {
    days[d] = i === 0 ? shifts : shifts.map((s) => ({ ...s, key: newKey() }));
  });
  return { ...draft, days };
}

export function validateDraft(draft: HoursDraft): DraftProblem[] {
  const out: DraftProblem[] = [];
  for (const d of DAYS) {
    const shifts = draft.days[d];
    if (shifts.length > MAX_SHIFTS) out.push({ day: d, code: "too_many_shifts" });
    else if (shifts.some((s) => !HHMM.test(s.open) || !CLOSE.test(s.close))) out.push({ day: d, code: "invalid_time" });
  }
  return out;
}

export function bodyFromDraft(draft: HoursDraft, opts: { confirmLoss?: boolean } = {}): HoursBody {
  const days = {} as Record<Day, { open: string; close: string }[]>;
  for (const d of DAYS) days[d] = draft.days[d].map((s) => ({ open: s.open, close: s.close }));
  return { layout: draft.layout, days, ...(opts.confirmLoss ? { confirm_loss: true } : {}) };
}
