import { MICROS_PER_UNIT } from "@nexus/ui";

import { moneyText } from "@/components/money/money-model";
import type { MessageKey } from "@/i18n/messages";
import type { AgentSpec } from "@/lib/backend/builder-types";
import type { Money } from "@/lib/backend/money-types";
import type { CurrentPolicy, ModelPolicy, ModelQuality, PinnableModel, ProfileOption, QualityCheck, QualityProfile } from "@/lib/backend/model-quality-types";
import { QUALITY_PROFILES } from "@/lib/backend/model-quality-types";

/**
 * Spec 047 (historia 23; T147; requisito 39) — lo que Agente › Avanzado ›
 * Calidad decide sin pintar nada: cómo se escribe un precio por mensaje (son
 * fracciones de céntimo), la diferencia con la opción actual, los motivos de
 * una comprobación que no pasó, y si una opción se puede usar ya o hay que
 * comprobarla antes (39.9). Puro: lo prueban los tests sin montar la pantalla.
 */

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

const SYMBOL = { EUR: "€", USD: "USD" } as const;
/** Hasta cuatro decimales: un mensaje cuesta fracciones de céntimo, y «0,00 USD» mentiría. */
const UNIT = new Intl.NumberFormat("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 4, useGrouping: true });
const SMALLEST = 0.0001;

/**
 * «0,0042 USD» · «1,25 €». Desde un céntimo, como el resto del dinero
 * (`moneyText`); por debajo, con los decimales que hacen falta y, si ni eso,
 * «menos de 0,0001 USD».
 */
export function unitPriceText(t: T, value: Money): string {
  const amount = Math.abs(value.amount_micros) / MICROS_PER_UNIT;
  if (amount >= 0.01 || amount === 0) return moneyText({ amount_micros: Math.abs(value.amount_micros), currency: value.currency });
  // El espacio es duro, como en `formatMoney`: el importe no se parte de su moneda.
  if (amount < SMALLEST) return t("modelQuality.price.tiny", { amount: `${UNIT.format(SMALLEST)}\u00a0${SYMBOL[value.currency]}` });
  return `${UNIT.format(amount)}\u00a0${SYMBOL[value.currency]}`;
}

export function priceText(t: T, value: Money | null): string {
  return value ? t("modelQuality.price", { amount: unitPriceText(t, value) }) : t("modelQuality.price.none");
}

/** «0,0012 USD más que la actual» · «… menos …» · «Lo mismo que la actual». Sin opción actual, nada. */
export function deltaText(t: T, delta: Money | null): string | null {
  if (!delta) return null;
  if (delta.amount_micros === 0) return t("modelQuality.delta.same");
  const amount = unitPriceText(t, delta);
  return t(delta.amount_micros > 0 ? "modelQuality.delta.more" : "modelQuality.delta.less", { amount });
}

export function profileName(t: T, profile: string): string {
  return (QUALITY_PROFILES as readonly string[]).includes(profile) ? t(`modelQuality.profile.${profile}` as MessageKey) : profile;
}

export function profileLine(t: T, option: Pick<ProfileOption, "profile" | "line">): string {
  return (QUALITY_PROFILES as readonly string[]).includes(option.profile) ? t(`modelQuality.line.${option.profile}` as MessageKey) : option.line;
}

export function residencyText(t: T, residency: string): string {
  return residency === "eu" || residency === "us" ? t(`modelQuality.residency.${residency}` as MessageKey) : t("modelQuality.residency.global");
}

/** Lo que el AgentSpec de un agente de antes fija: su modelo de antes (`agent_spec/legacy.py`). */
const LEGACY_DEPLOYMENT = "nexus/current-binding";
const isLegacy = (p: CurrentPolicy | ModelPolicy) => p.kind === "legacy" || ("deployment" in p && p.deployment === LEGACY_DEPLOYMENT);

/** El nombre de una política: el perfil, el modelo fijado (por su nombre si se conoce) o el de antes. */
export function policyName(t: T, policy: CurrentPolicy | ModelPolicy | null | undefined, pinnable: readonly PinnableModel[] = []): string {
  if (!policy || policy.kind === "legacy" || isLegacy(policy)) return t("modelQuality.legacy");
  if (policy.kind === "profile") return profileName(t, policy.profile);
  return pinnable.find((p) => p.deployment === policy.deployment)?.name ?? policy.deployment;
}

export function samePolicy(a: CurrentPolicy | ModelPolicy | null | undefined, b: CurrentPolicy | ModelPolicy | null | undefined): boolean {
  if (a && b && isLegacy(a) && isLegacy(b)) return true;
  if (!a || !b || a.kind !== b.kind) return false;
  if (a.kind === "profile" && b.kind === "profile") return a.profile === b.profile;
  if (a.kind === "pinned" && b.kind === "pinned") return a.deployment === b.deployment;
  return a.kind === "legacy";
}

/** La política del borrador, si tiene una válida (`agent-spec.schema.json`). */
export function draftPolicy(spec: AgentSpec | null | undefined): ModelPolicy | null {
  const raw = spec?.model_policy as Record<string, unknown> | null | undefined;
  if (!raw || typeof raw !== "object") return null;
  if (raw.kind === "profile" && typeof raw.profile === "string" && (QUALITY_PROFILES as readonly string[]).includes(raw.profile)) {
    return { kind: "profile", profile: raw.profile as QualityProfile };
  }
  if (raw.kind === "pinned" && typeof raw.deployment === "string" && raw.deployment) return { kind: "pinned", deployment: raw.deployment };
  return null;
}

export function optionPolicy(option: ProfileOption | PinnableModel): ModelPolicy {
  return "profile" in option ? { kind: "profile", profile: option.profile } : { kind: "pinned", deployment: option.deployment };
}

export function optionName(t: T, option: ProfileOption | PinnableModel): string {
  return "profile" in option ? profileName(t, option.profile) : option.name;
}

/** Se está comprobando: un trabajo en marcha (o en cola). */
export function isChecking(check: QualityCheck): boolean {
  return check.status === "queued" || check.status === "running";
}

/**
 * Se puede llevar al borrador sin comprobar: ya está certificada para este
 * agente o su última comprobación pasó (39.9). La puerta lo vuelve a mirar al
 * guardar.
 */
export function usable(option: ProfileOption | PinnableModel): boolean {
  return option.certified || option.check.status === "passed";
}

/** Los motivos de una comprobación que no pasó, con palabras (`services/agent_quality.finish_check`). */
export function reasonText(t: T, reason: string, locale = "es"): string {
  if (reason === "critical_failed" || reason === "no_result" || reason === "run_failed") return t(`modelQuality.reason.${reason}` as MessageKey);
  const regression = /^regression:(\d+(?:\.\d+)?)$/.exec(reason);
  if (regression) {
    const drop = Number(regression[1]);
    // La nota va de 0 a 1: 0,05 son 5 puntos.
    const points = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(drop <= 1 ? drop * 100 : drop);
    return t("modelQuality.reason.regression", { points });
  }
  return t("modelQuality.reason.unknown");
}

/** Lo que se ofrece: con «Solo UE», los perfiles que no tienen modelo en la UE no salen (39.10). */
export function offeredProfiles(quality: ModelQuality): ProfileOption[] {
  return quality.profiles.filter((p) => p.offered);
}

/** «Automático», para proponérselo a un agente migrado (39.11). */
export function autoOption(quality: ModelQuality): ProfileOption | null {
  return quality.profiles.find((p) => p.profile === "auto" && p.offered) ?? null;
}

/** Cambia la comprobación de una opción en la lectura que ya tiene la pantalla. */
export function withCheck(quality: ModelQuality, policy: ModelPolicy, check: QualityCheck): ModelQuality {
  return {
    ...quality,
    profiles: quality.profiles.map((p) => (samePolicy(optionPolicy(p), policy) ? { ...p, check } : p)),
    pinnable: quality.pinnable.map((p) => (samePolicy(optionPolicy(p), policy) ? { ...p, check } : p)),
  };
}
