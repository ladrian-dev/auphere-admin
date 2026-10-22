import * as Notifications from "expo-notifications";
import { NativeTabs } from "expo-router/native-tabs";
import { useEffect, useRef } from "react";
import { router } from "expo-router";

import { useCounts, useMe } from "@/api/hooks";
import { noticesAsked } from "@/auth/store";
import { MeGateState } from "@/features/me-gate";
import { useT } from "@/i18n/t";
import { MODULES, TAB_BAR_MINIMIZE, knownModules, tabPlan } from "@/lib/modules";
import { useInboxStream } from "@/api/sse";
import { useTheme } from "@/theme/theme";

/**
 * The signed-in app: one native tab per module of the client, in the API's
 * order (R3.1, R3.2), from the same `/me` the web's sidebar reads.
 *
 * - Every module the app knows is declared, and the ones the client lacks are
 *   `hidden` — native tabs cannot be added at run time. Changing the set or
 *   the order remounts the navigator on purpose (`key`): the person lands on
 *   the first module, never on a tab that no longer exists (R3.5).
 * - One module: no tab bar at all (R3.4).
 * - The Bandeja's badge is what waits for a person, so the bar never
 *   minimizes while scrolling (spec 042, H22).
 */
export default function AppLayout() {
  const me = useMe();
  const t = useT();
  const { colors } = useTheme();
  const nav = me.data?.nav ?? [];
  const visible = knownModules(nav);
  const hasInbox = visible.includes("inbox");
  const counts = useCounts(hasInbox);
  useInboxStream(hasInbox);

  // The app's badge is what waits for a person (R8, same number as the tab).
  const waitingCount = counts.data?.waiting;
  useEffect(() => {
    if (waitingCount !== undefined) void Notifications.setBadgeCountAsync(waitingCount).catch(() => undefined);
  }, [waitingCount]);

  // R10.1: right after the first sign-in on this phone, say what we notify about.
  // Once per launch at most: `/me` is re-read on every return to the foreground.
  const offered = useRef(false);
  const ready = Boolean(me.data);
  useEffect(() => {
    if (!ready || offered.current) return;
    offered.current = true;
    void noticesAsked().then((asked) => {
      if (!asked) router.push("/notices-permission");
    });
  }, [ready]);

  if (!me.data || visible.length === 0) return <MeGateState query={me} />;

  const waiting = counts.data?.waiting ?? 0;
  return (
    <NativeTabs
      key={visible.join(",")}
      hidden={visible.length === 1}
      tintColor={colors.primaryText}
      minimizeBehavior={TAB_BAR_MINIMIZE}
    >
      {tabPlan(nav).map(({ module, hidden }) => {
        const m = MODULES[module];
        return (
          <NativeTabs.Trigger key={module} name={m.route} hidden={hidden}>
            <NativeTabs.Trigger.Icon sf={{ default: m.icon.ios, selected: m.selected.ios }} md={m.icon.android} />
            <NativeTabs.Trigger.Label>{t(m.label)}</NativeTabs.Trigger.Label>
            {module === "inbox" && waiting > 0 ? (
              <NativeTabs.Trigger.Badge>{waiting > 99 ? "99+" : String(waiting)}</NativeTabs.Trigger.Badge>
            ) : null}
          </NativeTabs.Trigger>
        );
      })}
    </NativeTabs>
  );
}
