import { router, Stack } from "expo-router";
import { RefreshControl, ScrollView, StyleSheet } from "react-native";

import { ApiError } from "@/api/errors";
import { demo } from "@/api/reservas";
import {
  useBizToday,
  useDeferredRemoveWait,
  useOffers,
  useReservasConfig,
  useStopOffer,
  useWaitlist,
  useWaitlistOffer,
  useWithPendingRemovals,
} from "@/api/reservas-hooks";
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

/**
 * «Lista de espera», stacked inside the Reservas tab (spec 044, Requisito 7,
 * D5; spec 069, Requisito 16): the offers running now with «Parar», the
 * people with «Reservarle ahora», «Ofrecer ahora» and «Quitar» — which waits
 * for «Deshacer» before it reaches the API (micro 6) — and «Apuntar a alguien».
 */
export default function WaitlistScreen() {
  const t = useT();
  const locale = useLocale();
  const online = useOnline();
  const toast = useToast();
  const { colors } = useTheme();
  const config = useReservasConfig();
  const today = useBizToday(config.data);
  const list = useWaitlist();
  const offers = useOffers(config.data?.waitlist.enabled ?? false);
  const offer = useWaitlistOffer();
  const stop = useStopOffer();
  const removeLater = useDeferredRemoveWait();
  const items = useWithPendingRemovals(list.data);
  // Offers count down in real time, from no earlier than the list was read.
  const now = useNowMs(15_000, list.dataUpdatedAt);

  const state = config.isError || (list.isError && !list.data) ? "error" : config.data && items && today ? "ready" : "loading";
  const pull = usePullRefresh(() => Promise.all([list.refetch(), offers.refetch()]));

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
          // The offers did not load: the people still show, and it is said.
          partial={offers.isError && !offers.data}
          partialText={t("reservas.wl.offers.partial")}
          onRetry={() => void list.refetch()}
          t={t}
        >
          {config.data && items && today ? (
            <WaitlistView
              config={config.data}
              items={items}
              offers={offers.data ?? []}
              now={now}
              today={today}
              online={online}
              busy={offer.isPending || stop.isPending}
              t={t}
              locale={locale}
              // A new route: the typed routes learn it on the next `expo start`.
              onAdd={() => router.push("/reservas/apuntar")}
              onBook={(w) => {
                const c = config.data!;
                const service = c.services?.catalog.find((s) => s.name === w.wants.service);
                const pro = c.services?.team.find((p) => p.name === w.wants.pro);
                router.push({
                  pathname: "/reserva/nueva",
                  params: {
                    date: w.wants.date && w.wants.date >= today ? w.wants.date : today,
                    name: w.name,
                    ...(w.phone ? { phone: w.phone } : {}),
                    ...(service ? { service: service.id } : {}),
                    ...(pro ? { pro: pro.id } : {}),
                    ...(w.wants.time != null ? { time: String(w.wants.time) } : {}),
                    ...(w.wants.partySize ? { party: String(w.wants.partySize) } : {}),
                  },
                });
              }}
              onOffer={(w) =>
                offer.mutate(w.id, {
                  onSuccess: () => {
                    haptics.success();
                    toast.show({ text: t("reservas.waitlist.offered.toast", { name: w.name }), tone: "ok" });
                  },
                  onError: (e) => toast.show({ text: errorText(e, t), tone: "warn" }),
                })
              }
              onStopOffer={(o) =>
                stop.mutate(o.id, {
                  onSuccess: () => {
                    haptics.warning();
                    toast.show({ text: t("reservas.wl.offer.stopped"), tone: "info" });
                  },
                  onError: (e) => toast.show({ text: errorText(e, t), tone: "warn" }),
                })
              }
              onRemove={(w) => {
                haptics.warning();
                const undo = removeLater(w.id, (e) =>
                  toast.show({ text: e instanceof ApiError && e.offline ? errorText(e, t) : t("reservas.wl.remove.failed"), tone: "warn" }),
                );
                toast.show({
                  text: t("reservas.wl.removed", { name: w.name }),
                  tone: "ok",
                  action: {
                    label: t("reservas.action.undo"),
                    onPress: () => {
                      if (undo()) haptics.light();
                      else toast.show({ text: t("reservas.undo.late"), tone: "warn" });
                    },
                  },
                });
              }}
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
