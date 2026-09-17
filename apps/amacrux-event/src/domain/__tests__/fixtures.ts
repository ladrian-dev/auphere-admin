import type { Answers } from "../types";

/** Perfil A — gerente de pyme: manual, pocos sistemas, sin equipo técnico, interés en piloto. */
export const PROFILE_A: Answers = {
  profile: "direccion", sector: "comercio_retail", teamSize: "11_50", customerType: "b2c",
  workLevel: "explorando", aiUsage: "no", dataLocation: "hojas_calculo",
  frictions: ["tareas_manuales", "copiar_datos", "emails_solicitudes"], goals: ["ahorrar_tiempo"],
  urgency: "proximos_meses", techCapacity: "sin_equipo", investment: "prueba",
};

/** Perfil B — operaciones: alto volumen, coordinación y reporting, herramientas desconectadas, urgencia alta. */
export const PROFILE_B: Answers = {
  profile: "operaciones", sector: "industria_logistica", teamSize: "51_200", customerType: "b2b",
  workLevel: "adoptando", aiUsage: "herramientas_puntuales", dataLocation: "varios_sistemas",
  frictions: ["operaciones_logistica", "reporting", "copiar_datos"], goals: ["escalar", "datos"],
  urgency: "inmediato", techCapacity: "limitado", investment: "proyecto",
};

/** Perfil C — ingeniería: equipo técnico, productividad del desarrollo, documentación/testing. */
export const PROFILE_C: Answers = {
  profile: "ingenieria", sector: "tecnologia_software", teamSize: "11_50", customerType: "b2b",
  workLevel: "avanzado", aiUsage: "integrada", dataLocation: "centralizada",
  frictions: ["desarrollo_software", "testing_qa", "documentacion_tecnica"], goals: ["acelerar_desarrollo", "calidad_producto"],
  urgency: "proximos_meses", techCapacity: "especializado", investment: "proyecto",
};

/** Perfil D — exploratorio: sin problema claro, baja urgencia, nivel inicial. */
export const PROFILE_D: Answers = {
  profile: "direccion", sector: "otro", teamSize: "1_10", customerType: "mixto",
  workLevel: "inicial", aiUsage: "no", dataLocation: "papel_chat",
  frictions: ["otro"], goals: ["decisiones"],
  urgency: "explorar", techCapacity: "sin_equipo", investment: "explorar",
};

/** Muchas categorías posibles a la vez. */
export const PROFILE_MANY: Answers = {
  profile: "innovacion", sector: "servicios_profesionales", teamSize: "200_plus", customerType: "mixto",
  workLevel: "avanzado", aiUsage: "herramientas_puntuales", dataLocation: "varios_sistemas",
  frictions: ["ventas_leads", "extraccion_datos", "atencion_cliente"], goals: ["aumentar_ventas", "datos"],
  urgency: "pronto", techCapacity: "interno", investment: "proyecto",
};
