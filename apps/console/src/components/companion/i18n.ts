import { type MessageKey, messages } from "@/i18n/messages";

/**
 * Optional lookup for the identifiers the backend sends (§1.4 of
 * `docs/companion/CONTRACT-V1.md`): `phase`, `verify.checks[].name`,
 * `impact[].key`, `intake.slots[].key`, `kind`, tool names.
 *
 * The rule is that the backend emits a stable identifier and this app
 * emits the human wording — but the identifier set grows with CO-04 and
 * beyond. Returning `null` for an unknown one lets each caller fall back
 * to what the backend actually sent, which is always better than a blank
 * cell or a raw snake_case key shown as if it were a sentence.
 *
 * Same shape as the existing `statusKey` / `roleKey` helpers.
 */
export function optionalKey(candidate: string): MessageKey | null {
  return candidate in messages ? (candidate as MessageKey) : null;
}
