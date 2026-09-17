/**
 * Etiquetas legibles y frases del resultado. Sin cifras de ahorro ni
 * garantías (spec Req. 5.8). Los textos marcados TODO_COMERCIAL en
 * comentarios quedan pendientes de validación por Amacrux.
 */
import type {
  Complexity, Confidence, Friction, Goal, IntentLevel, MaturitySegment, OpportunityCategory, ProfileSegment, ScoreRange, Sector,
} from "./enums";
import { optionLabel } from "./questions";
import type { Answers, Recommendation, Segment } from "./types";

export const frictionLabel = (f: Friction): string => optionLabel("frictions", f);
export const goalLabel = (g: Goal): string => optionLabel("goals", g);
export const sectorLabel = (s: Sector): string => (s === "otro" ? "Tu sector" : optionLabel("sector", s));

export const PROFILE_SEGMENT_LABELS: Record<ProfileSegment, string> = {
  decisor_negocio: "Decisión de negocio",
  operaciones: "Operaciones",
  tecnologico: "Tecnología e innovación",
  ingenieria: "Ingeniería de software",
  producto_innovacion: "Producto e innovación",
  marketing_ventas: "Marketing y ventas",
  consultor_independiente: "Consultoría o profesional independiente",
};

/** Visible al usuario: nunca dice "madurez". */
export const MATURITY_LABELS: Record<MaturitySegment, string> = {
  explorador: "Explorando posibilidades",
  inicial: "Primeros pasos con la automatización",
  en_adopcion: "Adoptando herramientas",
  integrador: "Conectando sistemas y procesos",
  escalador: "Escalando con robustez",
};

export const CATEGORY_LABELS: Record<OpportunityCategory, string> = {
  automatizacion_operativa: "Automatización operativa",
  ia_conocimiento_soporte: "IA para conocimiento y soporte",
  automatizacion_comercial: "Automatización comercial",
  procesamiento_documental: "Procesamiento documental",
  datos_reporting: "Datos y reporting",
  ia_desarrollo: "IA para desarrollo de software",
  integraciones_orquestacion: "Integraciones y orquestación",
  producto_digital: "Optimización de producto digital",
};

const CATEGORY_PHRASES: Record<OpportunityCategory, string> = {
  automatizacion_operativa: "reducir el trabajo manual y repetitivo del día a día",
  ia_conocimiento_soporte: "responder más rápido y con menos esfuerzo a solicitudes y consultas",
  automatizacion_comercial: "quitar fricción al proceso comercial, desde el primer contacto hasta la propuesta",
  procesamiento_documental: "dejar de teclear lo que ya está escrito en documentos, correos y formularios",
  datos_reporting: "tener los datos ordenados y los informes listos sin trabajo manual",
  ia_desarrollo: "acelerar el desarrollo y el mantenimiento de software con IA en el flujo del equipo",
  integraciones_orquestacion: "conectar las herramientas para que la información fluya sin copiarla a mano",
  producto_digital: "incorporar IA a tu producto digital donde más valor aporta a quien lo usa",
};

export const RANGE_LABELS: Record<ScoreRange, string> = {
  exploracion: "Explorando",
  oportunidad_inicial: "Inicial",
  oportunidad_prioritaria: "Prioritaria",
  alta_intencion: "Alta",
};

export const RANGE_DESCRIPTIONS: Record<ScoreRange, string> = {
  exploracion: "Buen momento para entender qué es posible antes de comprometer recursos.",
  oportunidad_inicial: "Hay señales claras: un primer piloto pequeño puede demostrar valor.",
  oportunidad_prioritaria: "Las piezas encajan: problema claro, objetivo definido y capacidad para empezar.",
  alta_intencion: "Urgencia, presupuesto y problema definido: conviene concretar un piloto cuanto antes.",
};

export const CONFIDENCE_LABELS: Record<Confidence, string> = {
  orientativo: "Orientativo",
  relevante: "Relevante",
  prioritario: "Prioritario",
};

export const COMPLEXITY_LABELS: Record<Complexity, string> = {
  quick_win: "Quick win",
  piloto_baja: "Piloto de baja complejidad",
  proyecto_integracion: "Proyecto de integración",
  transformacion_proceso: "Transformación de proceso",
  solucion_estrategica: "Solución estratégica",
};

export const TECH_COMPLEXITY_LABELS: Record<1 | 2 | 3 | 4 | 5, string> = {
  1: "Muy baja",
  2: "Baja",
  3: "Media",
  4: "Alta",
  5: "Muy alta",
};

/** CTA único decidido por el usuario (2026-09-16). La intención sigue viajando para analítica y correo. */
export const CTA_LABEL = "Solicita una DEMO";

export function ctaFor(intent: IntentLevel): { label: string; intent: IntentLevel } {
  return { label: CTA_LABEL, intent };
}

function joinNatural(items: string[]): string {
  if (items.length <= 1) return items[0] ?? "";
  return `${items.slice(0, -1).join(", ")} y ${items[items.length - 1]}`;
}

export function buildIntro(a: Answers, segment: Segment, top: Recommendation): string {
  const phrase = CATEGORY_PHRASES[top.opportunity.category];
  const cited = top.matchedFrictions.slice(0, 2).map((f) => frictionLabel(f).toLowerCase());
  const goals = a.goals.slice(0, 2).map((g) => goalLabel(g).toLowerCase());
  const base = `Por lo que nos cuentas, el mayor potencial parece estar en ${phrase}`;
  const because = cited.length > 0 ? `, sobre todo en ${joinNatural(cited)}` : "";
  const aim = goals.length > 0 ? `. Lo que buscas primero es ${joinNatural(goals)}, y las tres oportunidades de abajo apuntan a eso.` : ".";
  const stage = segment.maturity === "explorador" ? " Como todavía estás explorando, hemos priorizado pasos pequeños que se pueden probar sin comprometer recursos." : "";
  return `${base}${because}${aim}${stage}`;
}

export function buildShortTerm(top: Recommendation): string {
  return `Empezar por «${top.opportunity.title}». ${top.opportunity.recommendedFirstStep} Un primer piloto suele llevar ${top.opportunity.expectedTimeToPilot.toLowerCase()}.`;
}

export function buildMidTerm(second: Recommendation, third: Recommendation, segment: Segment): string {
  const link = segment.maturity === "integrador" || segment.maturity === "escalador"
    ? "Con la base conectada, "
    : "Cuando el primer piloto funcione, ";
  return `${link}seguir con «${second.opportunity.title}» y valorar «${third.opportunity.title}». Conviene medir el primer piloto antes de ampliar el alcance.`;
}

export function buildWarnings(a: Answers, segment: Segment, recs: Recommendation[]): string[] {
  const out: string[] = [];
  if (a.dataLocation === "papel_chat") out.push("Parte de la información vive en papel, correos o chats: el primer paso será ordenarla y digitalizarla; sin eso, automatizar no funciona.");
  if (a.dataLocation === "hojas_calculo") out.push("Los datos en hojas de cálculo sirven para empezar, pero habrá que validar su calidad y quién los mantiene.");
  if (a.techCapacity === "sin_equipo") out.push("Sin equipo técnico interno, conviene elegir soluciones con poco mantenimiento y acordar quién las opera.");
  if (segment.maturity === "explorador" || segment.maturity === "inicial") out.push("Antes de un piloto hay que validar volumen real, sistemas actuales y quién decide; estas recomendaciones son orientativas.");
  if (a.aiUsage === "no") out.push("Si es el primer uso de IA en la empresa, definir unas normas mínimas de uso (qué datos se comparten y con qué herramientas) evita sorpresas.");
  for (const r of recs) for (const w of r.warnings) if (!out.includes(w)) out.push(w);
  return out.slice(0, 5);
}

export function reasonsFor(rec: { matchedFrictions: Friction[]; matchedGoals: Goal[] }, segment: Segment, profileMatch: boolean): string[] {
  const reasons: string[] = [];
  if (rec.matchedFrictions.length > 0) reasons.push(`Porque marcaste ${joinNatural(rec.matchedFrictions.map((f) => frictionLabel(f).toLowerCase()))}.`);
  if (rec.matchedGoals.length > 0) reasons.push(`Encaja con tu objetivo de ${joinNatural(rec.matchedGoals.map((g) => goalLabel(g).toLowerCase()))}.`);
  if (profileMatch) reasons.push(`Es habitual en perfiles de ${PROFILE_SEGMENT_LABELS[segment.profile].toLowerCase()}.`);
  if (reasons.length === 0) reasons.push("Es un punto de partida frecuente para empresas en tu situación y se puede probar con poco riesgo.");
  return reasons;
}
