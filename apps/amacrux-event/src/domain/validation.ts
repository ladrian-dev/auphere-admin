import { z } from "zod";

import {
  AI_USAGES, ANALYTICS_EVENT_NAMES, CUSTOMER_TYPES, DATA_LOCATIONS, FRICTIONS, GOALS,
  INTENT_LEVELS, INVESTMENTS, LEAD_TIERS, MATURITY_SEGMENTS, OPPORTUNITY_CATEGORIES,
  PROFILES, PROFILE_SEGMENTS, SCORE_RANGES, SECTORS, TEAM_SIZES, TECH_CAPACITIES,
  URGENCIES, WIZARD_STEPS, WORK_LEVELS, COMPLEXITIES,
} from "./enums";

const unique = <T>(items: T[]) => new Set(items).size === items.length;

export const CampaignSchema = z.string().regex(/^[a-z0-9-]{1,64}$/, "Identificador de campaña no válido");

const utmValue = z.string().regex(/^[A-Za-z0-9_-]{1,64}$/);
export const UtmSchema = z
  .object({ source: utmValue.optional(), medium: utmValue.optional(), campaign: utmValue.optional(), content: utmValue.optional() })
  .strict();

export const FrictionsSchema = z
  .array(z.enum(FRICTIONS))
  .min(1, "Elige al menos una situación")
  .max(3, "Como máximo tres")
  .refine(unique, "Sin repetidos");

export const GoalsSchema = z
  .array(z.enum(GOALS))
  .min(1, "Elige al menos un objetivo")
  .max(2, "Como máximo dos")
  .refine(unique, "Sin repetidos");

export const AnswersSchema = z
  .object({
    profile: z.enum(PROFILES),
    sector: z.enum(SECTORS),
    teamSize: z.enum(TEAM_SIZES),
    customerType: z.enum(CUSTOMER_TYPES),
    workLevel: z.enum(WORK_LEVELS),
    aiUsage: z.enum(AI_USAGES),
    dataLocation: z.enum(DATA_LOCATIONS),
    frictions: FrictionsSchema,
    goals: GoalsSchema,
    urgency: z.enum(URGENCIES),
    techCapacity: z.enum(TECH_CAPACITIES),
    investment: z.enum(INVESTMENTS),
    campaign: CampaignSchema.optional(),
    utm: UtmSchema.optional(),
  })
  .strict();

export const PartialAnswersSchema = AnswersSchema.partial()
  .extend({
    frictions: z.array(z.enum(FRICTIONS)).max(3).refine(unique).optional(),
    goals: z.array(z.enum(GOALS)).max(2).refine(unique).optional(),
  })
  .strict();

export const SegmentSchema = z
  .object({
    profile: z.enum(PROFILE_SEGMENTS),
    maturity: z.enum(MATURITY_SEGMENTS),
    opportunityCategories: z.array(z.enum(OPPORTUNITY_CATEGORIES)).max(8),
    intent: z.enum(INTENT_LEVELS),
    complexity: z.enum(COMPLEXITIES),
  })
  .strict();

export const ResultSnapshotSchema = z
  .object({
    scoreTotal: z.number().int().min(0).max(100),
    range: z.enum(SCORE_RANGES),
    leadTier: z.enum(LEAD_TIERS),
    segment: SegmentSchema,
    recommendationIds: z.array(z.string().regex(/^[a-z0-9-]{1,64}$/)).length(3),
  })
  .strict();

const phone = z
  .string()
  .trim()
  .transform((v) => (v === "" ? undefined : v))
  .pipe(z.string().regex(/^[0-9+() -]{7,20}$/, "Teléfono no válido").optional());

export const LeadSchema = z
  .object({
    name: z.string().trim().min(2, "Escribe tu nombre").max(120),
    company: z.string().trim().min(1, "Escribe tu empresa").max(160),
    email: z.string().trim().toLowerCase().email("Correo no válido").max(200),
    role: z.string().trim().max(120).optional().transform((v) => (v && v.length > 0 ? v : undefined)),
    phone: phone.optional(),
    interest: z.enum(OPPORTUNITY_CATEGORIES),
    consentContact: z.literal(true, { errorMap: () => ({ message: "Necesitamos tu consentimiento para contactarte" }) }),
    consentMarketing: z.boolean().optional().default(false),
    resultSnapshot: ResultSnapshotSchema,
    answers: AnswersSchema,
    campaign: CampaignSchema.optional(),
    utm: UtmSchema.optional(),
    idempotencyKey: z.string().uuid(),
    fax: z.string().max(200).optional(),
  })
  .strict();

export type LeadInput = z.input<typeof LeadSchema>;
export type LeadParsed = z.output<typeof LeadSchema>;

/** Campos del formulario (antes de añadir snapshot, campaña e idempotencia). */
export const LeadFormSchema = LeadSchema.pick({
  name: true, company: true, email: true, role: true, phone: true, interest: true,
  consentContact: true, consentMarketing: true,
});
export type LeadFormValues = z.input<typeof LeadFormSchema>;

export const StoredSessionSchema = z
  .object({
    version: z.literal(1),
    step: z.enum(WIZARD_STEPS),
    answers: PartialAnswersSchema,
    startedAt: z.number().int().nonnegative(),
    contactDecision: z.enum(["submitted", "skipped"]).optional(),
  })
  .strict();

export const AnalyticsEventSchema = z
  .object({
    name: z.enum(ANALYTICS_EVENT_NAMES),
    props: z
      .object({
        step: z.string().max(32).optional(),
        profileCategory: z.enum(PROFILE_SEGMENTS).optional(),
        recommendationCategory: z.enum(OPPORTUNITY_CATEGORIES).optional(),
        maturityLevel: z.enum(MATURITY_SEGMENTS).optional(),
        intentLevel: z.enum(INTENT_LEVELS).optional(),
        campaign: CampaignSchema.optional(),
        ts: z.number(),
      })
      .strict(),
  })
  .strict();
