import { Stack } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { useState } from "react";

import { useMe, useUsageSpend, useUsageSummary } from "@/api/hooks";
import { CONSOLE_URL } from "@/config";
import { SettingsToolbar } from "@/features/tab-stack";
import { UsageView, type Period } from "@/features/usage/usage-view";
import { useLocale, useT } from "@/i18n/t";
import { clock } from "@/lib/format";
import { usePullRefresh } from "@/lib/use-pull-refresh";
import { useActions } from "@/ui/actions";
import { useOnline } from "@/ui/online";
import { ScrollScreen } from "@/ui/screen";
import { OfflineBanner, Skeleton } from "@/ui/states";

/**
 * Consumo (R4.2): read-only, the client's own money, in its five states.
 * The 90-day series is read first (spec 042, R9.2): it contains the other
 * two, so it decides whether there is anything to chart before a period is
 * offered. The chosen period is read only when there is.
 */
export default function Consumo() {
  const t = useT();
  const locale = useLocale();
  const online = useOnline();
  const actions = useActions();
  const me = useMe();
  const [days, setDays] = useState<Period>(30);
  const [agent, setAgent] = useState<string | null>(null);
  const summary = useUsageSummary();
  const wide = useUsageSpend(90, agent);
  const anySpend = wide.data ? wide.data.series_cents.some((c) => c > 0) : null;
  const narrow = useUsageSpend(days, agent, anySpend === true && days !== 90);
  const spend = days === 90 ? wide : narrow;
  const agents = (me.data?.agents ?? []).map((a) => ({ id: a.id, name: a.name }));

  const pickAgent = () =>
    actions(t("lite.usage.agent"), [
      { label: t("lite.usage.agent.all"), onPress: () => setAgent(null) },
      ...agents.map((a) => ({ label: a.name, onPress: () => setAgent(a.id) })),
    ]);

  const pull = usePullRefresh(() => Promise.all([summary.refetch(), wide.refetch(), days !== 90 && anySpend ? narrow.refetch() : null]));

  return (
    <>
      <Stack.Screen options={{ title: t("app.tab.usage") }} />
      <SettingsToolbar />
      <ScrollScreen
        refreshing={pull.refreshing}
        onRefresh={pull.onRefresh}
        testID="consumo"
      >
        {!online && summary.data ? <OfflineBanner since={clock(new Date(summary.dataUpdatedAt), locale)} /> : null}
        {summary.data || summary.isError ? (
          <UsageView
            summary={summary.data ?? null}
            spend={spend.data ?? null}
            spendFailed={spend.isError || (anySpend === null && wide.isError)}
            anySpend={anySpend}
            days={days}
            onDays={setDays}
            agents={agents}
            agent={agent}
            onAgent={pickAgent}
            t={t}
            locale={locale}
            onRetry={() => void summary.refetch()}
            onWeb={() => void WebBrowser.openBrowserAsync(`${CONSOLE_URL}/usage`)}
            contact={me.data?.balance_contact ?? null}
          />
        ) : (
          <Skeleton rows={4} />
        )}
      </ScrollScreen>
    </>
  );
}
