import { Stack } from "expo-router";
import { Alert, RefreshControl, ScrollView, StyleSheet } from "react-native";

import { demo } from "@/api/reservas";
import { useBizToday, useReservasConfig, useWaitlist, useWaitlistOffer, useWaitlistRemove } from "@/api/reservas-hooks";
import { useLocale, useT } from "@/i18n/t";
import { clock } from "@/lib/format";
import { useNowMs } from "@/lib/use-now";
import { usePullRefresh } from "@/lib/use-pull-refresh";
import { haptics } from "@/motion/haptics";
import { useTheme } from "@/theme/theme";
import { useOnline } from "@/ui/online";
import { useToast } from "@/ui/toast";

import { ReservasBody } from "./body";
import { errorText } from "./screen";
import { WaitlistView } from "./waitlist";

/** «Lista de espera», stacked inside the Reservas tab (spec 044, Requisito 7, D5). */
export default function WaitlistScreen() {
  const t = useT();
  const locale = useLocale();
  const online = useOnline();
  const toast = useToast();
  const { colors } = useTheme();
  const config = useReservasConfig();
  const today = useBizToday(config.data);
  const list = useWaitlist();
  const offer = useWaitlistOffer();
  const remove = useWaitlistRemove();
  // Offers count down in real time, from no earlier than the list was read.
  const now = useNowMs(15_000, list.dataUpdatedAt);

  const state = config.isError || (list.isError && !list.data) ? "error" : config.data && list.data && today ? "ready" : "loading";
  const pull = usePullRefresh(() => list.refetch());

  return (
    <>
      <Stack.Screen options={{ title: t("reservas.waitlist.title"), headerLargeTitleEnabled: false }} />
      <ScrollView
        style={{ backgroundColor: colors.background }}
        contentInsetAdjustmentBehavior="automatic"
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={pull.refreshing} onRefresh={pull.onRefresh} tintColor={colors.primaryText} />}
      >
        <ReservasBody
          state={state}
          offline={!online}
          demo={demo !== null}
          offlineSince={!online && list.data ? clock(new Date(list.dataUpdatedAt), locale) : null}
          partial={false}
          onRetry={() => void list.refetch()}
          t={t}
        >
          {config.data && list.data && today ? (
            <WaitlistView
              config={config.data}
              items={list.data}
              now={now}
              today={today}
              online={online}
              busy={offer.isPending || remove.isPending}
              t={t}
              locale={locale}
              onOffer={(w) =>
                offer.mutate(w.id, {
                  onSuccess: () => {
                    haptics.success();
                    toast.show({ text: t("reservas.waitlist.offered.toast", { name: w.name }) });
                  },
                  onError: (e) => toast.show({ text: errorText(e, t) }),
                })
              }
              onRemove={(w) =>
                Alert.alert(t("reservas.waitlist.remove.title", { name: w.name }), undefined, [
                  { text: t("app.cancel"), style: "cancel" },
                  {
                    text: t("reservas.waitlist.remove"),
                    style: "destructive",
                    onPress: () =>
                      remove.mutate(w.id, {
                        onSuccess: () => toast.show({ text: t("reservas.waitlist.removed") }),
                        onError: (e) => toast.show({ text: errorText(e, t) }),
                      }),
                  },
                ])
              }
            />
          ) : null}
        </ReservasBody>
      </ScrollView>
    </>
  );
}

const styles = StyleSheet.create({
  content: { padding: 16, paddingBottom: 48 },
});
