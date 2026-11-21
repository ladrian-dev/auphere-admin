import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

import type { T } from "@/i18n/t";

/**
 * iOS categories (R8.10, R8.12): no actions at all — nothing is answered or
 * taken over from a notice — and a neutral placeholder when the person hides
 * previews on the lock screen. The ids are the API's (`KIND_CONFIG`).
 */
export const CATEGORIES = [
  { id: "inbox_waiting", placeholder: "app.notices.placeholder.waiting" },
  { id: "inbox_message", placeholder: "app.notices.placeholder.message" },
  { id: "client_balance", placeholder: "app.notices.placeholder.balance" },
  // Spec 044 (R14.6): Reservas' notices, with no actions either.
  { id: "reservations", placeholder: "avisos.placeholder.reservations" },
  // Spec 047 (T170): `agents.state`, the agents' and numbers' notices; the bag's three use `client_balance`.
  { id: "agents", placeholder: "avisos.placeholder.agents" },
] as const;

/**
 * One at a time, never `Promise.all`: on SDK 58, expo-notifications turns each
 * reply into JS off the JS thread, and five at once crashed the app at launch on
 * iOS 26 (EXC_BAD_ACCESS in Hermes, spec 069). The order is the list's.
 */
let queue: Promise<void> = Promise.resolve();

export function ensureCategories(t: T): Promise<void> {
  if (Platform.OS !== "ios") return Promise.resolve();
  // A second call (the effect again, in another language) waits for the first.
  const run = queue.then(async () => {
    for (const c of CATEGORIES) {
      await Notifications.setNotificationCategoryAsync(c.id, [], { previewPlaceholder: t(c.placeholder) });
    }
  });
  queue = run.catch(() => undefined);
  return run;
}
