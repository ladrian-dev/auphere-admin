/**
 * Tipos puros de Agente › Avanzado › Calidad — spec 047, T147 (requisito 39;
 * `contracts/console-api.md` §4). Reflejan `api/console/agent_quality.py`. Sin
 * imports con efectos: valen para componentes de cliente y para los tests. El
 * cliente de la API es `./model-quality.ts`.
 *
 * Los precios son precios (el modelo por 2,2, 39.6), nunca costes (C9), en
 * `{amount_micros, currency}` como el resto del dinero.
 */
import type { Money } from "./money-types";

export type QualityProfile = "auto" | "economy" | "balanced" | "max";
export const QUALITY_PROFILES: readonly QualityProfile[] = ["auto", "economy", "balanced", "max"];

/** La política de modelo de una versión (39.1): un perfil o un modelo fijado. */
export type ModelPolicy = { kind: "profile"; profile: QualityProfile } | { kind: "pinned"; deployment: string };
/** Lo que lleva hoy la versión publicada; `legacy` es un agente de antes, con su modelo de siempre. */
export type CurrentPolicy = ModelPolicy | { kind: "legacy" };

export type QualityCheckStatus = "none" | "queued" | "running" | "passed" | "failed";
/** «Comprobando la calidad…» (39.9): la suite del agente con esa política. */
export type QualityCheck = { status: QualityCheckStatus; job_id: string | null; reasons: string[] };

export type ProfileOption = {
  profile: QualityProfile;
  /** La línea de la API; la pantalla escribe la suya. */
  line: string;
  /** Con «Solo UE», solo si tiene modelo en la UE para cada tarea (39.10). */
  offered: boolean;
  price_per_message: Money | null;
  /** Frente a la opción actual: positiva si es más cara. */
  delta: Money | null;
  current: boolean;
  /** Sus modelos de conversación ya están certificados para este agente. */
  certified: boolean;
  check: QualityCheck;
};

export type PinnableModel = {
  deployment: string;
  name: string;
  provider: string;
  residency: "eu" | "us" | "global" | string;
  price_per_message: Money | null;
  delta: Money | null;
  current: boolean;
  certified: boolean;
  check: QualityCheck;
};

export type ModelQuality = {
  current: CurrentPolicy;
  /** La estimación sale del perfil de 30 días del agente o, sin tráfico, del sector (39.4). */
  estimate_source: "agent_30d" | "sector";
  profiles: ProfileOption[];
  pinnable: PinnableModel[];
  pinned_line: string;
  /** El precio real medio por mensaje de los últimos 7 días (39.5). */
  real_price_7d: Money | null;
  /** Agente migrado: se le propone «Automático» (39.11). */
  suggest_auto: boolean;
  eu_only: boolean;
  allowed: "change"[];
};

export type QualityCheckAccepted = { job_id: string; run_id?: string };
