/** Valores internos cerrados. Las etiquetas visibles viven en questions.ts y copy.ts. */

export const PROFILES = [
  "direccion", "operaciones", "innovacion", "tecnologia", "ingenieria",
  "producto", "marketing_ventas", "consultoria", "otro",
] as const;
export type Profile = (typeof PROFILES)[number];

export const SECTORS = [
  "comercio_retail", "servicios_profesionales", "salud_farmacia", "hosteleria_turismo",
  "industria_logistica", "tecnologia_software", "educacion", "finanzas_seguros",
  "sector_publico", "otro",
] as const;
export type Sector = (typeof SECTORS)[number];

export const TEAM_SIZES = ["1_10", "11_50", "51_200", "200_plus"] as const;
export type TeamSize = (typeof TEAM_SIZES)[number];

export const CUSTOMER_TYPES = ["b2b", "b2c", "publico", "mixto"] as const;
export type CustomerType = (typeof CUSTOMER_TYPES)[number];

export const WORK_LEVELS = ["inicial", "explorando", "adoptando", "avanzado", "escalando"] as const;
export type WorkLevel = (typeof WORK_LEVELS)[number];

export const AI_USAGES = ["no", "pruebas_individuales", "herramientas_puntuales", "integrada"] as const;
export type AiUsage = (typeof AI_USAGES)[number];

export const DATA_LOCATIONS = ["papel_chat", "hojas_calculo", "varios_sistemas", "centralizada"] as const;
export type DataLocation = (typeof DATA_LOCATIONS)[number];

export const FRICTIONS = [
  "tareas_manuales", "copiar_datos", "emails_solicitudes", "atencion_cliente", "presupuestos",
  "documental", "extraccion_datos", "reporting", "ventas_leads", "operaciones_logistica",
  "planificacion_equipos", "soporte_interno", "desarrollo_software", "testing_qa",
  "documentacion_tecnica", "busqueda_interna", "visibilidad_datos", "sin_tiempo_innovar", "otro",
] as const;
export type Friction = (typeof FRICTIONS)[number];

export const GOALS = [
  "ahorrar_tiempo", "reducir_errores", "aumentar_ventas", "mejorar_atencion", "escalar",
  "productividad", "datos", "acelerar_desarrollo", "calidad_producto", "decisiones",
  "nuevos_servicios", "reducir_costes",
] as const;
export type Goal = (typeof GOALS)[number];

export const URGENCIES = ["explorar", "proximos_meses", "pronto", "inmediato"] as const;
export type Urgency = (typeof URGENCIES)[number];

export const TECH_CAPACITIES = ["sin_equipo", "limitado", "interno", "especializado"] as const;
export type TechCapacity = (typeof TECH_CAPACITIES)[number];

export const INVESTMENTS = ["explorar", "prueba", "proyecto", "estrategico"] as const;
export type Investment = (typeof INVESTMENTS)[number];

export const PROFILE_SEGMENTS = [
  "decisor_negocio", "operaciones", "tecnologico", "ingenieria",
  "producto_innovacion", "marketing_ventas", "consultor_independiente",
] as const;
export type ProfileSegment = (typeof PROFILE_SEGMENTS)[number];

export const MATURITY_SEGMENTS = ["explorador", "inicial", "en_adopcion", "integrador", "escalador"] as const;
export type MaturitySegment = (typeof MATURITY_SEGMENTS)[number];

export const OPPORTUNITY_CATEGORIES = [
  "automatizacion_operativa", "ia_conocimiento_soporte", "automatizacion_comercial",
  "procesamiento_documental", "datos_reporting", "ia_desarrollo",
  "integraciones_orquestacion", "producto_digital",
] as const;
export type OpportunityCategory = (typeof OPPORTUNITY_CATEGORIES)[number];

export const INTENT_LEVELS = ["baja", "media", "alta", "muy_alta"] as const;
export type IntentLevel = (typeof INTENT_LEVELS)[number];

export const COMPLEXITIES = [
  "quick_win", "piloto_baja", "proyecto_integracion", "transformacion_proceso", "solucion_estrategica",
] as const;
export type Complexity = (typeof COMPLEXITIES)[number];

export const CONFIDENCES = ["orientativo", "relevante", "prioritario"] as const;
export type Confidence = (typeof CONFIDENCES)[number];

export const SCORE_RANGES = ["exploracion", "oportunidad_inicial", "oportunidad_prioritaria", "alta_intencion"] as const;
export type ScoreRange = (typeof SCORE_RANGES)[number];

/** Etiqueta interna para Amacrux. Nunca se muestra en la interfaz. */
export const LEAD_TIERS = ["frio", "tibio", "caliente", "muy_caliente"] as const;
export type LeadTier = (typeof LEAD_TIERS)[number];

/** Una pantalla por pregunta: el paso del wizard es el id de la pregunta. */
export const QUESTION_STEPS = [
  "profile", "sector", "teamSize", "customerType", "workLevel", "aiUsage", "dataLocation",
  "frictions", "goals", "urgency", "techCapacity", "investment",
] as const;
export type QuestionStep = (typeof QUESTION_STEPS)[number];

/** Flujo v2 (2026-09-16): el contacto es la puerta al resultado. */
export const WIZARD_STEPS = ["welcome", ...QUESTION_STEPS, "lead", "processing", "result"] as const;
export type WizardStep = (typeof WIZARD_STEPS)[number];

export const ANALYTICS_EVENT_NAMES = [
  "landing_viewed", "assessment_started", "question_answered", "assessment_completed",
  "result_viewed", "recommendation_selected", "contact_form_viewed", "lead_submitted",
  "contact_skipped", "assessment_restarted", "error_shown",
] as const;
export type AnalyticsEventName = (typeof ANALYTICS_EVENT_NAMES)[number];
