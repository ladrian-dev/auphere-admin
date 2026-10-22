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
] as const;

export async function ensureCategories(t: T): Promise<void> {
  if (Platform.OS !== "ios") return;
  await Promise.all(
    CATEGORIES.map((c) => Notifications.setNotificationCategoryAsync(c.id, [], { previewPlaceholder: t(c.placeholder) })),
  );
}
