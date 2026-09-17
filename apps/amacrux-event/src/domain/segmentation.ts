import type {
  Complexity, Friction, Goal, IntentLevel, MaturitySegment, OpportunityCategory, ProfileSegment, WorkLevel,
} from "./enums";
import { OPPORTUNITY_CATEGORIES, WORK_LEVELS } from "./enums";
import type { Answers, Segment } from "./types";

/** Señales fricción → categorías (la primera es la principal). */
export const FRICTION_CATEGORIES: Record<Friction, OpportunityCategory[]> = {
  tareas_manuales: ["automatizacion_operativa"],
  copiar_datos: ["integraciones_orquestacion", "automatizacion_operativa"],
  operaciones_logistica: ["automatizacion_operativa"],
  planificacion_equipos: ["automatizacion_operativa"],
  sin_tiempo_innovar: ["automatizacion_operativa"],
  emails_solicitudes: ["ia_conocimiento_soporte", "automatizacion_operativa"],
  atencion_cliente: ["ia_conocimiento_soporte"],
  soporte_interno: ["ia_conocimiento_soporte"],
  busqueda_interna: ["ia_conocimiento_soporte"],
  ventas_leads: ["automatizacion_comercial"],
  presupuestos: ["automatizacion_comercial"],
  documental: ["procesamiento_documental"],
  extraccion_datos: ["procesamiento_documental"],
  reporting: ["datos_reporting"],
  visibilidad_datos: ["datos_reporting"],
  desarrollo_software: ["ia_desarrollo"],
  testing_qa: ["ia_desarrollo"],
  documentacion_tecnica: ["ia_desarrollo"],
  otro: [],
};

export const GOAL_CATEGORIES: Partial<Record<Goal, OpportunityCategory[]>> = {
  acelerar_desarrollo: ["ia_desarrollo"],
  calidad_producto: ["producto_digital"],
  nuevos_servicios: ["producto_digital"],
  datos: ["datos_reporting"],
  aumentar_ventas: ["automatizacion_comercial"],
  mejorar_atencion: ["ia_conocimiento_soporte"],
};

export function realFrictions(a: Answers): Friction[] {
  return a.frictions.filter((f) => f !== "otro");
}

export function profileSegment(a: Answers): ProfileSegment {
  switch (a.profile) {
    case "direccion":
      return "decisor_negocio";
    case "operaciones":
      return "operaciones";
    case "innovacion":
    case "tecnologia":
      return "tecnologico";
    case "ingenieria":
      return "ingenieria";
    case "producto":
      return "producto_innovacion";
    case "marketing_ventas":
      return "marketing_ventas";
    case "consultoria":
      return "consultor_independiente";
    case "otro":
      return a.teamSize === "1_10" || a.teamSize === "11_50" ? "decisor_negocio" : "operaciones";
  }
}

export function workLevelIndex(level: WorkLevel): number {
  return WORK_LEVELS.indexOf(level);
}

export function maturitySegment(a: Answers): MaturitySegment {
  const level = workLevelIndex(a.workLevel);
  const adoptingOrMore = level >= workLevelIndex("adoptando");
  const clearProblems = realFrictions(a).length;

  if (clearProblems <= 1 && level <= workLevelIndex("explorando") && a.aiUsage === "no") return "explorador";
  if (level >= workLevelIndex("avanzado") && a.aiUsage === "integrada" && (a.techCapacity === "interno" || a.techCapacity === "especializado")) return "escalador";
  const integrationSignals = a.dataLocation === "varios_sistemas" || a.frictions.includes("copiar_datos") || a.frictions.includes("reporting");
  if (integrationSignals && adoptingOrMore) return "integrador";
  if (adoptingOrMore || a.aiUsage === "herramientas_puntuales" || a.aiUsage === "integrada") return "en_adopcion";
  return "inicial";
}

export function categorySignals(a: Answers): Map<OpportunityCategory, number> {
  const counts = new Map<OpportunityCategory, number>();
  const bump = (c: OpportunityCategory, n = 1) => counts.set(c, (counts.get(c) ?? 0) + n);
  for (const f of a.frictions) {
    const cats = FRICTION_CATEGORIES[f];
    cats.forEach((c, i) => bump(c, i === 0 ? 2 : 1));
  }
  for (const g of a.goals) for (const c of GOAL_CATEGORIES[g] ?? []) bump(c, 1);
  if (a.profile === "producto") bump("producto_digital", 1);
  return counts;
}

export function opportunityCategoriesFor(a: Answers): OpportunityCategory[] {
  const counts = categorySignals(a);
  return [...counts.entries()]
    .filter(([, n]) => n > 0)
    .sort((x, y) => y[1] - x[1] || OPPORTUNITY_CATEGORIES.indexOf(x[0]) - OPPORTUNITY_CATEGORIES.indexOf(y[0]))
    .map(([c]) => c);
}

export function intentLevel(a: Answers): IntentLevel {
  const budgetReady = a.investment === "proyecto" || a.investment === "estrategico";
  if (a.urgency === "inmediato" && budgetReady) return "muy_alta";
  if (a.urgency === "pronto" || a.urgency === "inmediato" || budgetReady) return "alta";
  if (a.urgency === "explorar" && a.investment === "explorar") return "baja";
  return "media";
}

export function estimateComplexity(a: Answers): Complexity {
  const level = workLevelIndex(a.workLevel);
  const bigTeam = a.teamSize === "51_200" || a.teamSize === "200_plus";
  const strongTeam = a.techCapacity === "interno" || a.techCapacity === "especializado";
  if (a.investment === "estrategico") return "solucion_estrategica";
  if ((a.dataLocation === "varios_sistemas" || a.frictions.includes("copiar_datos")) && level >= workLevelIndex("adoptando")) return "proyecto_integracion";
  if (bigTeam && (a.urgency === "pronto" || a.urgency === "inmediato") && strongTeam) return "transformacion_proceso";
  if (a.techCapacity === "sin_equipo" || a.investment === "explorar") return "quick_win";
  return "piloto_baja";
}

export function segmentAnswers(a: Answers): Segment {
  return {
    profile: profileSegment(a),
    maturity: maturitySegment(a),
    opportunityCategories: opportunityCategoriesFor(a),
    intent: intentLevel(a),
    complexity: estimateComplexity(a),
  };
}
