import { DAYS, type Day, type Hours, type HoursBody, type Layout, type ShiftOut } from "@/lib/backend/business-sections";
import { MAX_SHIFTS_PER_DAY, MINUTES_PER_DAY, checkDay, onStep, type RuleCode } from "@/lib/business-rules";

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

/** Spec 056: el de `lib/business-rules.ts`, el mismo que la API. */
export const MAX_SHIFTS = MAX_SHIFTS_PER_DAY;
const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;
const CLOSE = /^(([01]\d|2[0-3]):[0-5]\d|24:00)$/;

export type DraftShift = { key: string; open: string; close: string };
export type HoursDraft = { layout: Layout; days: Record<Day, DraftShift[]> };
export type DraftProblem = { day: Day; code: Extract<RuleCode, "too_many_shifts" | "invalid_time" | "bad_step" | "overlap" | "overlap_next_day"> };

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

/** Una fila de la lectura: un bloque o varios días seguidos con los mismos turnos. */
export type ReadRow = { key: "weekdays" | Day; days: Day[]; shifts: ShiftOut[] };

const sameOut = (a: readonly ShiftOut[], b: readonly ShiftOut[]) =>
  a.length === b.length && a.every((s, i) => s.open === b[i]?.open && s.close === b[i]?.close);

/**
 * La lectura del horario (prototipo aprobado): por bloques, sus tres filas; día
 * por día, los días seguidos iguales juntos. Si ningún día abre, no hay nada que
 * leer y la sección lo dice con su frase.
 */
export function readRows(hours: Pick<Hours, "layout" | "days">): ReadRow[] {
  if (!DAYS.some((d) => (hours.days[d] ?? []).length)) return [];
  const shiftsOf = (d: Day) => hours.days[d] ?? [];
  if ((hours.layout ?? "blocks") === "blocks") {
    return blockRows("blocks").map((row) => ({ ...row, shifts: shiftsOf(row.days[0] as Day) }));
  }
  const rows: ReadRow[] = [];
  for (const d of DAYS) {
    const last = rows[rows.length - 1];
    if (last && sameOut(last.shifts, shiftsOf(d))) last.days.push(d);
    else rows.push({ key: d, days: [d], shifts: shiftsOf(d) });
  }
  return rows;
}

/** «09:00 – 14:00 · 16:00 – 20:00»; un nocturno añade «(día siguiente)». */
export function shiftsText(shifts: readonly Pick<ShiftOut, "open" | "close">[], nextDay: string): string {
  return shifts.map((s) => `${s.open} – ${s.close}${isOvernight(s.open, s.close) ? ` ${nextDay}` : ""}`).join(" · ");
}

/** Los turnos de una fila en todos sus días (los bloques comparten turnos). */
export function setRow(draft: HoursDraft, row: Row, shifts: DraftShift[]): HoursDraft {
  const days = { ...draft.days };
  row.days.forEach((d, i) => {
    days[d] = i === 0 ? shifts : shifts.map((s) => ({ ...s, key: newKey() }));
  });
  return { ...draft, days };
}

const sameDay = (a: readonly Pick<ShiftOut, "open" | "close">[], b: readonly DraftShift[]) =>
  a.length === b.length && a.every((s, i) => s.open === b[i]?.open && s.close === b[i]?.close);

/** Un turno en minutos desde la medianoche del día que abre (la regla de la API). */
function span(s: DraftShift): [number, number] {
  const o = toMin(s.open);
  if (s.close === "24:00") return [o, MINUTES_PER_DAY];
  const c = toMin(s.close);
  return [o, c <= o ? c + MINUTES_PER_DAY : c];
}

/**
 * Lo que el borrador no puede guardar, día a día. Spec 056 (5.1, 5.5): las
 * reglas de `lib/business-rules.ts` (las de la API y las de Reservas), pero las
 * estrictas —pasos de 5 minutos, sin solapes— solo en los días que cambian
 * respecto a `original`: lo guardado de antes se queda como está («Revísalo»)
 * mientras nadie toque su día. Sin `original`, todos cuentan como cambiados.
 */
export function validateDraft(draft: HoursDraft, original?: Pick<Hours, "days">): DraftProblem[] {
  const out: DraftProblem[] = [];
  for (const d of DAYS) {
    const shifts = draft.days[d];
    if (shifts.length > MAX_SHIFTS) out.push({ day: d, code: "too_many_shifts" });
    else if (shifts.some((s) => !HHMM.test(s.open) || !CLOSE.test(s.close))) out.push({ day: d, code: "invalid_time" });
    else if (!original || !sameDay(original.days[d] ?? [], shifts)) {
      const checked = checkDay(shifts, d);
      if (!checked.ok) out.push({ day: d, code: checked.problem.code as DraftProblem["code"] });
    }
  }
  if (out.length) return out;
  // Un nocturno no pisa el primer turno del día siguiente; el domingo sigue en el lunes.
  DAYS.forEach((d, i) => {
    const spill = Math.max(0, ...draft.days[d].map(span).map(([, c]) => c - MINUTES_PER_DAY));
    const next = draft.days[DAYS[(i + 1) % DAYS.length] as Day].map(span).sort((a, b) => a[0] - b[0]);
    if (spill > 0 && next[0] && next[0][0] < spill) out.push({ day: d, code: "overlap_next_day" });
  });
  return out;
}

export function bodyFromDraft(draft: HoursDraft, opts: { confirmLoss?: boolean } = {}): HoursBody {
  const days = {} as Record<Day, { open: string; close: string }[]>;
  for (const d of DAYS) days[d] = draft.days[d].map((s) => ({ open: s.open, close: s.close }));
  return { layout: draft.layout, days, ...(opts.confirmLoss ? { confirm_loss: true } : {}) };
}

/**
 * «Revísalo» (spec 056, 5.5): los días con una hora fuera del paso de 5 minutos.
 * La API aceptaba cualquier minuto; lo guardado se enseña tal cual y se queda así
 * hasta que alguien cambie ese día. 24:00 cierra el día y está en el paso.
 */
export function reviewDays(hours: Pick<Hours, "days">): Day[] {
  const off = (hhmm: string) => !onStep(Math.min(toMin(hhmm), MINUTES_PER_DAY));
  return DAYS.filter((d) => (hours.days[d] ?? []).some((s) => off(s.open) || off(s.close)));
}
