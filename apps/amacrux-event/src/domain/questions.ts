/**
 * 12 preguntas, una por pantalla. Etiquetas cortas (2–4 palabras) pensadas
 * para chips en móvil. La palabra "madurez" no aparece en textos visibles.
 */
import type {
  AiUsage, CustomerType, DataLocation, Friction, Goal, Investment, Profile, QuestionStep, Sector,
  TeamSize, TechCapacity, Urgency, WorkLevel,
} from "./enums";

export interface Option<V extends string = string> {
  value: V;
  label: string;
  description?: string;
}

export type QuestionId = QuestionStep;

export interface Question<V extends string = string> {
  id: QuestionId;
  eyebrow: string;
  title: string;
  hint?: string;
  type: "single" | "multi" | "scale";
  max?: number;
  columns: 1 | 2;
  estimatedSeconds: number;
  options: Option<V>[];
}

const profile: Question<Profile> = {
  id: "profile", eyebrow: "Tu perfil", title: "¿Cuál es tu rol?", type: "single", columns: 2, estimatedSeconds: 10,
  options: [
    { value: "direccion", label: "Dirección" },
    { value: "operaciones", label: "Operaciones" },
    { value: "innovacion", label: "Innovación / digital" },
    { value: "tecnologia", label: "Tecnología" },
    { value: "ingenieria", label: "Ingeniería de software" },
    { value: "producto", label: "Producto o diseño" },
    { value: "marketing_ventas", label: "Marketing o ventas" },
    { value: "consultoria", label: "Consultoría" },
    { value: "agente_inmobiliario", label: "Agente inmobiliario" },
    { value: "otro", label: "Otro" },
  ],
};

const sector: Question<Sector> = {
  id: "sector", eyebrow: "Tu empresa", title: "¿En qué sector?", type: "single", columns: 2, estimatedSeconds: 10,
  options: [
    { value: "comercio_retail", label: "Comercio y retail" },
    { value: "servicios_profesionales", label: "Servicios profesionales" },
    { value: "salud_farmacia", label: "Salud y farmacia" },
    { value: "hosteleria_turismo", label: "Hostelería y turismo" },
    { value: "industria_logistica", label: "Industria y logística" },
    { value: "tecnologia_software", label: "Tecnología y software" },
    { value: "educacion", label: "Educación" },
    { value: "finanzas_seguros", label: "Finanzas y seguros" },
    { value: "sector_publico", label: "Sector público" },
    { value: "otro", label: "Otro" },
  ],
};

const teamSize: Question<TeamSize> = {
  id: "teamSize", eyebrow: "Tu empresa", title: "¿Tamaño del equipo?", type: "single", columns: 2, estimatedSeconds: 6,
  options: [
    { value: "1_10", label: "1–10 personas" },
    { value: "11_50", label: "11–50 personas" },
    { value: "51_200", label: "51–200 personas" },
    { value: "200_plus", label: "Más de 200" },
  ],
};

const customerType: Question<CustomerType> = {
  id: "customerType", eyebrow: "Tu empresa", title: "¿A quién vendes?", type: "single", columns: 2, estimatedSeconds: 6,
  options: [
    { value: "b2b", label: "Empresas (B2B)" },
    { value: "b2c", label: "Consumidores (B2C)" },
    { value: "publico", label: "Administración pública" },
    { value: "mixto", label: "Mixto" },
  ],
};

const workLevel: Question<WorkLevel> = {
  id: "workLevel", eyebrow: "Cómo trabajan", title: "¿Cómo trabajan hoy?", hint: "Elige lo que más se parezca.", type: "scale", columns: 1, estimatedSeconds: 15,
  options: [
    { value: "inicial", label: "Inicial", description: "Papel, WhatsApp y hojas de cálculo" },
    { value: "explorando", label: "Explorando", description: "Herramientas sueltas, cada una por su lado" },
    { value: "adoptando", label: "Adoptando", description: "Software de gestión, algo conectado" },
    { value: "avanzado", label: "Avanzado", description: "Sistemas conectados y datos ordenados" },
    { value: "escalando", label: "Escalando", description: "Automatizamos ya; buscamos robustez" },
  ],
};

const aiUsage: Question<AiUsage> = {
  id: "aiUsage", eyebrow: "Cómo trabajan", title: "¿Usan IA hoy?", type: "single", columns: 2, estimatedSeconds: 6,
  options: [
    { value: "no", label: "Todavía no" },
    { value: "pruebas_individuales", label: "Pruebas individuales" },
    { value: "herramientas_puntuales", label: "Alguna herramienta" },
    { value: "integrada", label: "Integrada en procesos" },
  ],
};

const dataLocation: Question<DataLocation> = {
  id: "dataLocation", eyebrow: "Cómo trabajan", title: "¿Dónde vive la información?", type: "single", columns: 2, estimatedSeconds: 8,
  options: [
    { value: "papel_chat", label: "Papel, correos y chats" },
    { value: "hojas_calculo", label: "Hojas de cálculo" },
    { value: "varios_sistemas", label: "Varios sistemas sueltos" },
    { value: "centralizada", label: "Centralizada" },
  ],
};

const frictions: Question<Friction> = {
  id: "frictions", eyebrow: "Fricciones", title: "¿Qué les quita más tiempo?", hint: "Hasta 3.", type: "multi", max: 3, columns: 2, estimatedSeconds: 25,
  options: [
    { value: "tareas_manuales", label: "Tareas manuales" },
    { value: "copiar_datos", label: "Copiar datos" },
    { value: "emails_solicitudes", label: "Correos y solicitudes" },
    { value: "atencion_cliente", label: "Atención al cliente" },
    { value: "presupuestos", label: "Presupuestos" },
    { value: "ventas_leads", label: "Ventas y seguimiento" },
    { value: "documental", label: "Gestión documental" },
    { value: "extraccion_datos", label: "Sacar datos de PDF" },
    { value: "reporting", label: "Informes" },
    { value: "visibilidad_datos", label: "Visibilidad de datos" },
    { value: "busqueda_interna", label: "Buscar información" },
    { value: "operaciones_logistica", label: "Logística" },
    { value: "planificacion_equipos", label: "Coordinación" },
    { value: "soporte_interno", label: "Soporte interno" },
    { value: "desarrollo_software", label: "Desarrollo" },
    { value: "testing_qa", label: "Testing y calidad" },
    { value: "documentacion_tecnica", label: "Documentación" },
    { value: "sin_tiempo_innovar", label: "Sin tiempo" },
    { value: "otro", label: "Otro" },
  ],
};

const goals: Question<Goal> = {
  id: "goals", eyebrow: "Objetivos", title: "¿Qué quieres conseguir?", hint: "Hasta 2.", type: "multi", max: 2, columns: 2, estimatedSeconds: 15,
  options: [
    { value: "ahorrar_tiempo", label: "Ahorrar tiempo" },
    { value: "reducir_errores", label: "Reducir errores" },
    { value: "aumentar_ventas", label: "Vender más" },
    { value: "mejorar_atencion", label: "Mejor atención" },
    { value: "escalar", label: "Escalar" },
    { value: "productividad", label: "Más productividad" },
    { value: "datos", label: "Aprovechar datos" },
    { value: "acelerar_desarrollo", label: "Desarrollar más rápido" },
    { value: "calidad_producto", label: "Mejor producto" },
    { value: "decisiones", label: "Decidir mejor" },
    { value: "nuevos_servicios", label: "Nuevos servicios" },
    { value: "reducir_costes", label: "Reducir costos" },
  ],
};

const urgency: Question<Urgency> = {
  id: "urgency", eyebrow: "Contexto", title: "¿Cuándo quieres resultados?", type: "single", columns: 2, estimatedSeconds: 8,
  options: [
    { value: "explorar", label: "Sin urgencia" },
    { value: "proximos_meses", label: "Próximos meses" },
    { value: "pronto", label: "Pronto" },
    { value: "inmediato", label: "Ya, es prioritario" },
  ],
};

const techCapacity: Question<TechCapacity> = {
  id: "techCapacity", eyebrow: "Contexto", title: "¿Con qué apoyo técnico?", type: "single", columns: 2, estimatedSeconds: 8,
  options: [
    { value: "sin_equipo", label: "Sin equipo técnico" },
    { value: "limitado", label: "Apoyo limitado" },
    { value: "interno", label: "Equipo interno" },
    { value: "especializado", label: "Equipo especializado" },
  ],
};

const investment: Question<Investment> = {
  id: "investment", eyebrow: "Contexto", title: "¿Inversión prevista?", type: "single", columns: 2, estimatedSeconds: 8,
  options: [
    { value: "explorar", label: "Solo explorar" },
    { value: "prueba", label: "Para una prueba" },
    { value: "proyecto", label: "Para un proyecto" },
    { value: "estrategico", label: "Solución estratégica" },
  ],
};

export const ALL_QUESTIONS: Question[] = [profile, sector, teamSize, customerType, workLevel, aiUsage, dataLocation, frictions, goals, urgency, techCapacity, investment];
export const TOTAL_QUESTIONS = ALL_QUESTIONS.length;
export const TOTAL_ESTIMATED_SECONDS = ALL_QUESTIONS.reduce((acc, q) => acc + q.estimatedSeconds, 0);

export function questionIndex(id: QuestionId): number {
  return ALL_QUESTIONS.findIndex((q) => q.id === id);
}

export function questionById(id: QuestionId): Question {
  const q = ALL_QUESTIONS.find((x) => x.id === id);
  if (!q) throw new Error(`Pregunta desconocida: ${id}`);
  return q;
}

export function remainingSeconds(id: QuestionId): number {
  return ALL_QUESTIONS.slice(questionIndex(id)).reduce((acc, q) => acc + q.estimatedSeconds, 0);
}

export function optionLabel(questionId: QuestionId, value: string): string {
  return questionById(questionId).options.find((o) => o.value === value)?.label ?? value;
}
