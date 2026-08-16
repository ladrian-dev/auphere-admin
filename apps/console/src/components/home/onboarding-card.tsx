import { backendFor } from "@/lib/backend";
import type { Principal } from "@/lib/principal";

import { OnboardingCardClient } from "./onboarding-card-client";

/**
 * Home "getting started" card (CP-29). Server component: fetches
 * ``GET /console/onboarding`` (best-effort — renders an error state, never
 * throws into the page) and hands the data to the client card, which owns
 * the dismissal (localStorage, per person/browser). Hidden once complete
 * or dismissed. Mount it from ``app/(console)/page.tsx``:
 *
 *   <OnboardingCard principal={principal} />
 */
export async function OnboardingCard({ principal }: { principal: Principal }) {
  const data = await backendFor(principal).onboarding().catch(() => null);
  return <OnboardingCardClient data={data} role={principal.role} />;
}
