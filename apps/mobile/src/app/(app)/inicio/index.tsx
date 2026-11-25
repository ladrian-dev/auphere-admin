import { router, Stack } from "expo-router";
import { useIsFocused } from "expo-router/react-navigation";
import { RefreshControl, ScrollView, StyleSheet } from "react-native";

import { useHome, useMe } from "@/api/hooks";
import { useBizNow, useBizToday, useHasReservas, useReservasConfig, useReservasRange, useWaitlist } from "@/api/reservas-hooks";
import { HomeView } from "@/features/home/home-view";
import { useHomeCounts, useHomeInbox } from "@/features/home/reads";
import { HomeSkeleton } from "@/features/home/skeleton";
import type { TodayReservas } from "@/features/home/today-reservas";
import { SettingsToolbar } from "@/features/tab-stack";
import { useLocale, useT } from "@/i18n/t";
import { clock } from "@/lib/format";
import { usePullRefresh } from "@/lib/use-pull-refresh";
import { useTheme } from "@/theme/theme";
import { useOnline } from "@/ui/online";
import { OfflineBanner } from "@/ui/states";

/**
 * Inicio (spec 069, R8): «Hola, {nombre}» as the large title, the day in four
 * tiles, the latest of the Bandeja and, at the bottom, whoever waits. Its six
 * states: the skeleton of the final layout, error with «Reintentar», partial,
 * a new business in words, ideal, and offline with the time of the last read.
 * No agents and no way into Negocio: neither is a client's module (spec 056, 2.6).
 */
export default function Inicio() {
  const t = useT();
  const locale = useLocale();
  const { colors } = useTheme();
  const online = useOnline();
  const focused = useIsFocused();
  const me = useMe();
  const home = useHome();
  const nav = me.data?.nav ?? [];
  const hasInbox = nav.includes("inbox");
  const inbox = useHomeInbox(hasInbox, (home.data?.waiting?.count ?? 0) > 0);
  const counts = useHomeCounts(hasInbox);
  const first = (me.data?.user.name ?? "").split(" ")[0] || me.data?.user.name || "";
  const reservas = useTodayReservas();
  const pull = usePullRefresh(() => Promise.all([home.refetch(), inbox.refetch(), hasInbox ? counts.refetch() : null]));

  /** One rule from Inicio (log, decision 3): a conversation opens in the Bandeja's tab, so «back» lands there. */
  const openInBandeja = (id: string | null) => {
    router.navigate("/bandeja");
    if (id) router.push(`/conversacion/${id}`);
  };

  return (
    <>
      <Stack.Screen options={{ title: first ? t("app.home.greeting", { name: first }) : t("app.tab.panel") }} />
      <SettingsToolbar />
      {/* Its own scroll, not `ScrollScreen`: the content grows to the screen so the bottom card stays in the thumb's reach. */}
      <ScrollView
        testID="inicio"
        style={{ backgroundColor: colors.background }}
        contentInsetAdjustmentBehavior="automatic"
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={pull.refreshing} onRefresh={pull.onRefresh} tintColor={colors.primaryText} colors={[colors.primaryDeep]} />}
      >
        {!online && home.data ? <OfflineBanner since={clock(new Date(home.dataUpdatedAt), locale)} /> : null}
        {me.data && (home.data || home.isError) ? (
          <HomeView
            me={me.data}
            home={home.data ?? null}
            t={t}
            locale={locale}
            focused={focused}
            onRetry={() => void home.refetch()}
            onAttend={openInBandeja}
            onOpenConversation={openInBandeja}
            onUsage={() => router.navigate("/consumo")}
            onInbox={() => router.navigate("/bandeja")}
            reservas={reservas.today}
            onReservas={() => router.navigate({ pathname: "/reservas", params: reservas.date ? { date: reservas.date } : {} })}
            latest={inbox.latest}
            waiting={inbox.waiting}
            counts={counts.data ?? null}
          />
        ) : (
          <HomeSkeleton />
        )}
      </ScrollView>
    </>
  );
}

/** Today in Reservas for Inicio, or `null` without the module (R8.2). */
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

const styles = StyleSheet.create({
  content: { flexGrow: 1, padding: 16, gap: 16, paddingBottom: 32 },
});
