import { Stack } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { useState } from "react";

import { useMe, useUsageSpend, useUsageSummary } from "@/api/hooks";
import { CONSOLE_URL } from "@/config";
import { UsageView, type Period } from "@/features/usage/usage-view";
import { useLocale, useT } from "@/i18n/t";
import { clock } from "@/lib/format";
import { useActions } from "@/ui/actions";
import { useOnline } from "@/ui/online";
import { ScrollScreen } from "@/ui/screen";
import { OfflineBanner, Skeleton } from "@/ui/states";

/** Consumo (R4.2): read-only, the client's own money, in its five states. */
export default function Consumo() {
  const t = useT();
  const locale = useLocale();
  const online = useOnline();
  const actions = useActions();
  const me = useMe();
  const [days, setDays] = useState<Period>(30);
  const [agent, setAgent] = useState<string | null>(null);
  const summary = useUsageSummary();
  const spend = useUsageSpend(days, agent);
  const agents = (me.data?.agents ?? []).map((a) => ({ id: a.id, name: a.name }));

  const pickAgent = () =>
    actions(t("lite.usage.agent"), [
      { label: t("lite.usage.agent.all"), onPress: () => setAgent(null) },
      ...agents.map((a) => ({ label: a.name, onPress: () => setAgent(a.id) })),
    ]);

  return (
    <>
      <Stack.Screen options={{ title: t("app.tab.usage") }} />
      <ScrollScreen
        refreshing={summary.isRefetching}
        onRefresh={() => {
          void summary.refetch();
          void spend.refetch();
        }}
        testID="consumo"
      >
        {!online && summary.data ? <OfflineBanner since={clock(new Date(summary.dataUpdatedAt), locale)} /> : null}
        {summary.data || summary.isError ? (
          <UsageView
            summary={summary.data ?? null}
            spend={spend.data ?? null}
            spendFailed={spend.isError}
            days={days}
            onDays={setDays}
            agents={agents}
            agent={agent}
            onAgent={pickAgent}
            t={t}
            locale={locale}
            onRetry={() => void summary.refetch()}
            onWeb={() => void WebBrowser.openBrowserAsync(`${CONSOLE_URL}/usage`)}
          />
        ) : (
          <Skeleton rows={4} />
        )}
      </ScrollScreen>
    </>
  );
}
