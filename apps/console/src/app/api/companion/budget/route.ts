import { withCompanion } from "../_guard";

export const dynamic = "force-dynamic";

/** Month-to-date Companion spend, in tokens. Its own cap on purpose: the
 *  playground and the Companion must not steal budget from each other. */
export async function GET(): Promise<Response> {
  return withCompanion((b) => b.getCompanionBudget());
}
