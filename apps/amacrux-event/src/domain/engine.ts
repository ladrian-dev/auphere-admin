import type { MaturitySegment, OpportunityCategory, TechCapacity } from "./enums";
import { MATURITY_SEGMENTS } from "./enums";
import { buildIntro, buildMidTerm, buildShortTerm, buildWarnings, ctaFor, MATURITY_LABELS, PROFILE_SEGMENT_LABELS, RANGE_LABELS, reasonsFor, sectorLabel } from "./copy";
import { DEFAULTS_BY_PROFILE, OPPORTUNITIES } from "./opportunities";
import { scoreAnswers } from "./scoring";
import { segmentAnswers } from "./segmentation";
import type { Answers, Opportunity, Recommendation, Result, Segment } from "./types";

export const CAPACITY_INDEX: Record<TechCapacity, number> = { sin_equipo: 2, limitado: 3, interno: 4, especializado: 5 };

const maturityIndex = (m: MaturitySegment) => MATURITY_SEGMENTS.indexOf(m);

export function maturityOutside(o: Opportunity, m: MaturitySegment): boolean {
  const [lo, hi] = o.maturityRange;
  const i = maturityIndex(m);
  return i < maturityIndex(lo) || i > maturityIndex(hi);
}

interface Ranked {
  opportunity: Opportunity;
  points: number;
  matchedFrictions: Recommendation["matchedFrictions"];
  matchedGoals: Recommendation["matchedGoals"];
  profileMatch: boolean;
  warnings: string[];
}

export function rankOpportunities(a: Answers, segment: Segment): Ranked[] {
  const allowed = CAPACITY_INDEX[a.techCapacity] + 1;
  const out: Ranked[] = [];
  OPPORTUNITIES.forEach((o) => {
    if (o.technicalComplexity > allowed) return;
    const matchedFrictions = a.frictions.filter((f) => o.problemSignals.includes(f));
    const matchedGoals = a.goals.filter((g) => o.desiredOutcomes.includes(g));
    const profileMatch = o.applicableProfiles.length === 0 || o.applicableProfiles.includes(segment.profile);
    const sectorMatch = o.applicableSectors.length > 0 && o.applicableSectors.includes(a.sector);
    const categoryMatch = segment.opportunityCategories.includes(o.category);
    let points = matchedFrictions.length * 3 + matchedGoals.length * 2 + (profileMatch && o.applicableProfiles.length > 0 ? 2 : 0) + (sectorMatch ? 1 : 0) + (categoryMatch ? 2 : 0);
    const warnings: string[] = [];
    if (maturityOutside(o, segment.maturity)) {
      points *= 0.5;
      warnings.push(`«${o.title}» suele funcionar mejor con más base digital de la que describes; conviene empezar por ordenar datos y procesos.`);
    }
    if (a.investment === "explorar" && o.technicalComplexity >= 4) points *= 0.6;
    if (o.warning) warnings.push(o.warning);
    out.push({ opportunity: o, points, matchedFrictions, matchedGoals, profileMatch: profileMatch && o.applicableProfiles.length > 0, warnings });
  });
  return out.sort((x, y) => y.points - x.points || x.opportunity.technicalComplexity - y.opportunity.technicalComplexity || OPPORTUNITIES.indexOf(x.opportunity) - OPPORTUNITIES.indexOf(y.opportunity));
}

function confidenceFor(r: Ranked): Recommendation["confidence"] {
  if (r.matchedFrictions.length >= 2 && r.points >= 9) return "prioritario";
  if (r.matchedFrictions.length >= 1 && r.points >= 5) return "relevante";
  return "orientativo";
}

function pickTopThree(ranked: Ranked[], a: Answers, segment: Segment): Ranked[] {
  const picked: Ranked[] = [];
  const perCategory = new Map<OpportunityCategory, number>();
  const take = (r: Ranked) => {
    picked.push(r);
    perCategory.set(r.opportunity.category, (perCategory.get(r.opportunity.category) ?? 0) + 1);
  };
  for (const r of ranked) {
    if (picked.length === 3) break;
    if (r.points <= 0) break;
    if ((perCategory.get(r.opportunity.category) ?? 0) >= 2) continue;
    take(r);
  }
  if (picked.length < 3) {
    const allowed = CAPACITY_INDEX[a.techCapacity] + 1;
    const defaults = DEFAULTS_BY_PROFILE[segment.profile];
    for (const id of defaults) {
      if (picked.length === 3) break;
      if (picked.some((p) => p.opportunity.id === id)) continue;
      const o = OPPORTUNITIES.find((x) => x.id === id);
      if (!o || o.technicalComplexity > allowed) continue;
      if ((perCategory.get(o.category) ?? 0) >= 2) continue;
      take({ opportunity: o, points: 0, matchedFrictions: [], matchedGoals: [], profileMatch: false, warnings: o.warning ? [o.warning] : [] });
    }
  }
  if (picked.length < 3) {
    // Último recurso: las más sencillas del catálogo que aún no estén.
    for (const r of ranked) {
      if (picked.length === 3) break;
      if (picked.some((p) => p.opportunity.id === r.opportunity.id)) continue;
      if ((perCategory.get(r.opportunity.category) ?? 0) >= 2) continue;
      take({ ...r, points: 0, matchedFrictions: [], matchedGoals: [] });
    }
  }
  return picked;
}

export function generateResult(a: Answers, now: Date = new Date()): Result {
  const segment = segmentAnswers(a);
  const score = scoreAnswers(a, segment);
  const ranked = rankOpportunities(a, segment);
  const picked = pickTopThree(ranked, a, segment);
  if (picked.length < 3) throw new Error("El catálogo no puede producir tres recomendaciones");

  const recommendations = picked.map<Recommendation>((r) => ({
    opportunity: r.opportunity,
    score: Math.round(r.points * 10) / 10,
    confidence: confidenceFor(r),
    reasons: reasonsFor(r, segment, r.profileMatch),
    warnings: r.warnings,
    matchedFrictions: r.matchedFrictions,
    matchedGoals: r.matchedGoals,
  })) as [Recommendation, Recommendation, Recommendation];

  const finalSegment: Segment = { ...segment, complexity: recommendations[0].opportunity.complexityLabel };
  const warnings = buildWarnings(a, finalSegment, recommendations);

  return {
    version: 1,
    generatedAt: now.toISOString(),
    summary: {
      profileLabel: PROFILE_SEGMENT_LABELS[finalSegment.profile],
      sectorLabel: sectorLabel(a.sector),
      maturityLabel: MATURITY_LABELS[finalSegment.maturity],
      opportunityLevel: score.range,
      opportunityLevelLabel: RANGE_LABELS[score.range],
    },
    intro: buildIntro(a, finalSegment, recommendations[0]),
    recommendations,
    shortTerm: buildShortTerm(recommendations[0]),
    midTerm: buildMidTerm(recommendations[1], recommendations[2], finalSegment),
    warnings,
    cta: ctaFor(finalSegment.intent),
    segment: finalSegment,
    score,
  };
}
