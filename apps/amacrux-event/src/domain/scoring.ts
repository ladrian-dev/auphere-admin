import type { Goal, IntentLevel, Investment, LeadTier, ScoreRange, TechCapacity, Urgency, WorkLevel } from "./enums";
import { realFrictions } from "./segmentation";
import type { Answers, Score, ScoreBreakdown, Segment } from "./types";

/** Pesos del brief. Las tablas se exportan para que los tests las citen. */
export const URGENCY_POINTS: Record<Urgency, number> = { explorar: 3, proximos_meses: 8, pronto: 12, inmediato: 15 };
export const CAPACITY_POINTS: Record<TechCapacity, number> = { sin_equipo: 4, limitado: 8, interno: 12, especializado: 15 };
export const INVESTMENT_POINTS: Record<Investment, number> = { explorar: 3, prueba: 8, proyecto: 12, estrategico: 15 };
export const WORK_LEVEL_POINTS: Record<WorkLevel, number> = { inicial: 2, explorando: 4, adoptando: 6, avanzado: 8, escalando: 10 };
export const INTENT_POINTS: Record<IntentLevel, number> = { baja: 2, media: 5, alta: 8, muy_alta: 10 };
export const GOAL_IMPACT: Record<Goal, number> = {
  ahorrar_tiempo: 8, reducir_costes: 8, aumentar_ventas: 9, escalar: 9, mejorar_atencion: 7, productividad: 7,
  datos: 6, decisiones: 6, acelerar_desarrollo: 7, calidad_producto: 6, reducir_errores: 7, nuevos_servicios: 6,
};
const HIGH_VOLUME_FRICTIONS = new Set(["atencion_cliente", "operaciones_logistica", "ventas_leads"]);

const clamp = (n: number, min: number, max: number) => Math.max(min, Math.min(max, n));

export function rangeFor(total: number): ScoreRange {
  if (total >= 75) return "alta_intencion";
  if (total >= 55) return "oportunidad_prioritaria";
  if (total >= 30) return "oportunidad_inicial";
  return "exploracion";
}

export function tierFor(range: ScoreRange): LeadTier {
  return ({ exploracion: "frio", oportunidad_inicial: "tibio", oportunidad_prioritaria: "caliente", alta_intencion: "muy_caliente" } as const)[range];
}

export function scoreAnswers(a: Answers, segment: Segment): Score {
  const real = realFrictions(a).length;
  const clarityBase = real === 0 ? 4 : real === 1 ? 12 : real === 2 ? 17 : 20;
  const problemClarity = clamp(clarityBase - (a.goals.length === 0 ? 3 : 0), 0, 20);

  const goalPoints = a.goals.slice(0, 2).reduce((acc, g) => acc + GOAL_IMPACT[g], 0);
  const sizeBonus = a.teamSize === "51_200" ? 2 : a.teamSize === "200_plus" ? 3 : 0;
  const volumeBonus = a.frictions.filter((f) => HIGH_VOLUME_FRICTIONS.has(f)).length;
  const impact = clamp(goalPoints + sizeBonus + volumeBonus, 0, 20);

  const urgency = URGENCY_POINTS[a.urgency];
  const capacity = clamp(Math.round(CAPACITY_POINTS[a.techCapacity] * 0.6 + INVESTMENT_POINTS[a.investment] * 0.4), 0, 15);

  const dataAdjust = a.dataLocation === "papel_chat" ? -2 : a.dataLocation === "centralizada" ? 2 : 0;
  const maturity = clamp(WORK_LEVEL_POINTS[a.workLevel] + dataAdjust, 0, 10);

  const cats = segment.opportunityCategories.length;
  const fitBase = cats === 0 ? 0 : cats === 1 ? 6 : cats === 2 ? 8 : 10;
  const onlyOther = a.frictions.length > 0 && real === 0;
  const fit = clamp(fitBase - (onlyOther ? 4 : 0), 0, 10);

  const intent = INTENT_POINTS[segment.intent];

  const breakdown: ScoreBreakdown = { problemClarity, impact, urgency, capacity, maturity, fit, intent };
  const total = Object.values(breakdown).reduce((x, y) => x + y, 0);
  const range = rangeFor(total);
  return { total, range, breakdown, leadTier: tierFor(range) };
}
