import { withPrincipal } from "../_guard";

export const dynamic = "force-dynamic";

/**
 * Is the Companion turned on for this partner? — §10 of
 * `docs/companion/CONTRACT-V2.md`.
 *
 * `partners.companion_enabled` defaults to **false**: the pilot is
 * internal (Auphere first, two weeks of our own use, then Facelad and
 * Amacrux). The console reads it to decide whether to MOUNT the bubble.
 * An off bubble is absence, not a disabled button — a disabled button
 * advertises something you cannot have.
 *
 * Deliberately not behind `companion:use`. That permission answers a
 * different question ("your role cannot use it", which CO-03 already
 * answers with a disabled bubble and an explanation), and requiring it
 * here would make every analyst look like a partner without the feature.
 *
 * No parameter of any kind — least of all a `tenant_id` or a
 * `partner_id`. The partner is resolved from the principal.
 */
export async function GET(): Promise<Response> {
  return withPrincipal((b) => b.getCompanionEnabled());
}
