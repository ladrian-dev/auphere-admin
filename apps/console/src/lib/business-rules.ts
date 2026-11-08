import type { Day, PriceKind } from "@/lib/backend/business-sections";

/**
 * Las reglas del horario y de los servicios — spec 056 (requisito 5, research R5).
 *
 * La ficha del partner y los Ajustes de Reservas del cliente aceptan y rechazan
 * **los mismos** valores, los edite quien los edite (5.1, 5.2):
 *
 * - de 0 a 6 turnos por día; sin turnos, cerrado;
 * - horas `HH:MM` en pasos de 5 minutos, con 24:00 solo como cierre;
 * - un cierre igual o anterior a la apertura es del día siguiente, sin solapes,
 *   tampoco con el primer turno del día siguiente (el domingo sigue en el lunes);
 * - duración de 5 a 480 minutos, en pasos de 5;
 * - precio sin precio, gratis o un importe; gratis no guarda importe;
 * - importe entero en unidades menores, de 0 a 10¹²;
 * - categoría de 40 caracteres como máximo y nombre de 1 a 120, con los
 *   espacios colapsados.
 *
 * Espejo de la API: `apps/api/src/nexus_api/services/business/rules.py`. Un
 * cambio aquí va con el suyo allí en el mismo commit; las dos pruebas fijan los
 * mismos casos (`lib/__tests__/business-rules.test.ts` y
 * `apps/api/tests/unit/test_business_rules.py`). Los códigos de error son los
 * de la API, para traducir los dos con la misma tabla. Puro: sin React ni API.
 */

export const WEEK_DAYS: readonly Day[] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
/** Las horas son minutos desde la medianoche del día que abre: un nocturno cierra pasado 1440. */
export const MINUTES_PER_DAY = 1440;
export const MAX_SHIFTS_PER_DAY = 6;
export const TIME_STEP = 5;
export const DURATION_MIN = 5;
export const DURATION_MAX = 480;
export const DURATION_STEP = 5;
export const PRICE_KINDS: readonly PriceKind[] = ["none", "free", "amount"];
/** Con 10⁹, diez millones de pesos colombianos (en céntimos) serían el tope. */
export const AMOUNT_MAX_MINOR = 10 ** 12;
export const CATEGORY_MAX = 40;
export const NAME_MIN = 1;
export const NAME_MAX = 120;

export type RuleCode =
  | "invalid_time"
  | "bad_step"
  | "too_many_shifts"
  | "overlap"
  | "overlap_next_day"
  | "invalid_day"
  | "bad_duration"
  | "price_invalid"
  | "price_amount_required"
  | "amount_too_large"
  | "category_too_long"
  | "name_required"
  | "name_too_long";
export type RuleProblem = { code: RuleCode; field: string; day?: string };
export type Checked<V> = { ok: true; value: V } | { ok: false; problem: RuleProblem };
/** Un turno en minutos desde la medianoche del día que abre. */
export type ShiftMinutes = [open: number, close: number];
export type ShiftText = { open: string; close: string };

const HHMM = /^([01]\d|2[0-3]):([0-5]\d)$/;
const END_OF_DAY = "24:00";

const ok = <V>(value: V): Checked<V> => ({ ok: true, value });
const fail = (code: RuleCode, field: string, day?: string): { ok: false; problem: RuleProblem } => ({
  ok: false,
  problem: { code, field, ...(day ? { day } : {}) },
});

// ── las horas ──────────────────────────────────────────────────────────────

/** ¿Cae en el paso de 5 minutos? Lo que no, se enseña marcado «Revísalo» (5.5). */
export function onStep(minutes: number): boolean {
  return minutes % TIME_STEP === 0;
}

/** `HH:MM` → minutos desde la medianoche. 24:00 solo vale como cierre. */
export function timeMinutes(raw: string, opts: { closing?: boolean; day?: string } = {}): Checked<number> {
  const field = opts.closing ? "close" : "open";
  if (opts.closing && raw === END_OF_DAY) return ok(MINUTES_PER_DAY);
  const m = HHMM.exec(raw);
  if (!m) return fail("invalid_time", field, opts.day);
  const minutes = Number(m[1]) * 60 + Number(m[2]);
  return onStep(minutes) ? ok(minutes) : fail("bad_step", field, opts.day);
}

/**
 * Un turno en minutos. Un cierre igual o anterior a la apertura es del día
 * siguiente; de 00:00 a 24:00 (o a 00:00), 24 horas. La regla de la API.
 */
export function shiftMinutes(open: string, close: string, day?: string): Checked<ShiftMinutes> {
  const o = timeMinutes(open, { day });
  if (!o.ok) return o;
  const c = timeMinutes(close, { closing: true, day });
  if (!c.ok) return c;
  if (c.value === MINUTES_PER_DAY) return ok([o.value, c.value]);
  return ok([o.value, c.value <= o.value ? c.value + MINUTES_PER_DAY : c.value]);
}

/** Los turnos de un día, en orden: de 0 a 6 y sin solapes. Que uno empiece cuando cierra el anterior vale. */
export function checkDay(shifts: readonly ShiftText[], day?: string): Checked<ShiftMinutes[]> {
  if (shifts.length > MAX_SHIFTS_PER_DAY) return fail("too_many_shifts", "shifts", day);
  const out: ShiftMinutes[] = [];
  for (const s of shifts) {
    const one = shiftMinutes(s.open, s.close, day);
    if (!one.ok) return one;
    out.push(one.value);
  }
  out.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  for (let i = 1; i < out.length; i++) if (out[i]![0] < out[i - 1]![1]) return fail("overlap", "shifts", day);
  return ok(out);
}

/**
 * La semana entera; un día que no está, cerrado. Además de cada día, un nocturno
 * no puede pisar el primer turno del día siguiente, y el domingo sigue en el lunes.
 */
export function checkWeek(days: Readonly<Record<string, readonly ShiftText[] | undefined>>): Checked<Record<Day, ShiftMinutes[]>> {
  for (const key of Object.keys(days)) if (!(WEEK_DAYS as readonly string[]).includes(key)) return fail("invalid_day", "days", key);
  const week = {} as Record<Day, ShiftMinutes[]>;
  for (const d of WEEK_DAYS) {
    const one = checkDay(days[d] ?? [], d);
    if (!one.ok) return one;
    week[d] = one.value;
  }
  for (const [i, d] of WEEK_DAYS.entries()) {
    const spill = Math.max(0, ...week[d].filter(([, c]) => c > MINUTES_PER_DAY).map(([, c]) => c - MINUTES_PER_DAY));
    const next = week[WEEK_DAYS[(i + 1) % WEEK_DAYS.length]!];
    if (spill && next[0] && next[0][0] < spill) return fail("overlap_next_day", "shifts", d);
  }
  return ok(week);
}

// ── los servicios ──────────────────────────────────────────────────────────

export function durationOk(minutes: number): boolean {
  return Number.isInteger(minutes) && minutes >= DURATION_MIN && minutes <= DURATION_MAX && minutes % DURATION_STEP === 0;
}

export function checkDuration(minutes: number): Checked<number> {
  return durationOk(minutes) ? ok(minutes) : fail("bad_duration", "duration_min");
}

/** El importe que se guarda: solo con `amount`. Gratis y sin precio no guardan importe. */
export function checkPrice(kind: string, amountMinor: number | null | undefined): Checked<number | null> {
  if (!(PRICE_KINDS as readonly string[]).includes(kind)) return fail("price_invalid", "price");
  if (kind !== "amount") return ok(null);
  if (amountMinor == null) return fail("price_amount_required", "price");
  if (!Number.isInteger(amountMinor) || amountMinor < 0) return fail("price_invalid", "price");
  if (amountMinor > AMOUNT_MAX_MINOR) return fail("amount_too_large", "price");
  return ok(amountMinor);
}

const collapsed = (value: string | null | undefined) => (value ?? "").split(/\s+/).filter(Boolean).join(" ");

/** Recortada y con los espacios de dentro colapsados; vacía es ninguna. */
export function checkCategory(value: string | null | undefined): Checked<string | null> {
  const category = collapsed(value) || null;
  return category && category.length > CATEGORY_MAX ? fail("category_too_long", "category") : ok(category);
}

export function checkName(value: string | null | undefined): Checked<string> {
  const name = collapsed(value);
  if (name.length < NAME_MIN) return fail("name_required", "name");
  if (name.length > NAME_MAX) return fail("name_too_long", "name");
  return ok(name);
}
