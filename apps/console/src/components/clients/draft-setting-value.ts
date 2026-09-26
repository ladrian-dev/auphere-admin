/**
 * Cómo se lee un ajuste del agente (spec 017, R3.2).
 *
 * La API contesta con el JSON de `policies.console` — claves, no frases,
 * que es lo correcto: no sabe en qué idioma mira el partner. Pero
 * enseñarlo en crudo («enabled: ✓ · triggers: user_asks_human, angry,
 * out_of_scope») no es revisar nada. Aquí cada campo conocido se dice en
 * una frase, y lo que no se conozca cae a una línea legible antes que a un
 * volcado.
 *
 * Módulo puro: se prueba sin montar React.
 */
import type { MessageKey } from "@/i18n/messages";

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

type Dict = Record<string, unknown>;

const isDict = (v: unknown): v is Dict => typeof v === "object" && v !== null && !Array.isArray(v);

/** Una frase por campo; `null` cuando este campo no tiene una propia. */
function known(t: T, field: string, value: Dict): string | null {
  switch (field) {
    case "identity": {
      const name = typeof value.name === "string" ? value.name.trim() : "";
      return name ? t("draft.value.identity", { name }) : t("draft.value.identity.none");
    }
    case "tone": {
      const style = typeof value.style === "string" ? value.style : "";
      return style ? t("draft.value.tone", { style }) : null;
    }
    case "schedule": {
      const weekly = value.weekly;
      const days = isDict(weekly) ? Object.values(weekly).filter((v) => Array.isArray(v) && v.length > 0).length : 0;
      if (days === 0) return t("draft.value.schedule.always");
      return t("draft.value.schedule.hours", { days, timezone: String(value.timezone ?? "UTC") });
    }
    case "languages": {
      const primary = String(value.primary ?? "");
      const allowed = Array.isArray(value.allowed) ? value.allowed.join(", ") : "";
      return primary ? t("draft.value.languages", { primary, allowed: allowed || primary }) : null;
    }
    case "escalation": {
      if (value.enabled === false) return t("draft.value.escalation.off");
      const count = Array.isArray(value.triggers) ? value.triggers.length : 0;
      return t("draft.value.escalation.on", { count });
    }
    case "ai_disclosure":
      return t(value.enabled === false ? "draft.value.disclosure.off" : "draft.value.disclosure.on");
    default:
      return null;
  }
}

/**
 * El valor de un ajuste, dicho para una persona. `field` elige la frase;
 * sin frase propia, se resume sin inventar.
 */
export function settingValue(t: T, field: string, value: unknown): string {
  if (value === null || value === undefined) return t("draft.value.none");
  if (field === "objective") {
    const text = typeof value === "string" ? value.trim() : "";
    return text ? t("draft.value.objective", { text: clip(text) }) : t("draft.value.objective.none");
  }
  if (typeof value === "boolean") return value ? "✓" : "—";
  if (typeof value === "string") return value.trim() ? clip(value) : t("draft.value.none");
  if (typeof value === "number") return String(value);
  if (Array.isArray(value)) return value.length ? value.map((v) => settingValue(t, "", v)).join(", ") : t("draft.value.none");
  if (isDict(value)) {
    const phrase = known(t, field, value);
    if (phrase) return phrase;
    // Sin frase propia: solo lo que tiene contenido, para no llenar la
    // fila de claves vacías.
    const parts = Object.entries(value)
      .filter(([, v]) => v !== null && v !== undefined && v !== "" && !(Array.isArray(v) && v.length === 0))
      .map(([k, v]) => `${k}: ${settingValue(t, "", v)}`);
    return parts.length ? parts.join(" · ") : t("draft.value.none");
  }
  return String(value);
}

/** Un objetivo de 4000 caracteres no cabe en una celda. */
function clip(text: string, max = 120): string {
  return text.length <= max ? text : `${text.slice(0, max - 1)}…`;
}
