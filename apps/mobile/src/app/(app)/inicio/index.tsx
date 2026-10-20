import { router, Stack } from "expo-router";

import { useHome, useMe } from "@/api/hooks";
import { HomeView } from "@/features/home/home-view";
import { useLocale, useT } from "@/i18n/t";
import { clock } from "@/lib/format";
import { ScrollScreen } from "@/ui/screen";
import { OfflineBanner, Skeleton } from "@/ui/states";
import { useOnline } from "@/ui/online";
import { Text } from "@/ui/text";

/** Inicio (R4.1): the Panel of the client, with its five states. */
export default function Inicio() {
  const t = useT();
  const locale = useLocale();
  const online = useOnline();
  const me = useMe();
  const home = useHome();
  const first = (me.data?.user.name ?? "").split(" ")[0] || me.data?.user.name || "";

  return (
    <>
      <Stack.Screen options={{ title: first ? t("app.home.greeting", { name: first }) : t("app.tab.panel") }} />
      <ScrollScreen refreshing={home.isRefetching} onRefresh={() => void home.refetch()} testID="inicio">
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
          />
        ) : (
          <Skeleton rows={4} />
        )}
      </ScrollScreen>
    </>
  );
}
