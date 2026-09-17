import { CAPACITY_INDEX, generateResult } from "@/domain/engine";
import type { Answers, Result } from "@/domain/types";

/**
 * Interfaz para enchufar otro proveedor (p. ej. un modelo de IA) sin tocar la
 * experiencia. Todo proveedor pasa por `validateResult` antes de mostrarse.
 */
export interface RecommendationProvider {
  recommend(answers: Answers): Promise<Result>;
}

export const rulesProvider: RecommendationProvider = {
  async recommend(answers) {
    return generateResult(answers);
  },
};

const FORBIDDEN_CLAIMS = /\d+\s?%|€|\$|garantiz|\bROI\b|retorno de (la )?inversi|asesor(ía|amiento) (legal|financier|médic)/i;
const EMAIL = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i;
const PHONE = /(?:\+?\d[\d\s().-]{7,}\d)/;

function textsOf(result: Result): string[] {
  const out = [result.intro, result.shortTerm, result.midTerm, ...result.warnings, result.cta.label];
  for (const r of result.recommendations ?? []) {
    const o = r.opportunity;
    out.push(o.title, o.problemSolved, o.howItWorks, o.benefitDescription, o.recommendedFirstStep, o.amacruxFit, o.commercialCta, o.warning ?? "", ...r.reasons, ...r.warnings);
  }
  return out;
}

export function validateResult(result: Result, answers: Answers): { ok: true } | { ok: false; violations: string[] } {
  const violations: string[] = [];
  const recs = result.recommendations ?? [];
  if (recs.length !== 3) violations.push(`Se esperaban 3 recomendaciones y hay ${recs.length}`);
  const allowed = CAPACITY_INDEX[answers.techCapacity] + 1;
  for (const r of recs) {
    if (r.opportunity.technicalComplexity > allowed) violations.push(`«${r.opportunity.title}» supera la capacidad técnica declarada`);
    if (!r.reasons || r.reasons.length === 0) violations.push(`«${r.opportunity.title}» no explica por qué se recomienda`);
  }
  for (const t of textsOf(result)) {
    if (FORBIDDEN_CLAIMS.test(t)) violations.push(`Texto con cifras, garantías o consejo profesional: "${t.slice(0, 60)}"`);
    if (EMAIL.test(t) || PHONE.test(t)) violations.push(`Texto con datos personales: "${t.slice(0, 60)}"`);
  }
  return violations.length === 0 ? { ok: true } : { ok: false, violations };
}
