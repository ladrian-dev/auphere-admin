import { z } from "zod";

import {
  ESCALATION_TRIGGERS,
  TONES,
  WEEKDAYS,
  type ConsolePolicy,
  type ScheduleSlot,
  type Weekday,
} from "@/lib/backend/agent-tools-types";

/**
 * Zod mirror of `services/agent_console_policy.py::ConsolePolicy` (strict,
 * same limits, same cross-field rules). Pure module: used by the form
 * (client), by the Server Action (server) and by tests. Messages are
 * injectable so the form can show translated errors while the action
 * keeps English defaults.
 */

export const TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/;
export const SCHEMA_VERSION = 1;

export type SchemaMessages = {
  tooLong: string;
  time: string;
  openBeforeClose: string;
  timezone: string;
  turnsRequired: string;
  language: string;
};

const DEFAULT_MESSAGES: SchemaMessages = {
  tooLong: "Too long.",
  time: "Use HH:MM (24 h).",
  openBeforeClose: "Opening time must be before closing time.",
  timezone: "Unknown timezone.",
  turnsRequired: "Set the number of turns for that trigger.",
  language: "Use a language code (2–8 chars).",
};

/** IANA check with what the runtime has (Intl); mirrors `zoneinfo` server-side. */
export function isValidTimezone(tz: string): boolean {
  if (!tz || tz.length > 64) return false;
  try {
    new Intl.DateTimeFormat("en", { timeZone: tz });
    return true;
  } catch {
    return false;
  }
}

export function buildConsolePolicySchema(m: Partial<SchemaMessages> = {}) {
  const msg = { ...DEFAULT_MESSAGES, ...m };
  const time = z.string().regex(TIME_RE, msg.time);
  const slot = z
    .object({ day: z.enum(WEEKDAYS), open: time, close: time })
    .strict()
    .refine((s) => !TIME_RE.test(s.open) || !TIME_RE.test(s.close) || s.open < s.close, { message: msg.openBeforeClose, path: ["close"] });
  return z
    .object({
      schema_version: z.number().int().min(1).max(SCHEMA_VERSION).default(SCHEMA_VERSION),
      identity: z.object({ name: z.string().max(120, msg.tooLong).default(""), persona: z.string().max(2000, msg.tooLong).default("") }).strict().default({}),
      tone: z.object({ style: z.enum(TONES).default("cercano"), guidance: z.string().max(2000, msg.tooLong).default("") }).strict().default({}),
      objective: z.string().max(4000, msg.tooLong).default(""),
      schedule: z
        .object({
          timezone: z.string().max(64, msg.tooLong).refine(isValidTimezone, msg.timezone).default("UTC"),
          weekly: z.array(slot).max(21).default([]),
          closed_message: z.string().max(1000, msg.tooLong).default(""),
        })
        .strict()
        .default({}),
      languages: z
        .object({
          primary: z.string().min(2, msg.language).max(8, msg.language).default("es"),
          allowed: z.array(z.string().min(2, msg.language).max(8, msg.language)).max(20).default([]),
        })
        .strict()
        .default({}),
      escalation: z
        .object({
          enabled: z.boolean().default(true),
          triggers: z.array(z.enum(ESCALATION_TRIGGERS)).default(["user_asks_human", "angry", "out_of_scope"]),
          after_n_turns: z.number().int().min(1).max(100).nullable().default(null),
          handoff_message: z.string().max(1000, msg.tooLong).default(""),
        })
        .strict()
        .refine((e) => !e.triggers.includes("after_n_turns") || e.after_n_turns != null, { message: msg.turnsRequired, path: ["after_n_turns"] })
        .default({}),
      ai_disclosure: z
        .object({
          enabled: z.boolean().default(true),
          disclosure_message: z.string().max(500, msg.tooLong).default(""),
          decided_by: z.string().max(255).nullable().default(null),
          decided_at: z.string().nullable().default(null),
        })
        .strict()
        .default({}),
    })
    .strict();
}

export const consolePolicySchema = buildConsolePolicySchema();
export type ConsolePolicyInput = z.input<typeof consolePolicySchema>;

/** Same shape as the API default (`ConsolePolicy()` in Python). */
export function defaultConsolePolicy(): ConsolePolicy {
  return {
    schema_version: SCHEMA_VERSION,
    identity: { name: "", persona: "" },
    tone: { style: "cercano", guidance: "" },
    objective: "",
    schedule: { timezone: "UTC", weekly: [], closed_message: "" },
    languages: { primary: "es", allowed: ["es"] },
    escalation: { enabled: true, triggers: ["user_asks_human", "angry", "out_of_scope"], after_n_turns: null, handoff_message: "" },
    ai_disclosure: { enabled: true, disclosure_message: "", decided_by: null, decided_at: null },
  };
}

/** Slot indexes grouped per weekday, in Monday→Sunday order (indexes point
 *  into the flat `weekly` array so the form can remove by index). */
export function groupSlotsByDay(weekly: ScheduleSlot[]): Array<{ day: Weekday; slots: Array<{ index: number; slot: ScheduleSlot }> }> {
  return WEEKDAYS.map((day) => ({
    day,
    slots: weekly.map((slot, index) => ({ index, slot })).filter((x) => x.slot.day === day),
  }));
}

/** "es, en, pt" → ["es","en","pt"] (lower-case, trimmed, deduplicated). */
export function parseLanguageList(text: string): string[] {
  return Array.from(new Set(text.split(/[,\s;]+/).map((s) => s.trim().toLowerCase()).filter(Boolean)));
}
