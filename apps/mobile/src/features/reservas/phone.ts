import type { MessageKey } from "@/i18n/t";

/**
 * Spec 064 (requisito 3.2), on the phone (spec 069, R15.1, R16.1): the phone
 * of a booking made by hand, and of someone put on the waitlist by hand. An
 * international number with its country prefix — a `+` and 8 to 15 digits —
 * written with the spaces, dashes and brackets people use. The same rule as
 * the web's `components/reservas/model/phone.ts`: the booking is linked to the
 * business's contact with exactly that number, who then gets its notices, so
 * a local number could be anyone's. A walk-in put on the list at the door is
 * the one exception (064 R3.7): that path never asks.
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

/** The sentence for each problem; «required» depends on who is asked for (booking or waitlist). */
export function phoneProblemKey(problem: PhoneProblem, required: MessageKey = "reservas.phone.required"): MessageKey {
  switch (problem) {
    case "required":
      return required;
    case "prefix":
      return "reservas.phone.prefix";
    case "chars":
      return "reservas.phone.chars";
    case "length":
      return "reservas.phone.length";
  }
}

/** The phone as it is sent: its spaces kept, trimmed, one space at a time. */
export function cleanPhone(raw: string): string {
  return raw.replace(/\s+/g, " ").trim();
}
