import { router, Stack } from "expo-router";

import { useAgents, useHasModule, useHome, useMe } from "@/api/hooks";
import { useBizNow, useBizToday, useHasReservas, useReservasConfig, useReservasRange, useWaitlist } from "@/api/reservas-hooks";
import type { AgentsRead } from "@/features/agents/agents-group";
import type { TodayReservas } from "@/features/home/today-reservas";
import { HomeView } from "@/features/home/home-view";
import { SettingsToolbar } from "@/features/tab-stack";
import { useLocale, useT } from "@/i18n/t";
import { clock } from "@/lib/format";
import { usePullRefresh } from "@/lib/use-pull-refresh";
import { ScrollScreen } from "@/ui/screen";
import { OfflineBanner, Skeleton } from "@/ui/states";
import { useOnline } from "@/ui/online";
import { Text } from "@/ui/text";

/**
 * Inicio (R4.1): the Panel of the client, with its five states. With
 * Reservas (spec 044, R9), today's reservations from the same read as the
 * Reservas tab (research D4).
 */
export default function Inicio() {
  const t = useT();
  const locale = useLocale();
  const online = useOnline();
  const me = useMe();
  const home = useHome();
  const first = (me.data?.user.name ?? "").split(" ")[0] || me.data?.user.name || "";
  const reservas = useTodayReservas();
  const agents = useHomeAgents();
  const hasBusiness = useHasModule("business");
  const pull = usePullRefresh(() => Promise.all([home.refetch(), agents.refetch()]));

  return (
    <>
      <Stack.Screen options={{ title: first ? t("app.home.greeting", { name: first }) : t("app.tab.panel") }} />
      <SettingsToolbar />
      <ScrollScreen refreshing={pull.refreshing} onRefresh={pull.onRefresh} testID="inicio">
        {me.data ? (
          <Text variant="subhead" tone="mutedForeground">
            {me.data.client.name}
          </Text>
        ) : null}
        {!online && home.data ? <OfflineBanner since={clock(new Date(home.dataUpdatedAt), locale)} /> : null}
        {me.data && (home.data || home.isError) ? (
          <HomeView
            me={me.data}
            home={home.data ?? null}
            t={t}
            locale={locale}
            onRetry={() => void home.refetch()}
            onAttend={(id) => (id ? router.push(`/conversacion/${id}`) : router.navigate("/bandeja"))}
            onUsage={() => router.navigate("/consumo")}
            onInbox={() => router.navigate("/bandeja")}
            reservas={reservas.today}
            onReservas={() => router.navigate({ pathname: "/reservas", params: reservas.date ? { date: reservas.date } : {} })}
            agents={agents.read}
            onAgent={(id) => router.push(`/agente/${id}`)}
            onBusiness={hasBusiness ? () => router.push("/negocio") : undefined}
            businessHint={me.data?.business?.hours_label ?? null}
          />
        ) : (
          <Skeleton rows={4} />
        )}
      </ScrollScreen>
    </>
  );
}

/** Spec 047 (50.1): the agents for Inicio, or `null` without the module. */
function useHomeAgents(): { read: AgentsRead | null; refetch: () => Promise<unknown> } {
  const has = useHasModule("agents");
  const q = useAgents(has);
  const refetch = () => (has ? q.refetch() : Promise.resolve());
  if (!has) return { read: null, refetch };
  if (q.data) return { read: { state: "ready", items: q.data.items }, refetch };
  if (q.isError) return { read: { state: "error", retry: () => void q.refetch() }, refetch };
  return { read: { state: "loading" }, refetch };
}

/** Today in Reservas for Inicio, or `null` without the module (R1.2). */
function useTodayReservas(): { today: TodayReservas | null; date: string | null } {
  const has = useHasReservas();
  const config = useReservasConfig(has);
  const date = useBizToday(config.data);
  const range = useReservasRange(has ? date : null, has ? date : null);
  const capacity = config.data?.mode === "capacity";
  const waitlist = useWaitlist(has && capacity);
  const now = useBizNow(range.data?.now);
  if (!has) return { today: null, date: null };
  if (config.isError || (range.isError && !range.data)) {
    return {
      today: {
        state: "error",
        retry: () => {
          void config.refetch();
          void range.refetch();
        },
      },
      date,
    };
  }
  if (!config.data || !range.data || !now) return { today: { state: "loading" }, date };
  const waiting = capacity && waitlist.data ? waitlist.data.filter((w) => w.state !== "accepted" && (w.wants.date === null || w.wants.date === now.date)).length : null;
  return { today: { state: "ready", config: config.data, items: range.data.items, now, waitlist: waiting }, date };
}
