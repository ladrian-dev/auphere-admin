import type { MessageKey } from "@/i18n/messages";

/**
 * Spec 064 (requisito 3.2): the phone of a booking made by hand. An
 * international number with its country prefix — a `+` and 8 to 15 digits —
 * written with the spaces, dashes and brackets people use.
 *
 * The prefix is required because the booking is linked to the business's
 * contact with exactly that number, who then gets its notices: a local number
 * could be anyone's. The waitlist asks for it with the same rule (spec 064, 3.7).
 */
const SHAPE = /^\+[0-9 ()-]*$/;

export type PhoneProblem = "required" | "prefix" | "chars" | "length";

/** What is wrong with `raw`, so the field says the right thing (WCAG 3.3.3), or `null`. */
export function phoneProblem(raw: string): PhoneProblem | null {
  const phone = raw.trim();
  if (!phone) return "required";
  if (!phone.startsWith("+")) return "prefix";
  if (!SHAPE.test(phone)) return "chars";
  const digits = phone.replace(/\D/g, "").length;
  return digits >= 8 && digits <= 15 ? null : "length";
}

export function validPhone(raw: string): boolean {
  return phoneProblem(raw) === null;
}

export const PHONE_PROBLEM_KEY = {
  required: "reservas.form.phoneRequired",
  prefix: "reservas.form.phonePrefix",
  chars: "reservas.form.phoneChars",
  length: "reservas.form.phoneLength",
} as const satisfies Record<PhoneProblem, MessageKey>;
