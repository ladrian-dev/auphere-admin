import * as Notifications from "expo-notifications";
import { AppState } from "react-native";

import { conversationOf } from "./routing";

/**
 * R8.7: while a conversation is open on screen, its own notices are not
 * shown — the person is already looking at it. Everything else shows as the
 * system would. The thread screen says which conversation is open.
 */
let open: string | null = null;

export function setOpenConversation(id: string | null): void {
  open = id;
}

export function shouldPresent(data: unknown, appState: string | null | undefined = AppState.currentState): boolean {
  const id = conversationOf(data);
  return !(id && id === open && appState === "active");
}

export function installHandler(): void {
  Notifications.setNotificationHandler({
    handleNotification: async (n) => {
      const show = shouldPresent(n.request.content.data);
      return { shouldShowBanner: show, shouldShowList: show, shouldPlaySound: show, shouldSetBadge: true };
    },
  });
}
