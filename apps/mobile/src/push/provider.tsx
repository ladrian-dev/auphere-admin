import * as Notifications from "expo-notifications";
import { router } from "expo-router";
import { createContext, use, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { AppState } from "react-native";

import { useSession } from "@/auth/session";
import { useT } from "@/i18n/t";

import { ensureCategories } from "./categories";
import { ensureChannels } from "./channels";
import { installHandler } from "./handler";
import { askPermission, readPermission, type Permission } from "./permission";
import { registerDevice } from "./register";
import { routeFor } from "./routing";

/**
 * Notices on this phone (spec 031, R8, R10): the system permission, the
 * device token handed to the API, and a tap that opens its screen — warm or
 * from a cold start. Normal notifications: the system shows them as they come.
 */
type PushApi = {
  permission: Permission | null;
  /** Ask the system (after our own explanation, R10.1). Registers on yes. */
  enable: () => Promise<Permission>;
};

const Ctx = createContext<PushApi | null>(null);

installHandler();

export function PushProvider({ children }: { children: ReactNode }) {
  const t = useT();
  const { state } = useSession();
  const signedIn = state.status === "signed-in";
  const [permission, setPermission] = useState<Permission | null>(null);
  const lastHandled = useRef<string | null>(null);

  useEffect(() => {
    void ensureChannels(t).catch(() => undefined);
    void ensureCategories(t).catch(() => undefined);
  }, [t]);

  // The permission can change in the phone's settings while the app is away.
  useEffect(() => {
    const read = () => void readPermission().then(setPermission).catch(() => undefined);
    read();
    const sub = AppState.addEventListener("change", (s) => s === "active" && read());
    return () => sub.remove();
  }, []);

  // Signed in with permission: hand the token to the API, and again if the system rotates it.
  useEffect(() => {
    if (!signedIn || permission !== "granted") return;
    void registerDevice();
    const sub = Notifications.addPushTokenListener((token) => void registerDevice(token));
    return () => sub.remove();
  }, [signedIn, permission]);

  // A tap opens the fact's screen (R8.6), including the one that launched the app.
  const last = Notifications.useLastNotificationResponse();
  useEffect(() => {
    if (!signedIn || !last || last.actionIdentifier !== Notifications.DEFAULT_ACTION_IDENTIFIER) return;
    const key = last.notification.request.identifier;
    if (lastHandled.current === key) return;
    lastHandled.current = key;
    const route = routeFor(last.notification.request.content.data);
    if (route) router.push(route);
  }, [last, signedIn]);

  // Signed out: no badge left behind (R7.1).
  useEffect(() => {
    if (state.status === "signed-out") void Notifications.setBadgeCountAsync(0).catch(() => undefined);
  }, [state.status]);

  const enable = useCallback(async () => {
    await ensureChannels(t).catch(() => undefined);
    const next = await askPermission().catch(() => "denied" as const);
    setPermission(next);
    return next;
  }, [t]);

  const value = useMemo(() => ({ permission, enable }), [permission, enable]);
  return <Ctx value={value}>{children}</Ctx>;
}

export function usePush(): PushApi {
  const ctx = use(Ctx);
  if (!ctx) throw new Error("usePush outside PushProvider");
  return ctx;
}
