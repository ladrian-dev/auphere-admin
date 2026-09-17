import type {
  AiUsage, AnalyticsEventName, Complexity, Confidence, CustomerType, DataLocation, Friction, Goal,
  IntentLevel, Investment, LeadTier, MaturitySegment, OpportunityCategory, Profile, ProfileSegment,
  ScoreRange, Sector, TeamSize, TechCapacity, Urgency, WizardStep, WorkLevel,
} from "./enums";

export interface Utm {
  source?: string;
  medium?: string;
  campaign?: string;
  content?: string;
}

/** Las 12 respuestas más la campaña. Nunca contiene datos personales. */
export interface Answers {
  profile: Profile;
  sector: Sector;
  teamSize: TeamSize;
  customerType: CustomerType;
  workLevel: WorkLevel;
  aiUsage: AiUsage;
  dataLocation: DataLocation;
  frictions: Friction[];
  goals: Goal[];
  urgency: Urgency;
  techCapacity: TechCapacity;
  investment: Investment;
  campaign?: string;
  utm?: Utm;
}

export type PartialAnswers = Partial<Omit<Answers, "frictions" | "goals">> & {
  frictions?: Friction[];
  goals?: Goal[];
};

export interface Segment {
  profile: ProfileSegment;
  maturity: MaturitySegment;
  opportunityCategories: OpportunityCategory[];
  intent: IntentLevel;
  complexity: Complexity;
}

export interface ScoreBreakdown {
  problemClarity: number; // 0–20
  impact: number; // 0–20
  urgency: number; // 0–15
  capacity: number; // 0–15
  maturity: number; // 0–10
  fit: number; // 0–10
  intent: number; // 0–10
}

export interface Score {
  total: number; // 0–100
  range: ScoreRange;
  breakdown: ScoreBreakdown;
  leadTier: LeadTier;
}

export interface Opportunity {
  id: string;
  title: string;
  category: OpportunityCategory;
  applicableProfiles: ProfileSegment[];
  applicableSectors: Sector[];
  problemSignals: Friction[];
  desiredOutcomes: Goal[];
  maturityRange: [MaturitySegment, MaturitySegment];
  technicalComplexity: 1 | 2 | 3 | 4 | 5;
  complexityLabel: Complexity;
  expectedTimeToPilot: string;
  problemSolved: string;
  howItWorks: string;
  benefitDescription: string;
  requiredInputs: string[];
  recommendedFirstStep: string;
  amacruxFit: string;
  relatedTools: string[];
  warning?: string;
  commercialCta: string;
}

export interface Recommendation {
  opportunity: Opportunity;
  score: number;
  confidence: Confidence;
  reasons: string[];
  warnings: string[];
  matchedFrictions: Friction[];
  matchedGoals: Goal[];
}

export interface ResultSummary {
  profileLabel: string;
  sectorLabel: string;
  maturityLabel: string;
  opportunityLevel: ScoreRange;
  opportunityLevelLabel: string;
}

export interface Result {
  version: 1;
  generatedAt: string;
  summary: ResultSummary;
  intro: string;
  recommendations: [Recommendation, Recommendation, Recommendation];
  shortTerm: string;
  midTerm: string;
  warnings: string[];
  cta: { label: string; intent: IntentLevel };
  segment: Segment;
  score: Score;
}

export type ContactDecision = "submitted" | "skipped";

/** Lo que se guarda en sessionStorage. Nunca incluye el lead. */
export interface StoredSession {
  version: 1;
  step: WizardStep;
  answers: PartialAnswers;
  startedAt: number;
  contactDecision?: ContactDecision;
}

export interface ResultSnapshot {
  scoreTotal: number;
  range: ScoreRange;
  leadTier: LeadTier;
  segment: Segment;
  recommendationIds: string[];
}

export interface Lead {
  name: string;
  company: string;
  email: string;
  role?: string;
  phone?: string;
  interest: OpportunityCategory;
  consentContact: true;
  consentMarketing: boolean;
  resultSnapshot: ResultSnapshot;
  /** Respuestas del diagnóstico (sin datos personales) para el resumen del correo. */
  answers: Answers;
  campaign?: string;
  utm?: Utm;
  idempotencyKey: string;
  /** Honeypot: las personas nunca lo ven; si llega relleno, no se envía nada. */
  fax?: string;
}

export interface AnalyticsProps {
  step?: string;
  profileCategory?: ProfileSegment;
  recommendationCategory?: OpportunityCategory;
  maturityLevel?: MaturitySegment;
  intentLevel?: IntentLevel;
  campaign?: string;
}

export interface AnalyticsEvent {
  name: AnalyticsEventName;
  props: AnalyticsProps & { ts: number };
}
