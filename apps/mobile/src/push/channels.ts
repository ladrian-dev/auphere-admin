import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

import type { T } from "@/i18n/t";

/**
 * One Android channel per kind (R8.9; Reservas' three share one, spec 044 R14.6), so the person decides each one's
 * importance in the phone's settings. All of them are PRIVATE on the lock
 * screen (R8.10): with the phone locked, Android shows only that there is a
 * notification. The ids are the API's (`push_payloads.KIND_CONFIG`); a
 * channel's importance cannot change once created, hence the `_v1`.
 */
export const CHANNELS = [
  { id: "waiting_v1", name: "app.notices.channel.waiting", importance: Notifications.AndroidImportance.HIGH },
  { id: "messages_v1", name: "app.notices.channel.messages", importance: Notifications.AndroidImportance.HIGH },
  { id: "balance_v1", name: "app.notices.channel.balance", importance: Notifications.AndroidImportance.DEFAULT },
  // Spec 044 (R14.6): Reservas' notices, not urgent — the system's default importance.
  { id: "reservations_v1", name: "avisos.channel.reservations", importance: Notifications.AndroidImportance.DEFAULT },
] as const;

export async function ensureChannels(t: T): Promise<void> {
  if (Platform.OS !== "android") return;
  await Promise.all(
    CHANNELS.map((c) =>
      Notifications.setNotificationChannelAsync(c.id, {
        name: t(c.name),
        importance: c.importance,
        lockscreenVisibility: Notifications.AndroidNotificationVisibility.PRIVATE,
        showBadge: true,
        enableVibrate: true,
      }),
    ),
  );
}
