/**
 * Tipos puros del conocimiento en dos capas (spec 047, historia 22; T133 y
 * T134): la capa del negocio, que ven todos los agentes del cliente, y la capa
 * propia de cada agente, que no ve ningún otro (garantía 9). Reflejan
 * `api/console/agent_knowledge.py`, `api/console/knowledge.py` y
 * `KnowledgeDocumentOut` de `schemas_agent_tools.py`. Sin imports con efectos:
 * valen para componentes de cliente y para los tests. El cliente de la API es
 * `./agent-knowledge.ts`.
 *
 * Nunca llevan el texto de la fuente: solo su estado, su tamaño y su capa.
 */
import type { KnowledgeDocumentOut } from "./agent-tools-types";

/** Una fuente con su capa (`agent_id` nulo = la del negocio) y su ventana para restaurarla. */
export type KnowledgeSource = KnowledgeDocumentOut & {
  agent_id?: string | null;
  removed_at?: string | null;
  restore_until?: string | null;
};

/** La pestaña Conocimiento de un agente: sus fuentes (las quitadas también) y cuántas tiene el negocio. */
export type AgentKnowledge = {
  items: KnowledgeSource[];
  /** Las fuentes de la capa del negocio que también ve este agente; se gestionan en Negocio. */
  business_sources: number;
};

/** Dónde se guarda lo que se enseña: todo el negocio (todos sus agentes) o solo este agente (37.3). */
export type TeachScope = "business" | "agent";

/** Lo más largo que admite «Enseñar» (`services/knowledge/teach.py`). */
export const TEACH_MAX_CHARS = 5_000;
