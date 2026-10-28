import { describe, expect, it } from "vitest";

import { t as translate } from "@/i18n/messages";
import type { AgentSpec } from "@/lib/backend/builder-types";

import {
  autoOption,
  deltaText,
  draftPolicy,
  offeredProfiles,
  policyName,
  priceText,
  reasonText,
  samePolicy,
  unitPriceText,
  usable,
  withCheck,
} from "../model-quality-model";
import { JOB, pinnable, profile, quality } from "./connector-fixtures";

const t = (key: Parameters<typeof translate>[1], vars?: Record<string, string | number>) => translate("es", key, vars);
/** Los importes llevan un espacio duro entre la cifra y la moneda; aquí se leen con uno normal. */
const plain = (text: string | null) => (text === null ? null : text.replace(/\u00a0/g, " "));
const usd = (amount_micros: number) => ({ amount_micros, currency: "USD" as const });

/**
 * Spec 047 (historia 23; T147; requisito 39) — lo que Calidad decide sin
 * pintar: el precio por mensaje (fracciones de céntimo), la diferencia con la
 * actual, los motivos de una comprobación y qué se puede llevar al borrador.
 */
describe("Calidad · los precios", () => {
  it("un mensaje cuesta fracciones de céntimo: se escriben con sus decimales, y desde un céntimo como el resto", () => {
    expect(plain(unitPriceText(t, usd(420)))).toBe("0,0042 USD");
    expect(plain(unitPriceText(t, usd(125_000)))).toBe("1,25 USD");
    expect(plain(unitPriceText(t, { amount_micros: 5_000, currency: "EUR" }))).toBe("0,05 €");
    expect(plain(unitPriceText(t, usd(0)))).toBe("0,00 USD");
    expect(plain(unitPriceText(t, usd(0.4)))).toBe("menos de 0,0001 USD");
    expect(plain(priceText(t, usd(200)))).toBe("0,002 USD por mensaje");
    expect(plain(priceText(t, null))).toBe("Sin precio estimado");
  });

  it("la diferencia con la opción actual, en las dos direcciones", () => {
    expect(plain(deltaText(t, usd(220)))).toBe("0,0022 USD más que la actual");
    expect(plain(deltaText(t, usd(-120)))).toBe("0,0012 USD menos que la actual");
    expect(plain(deltaText(t, usd(0)))).toBe("Lo mismo que la actual");
    expect(plain(deltaText(t, null))).toBeNull();
  });
});

describe("Calidad · las políticas", () => {
  it("nombra un perfil, un modelo fijado y el modelo de antes", () => {
    const q = quality();
    expect(policyName(t, { kind: "profile", profile: "balanced" })).toBe("Equilibrado");
    expect(policyName(t, { kind: "pinned", deployment: "anthropic/claude-sonnet-eu" }, q.pinnable)).toBe("Claude Sonnet (UE)");
    expect(policyName(t, { kind: "pinned", deployment: "otro/modelo" })).toBe("otro/modelo");
    expect(policyName(t, { kind: "legacy" })).toBe("El modelo que tenía antes de la consola nueva");
    expect(samePolicy({ kind: "profile", profile: "auto" }, { kind: "profile", profile: "auto" })).toBe(true);
    expect(samePolicy({ kind: "profile", profile: "auto" }, { kind: "pinned", deployment: "auto" })).toBe(false);
  });

  it("lee la política del borrador solo si tiene la forma del esquema", () => {
    expect(draftPolicy({ model_policy: { kind: "profile", profile: "max" } } as unknown as AgentSpec)).toEqual({ kind: "profile", profile: "max" });
    expect(draftPolicy({ model_policy: { kind: "pinned", deployment: "a/b" } } as unknown as AgentSpec)).toEqual({ kind: "pinned", deployment: "a/b" });
    expect(draftPolicy({ model_policy: { kind: "profile", profile: "turbo" } } as unknown as AgentSpec)).toBeNull();
    expect(draftPolicy(null)).toBeNull();
  });

  it("solo se lleva al borrador lo comprobado con este agente (39.9)", () => {
    expect(usable(profile({ profile: "auto", certified: true }))).toBe(true);
    expect(usable(profile({ profile: "economy", certified: false }))).toBe(false);
    expect(usable(pinnable({ check: { status: "passed", job_id: JOB, reasons: [] } }))).toBe(true);
  });

  it("los motivos de una comprobación que no pasó, con palabras", () => {
    expect(reasonText(t, "critical_failed")).toBe("Falló una prueba crítica.");
    expect(reasonText(t, "regression:0.05")).toBe("Las pruebas bajan 5 puntos frente a la última pasada.");
    expect(reasonText(t, "algo")).toBe("No cumple la puerta de calidad.");
  });

  it("con «Solo UE» no se ofrece lo que no tiene modelo en la UE, y a un migrado se le propone «Automático»", () => {
    const q = quality({ profiles: [profile({ profile: "auto" }), profile({ profile: "max", offered: false })] });
    expect(offeredProfiles(q).map((p) => p.profile)).toEqual(["auto"]);
    expect(autoOption(q)?.profile).toBe("auto");
    expect(autoOption(quality({ profiles: [profile({ profile: "auto", offered: false })] }))).toBeNull();
  });

  it("una comprobación nueva cambia solo su opción", () => {
    const q = withCheck(quality(), { kind: "profile", profile: "economy" }, { status: "running", job_id: JOB, reasons: [] });
    expect(q.profiles.find((p) => p.profile === "economy")?.check.status).toBe("running");
    expect(q.profiles.find((p) => p.profile === "max")?.check.status).toBe("failed");
  });
});
