import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";

import { ApiError } from "@/api/errors";
import type { MoreAction, ResAction } from "@/api/reservas";
import {
  useBizToday,
  useCancelPreview,
  useDeferredCancel,
  useHasInbox,
  useRequestConfirmation,
  useReservasConfig,
  useReservation,
  useWithPendingCancels,
} from "@/api/reservas-hooks";
import { CancelPanel } from "@/features/reservas/cancel-panel";
import { errorText, useActOn } from "@/features/reservas/screen";
import { ReservaSheet } from "@/features/reservas/sheet";
import { useLocale, useT } from "@/i18n/t";
import { haptics } from "@/motion/haptics";
import { glassAvailable } from "@/theme/glass";
import { useTheme } from "@/theme/theme";
import { icons } from "@/ui/icon";
import { useOnline } from "@/ui/online";
import { EmptyState, ErrorState, Skeleton } from "@/ui/states";
import { useToast } from "@/ui/toast";

/**
 * One reservation, as a sheet over Reservas (spec 044 Requisito 4, D5; spec
 * 069 Requisito 14): the detail read, with its history, by id — a notice or a
 * link brings nothing else — and every action through the API with its
 * version. Cancelling asks first, in the sheet: tell the customer or not, and
 * offer the slot to the waitlist or not (R14.2); then the sheet closes and the
 * notice offers «Deshacer» while nothing has gone out yet (micro 6).
 */
export default function ReservaRoute() {
  const { id } = useLocalSearchParams<{ id: string; date?: string }>();
  const t = useT();
  const locale = useLocale();
  const online = useOnline();
  const toast = useToast();
  const { colors } = useTheme();
  const config = useReservasConfig();
  const today = useBizToday(config.data);
  const hasInbox = useHasInbox();
  // The detail read: the reservation and its history (043 §4). A notice or a link brings only the id.
  const one = useReservation(id ?? null);
  const act = useActOn(t);
  const ask = useRequestConfirmation();
  const deferCancel = useDeferredCancel();
  const r = useWithPendingCancels(one.data ? [one.data] : undefined)?.[0] ?? null;
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState<"detail" | "cancel">("detail");
  const services = config.data?.mode === "services";
  const preview = useCancelPreview(r?.id ?? null, step === "cancel" && services);

  // Done well, the sheet closes and the notice (with «Deshacer») shows over the day; refused, it says why here.
  const run = (action: ResAction, opts: { text?: string } = {}) => {
    if (!r) return;
    setError(null);
    setBusy(true);
    act(r, action, {
      ...opts,
      after: () => {
        setBusy(false);
        router.back();
      },
      onError: (text) => {
        setBusy(false);
        setError(text);
        void one.refetch();
      },
    });
  };

  const more = (action: MoreAction) => {
    if (!r) return;
    if (action === "move") {
      router.push({ pathname: "/reserva/nueva", params: { move: r.id, date: r.date } });
      return;
    }
    setError(null);
    setBusy(true);
    ask.mutate(r, {
      onSuccess: () => {
        setBusy(false);
        haptics.success();
        router.back();
        toast.show({ text: t("reservas.done.request_confirmation"), tone: "ok" });
      },
      onError: (e) => {
        setBusy(false);
        haptics.warning();
        setError(errorText(e, t));
        void one.refetch();
      },
    });
  };

  const chat = (conversation: string) => {
    // The sheet goes first, then the conversation opens over the tabs (design §5.3: 200 ms after).
    router.back();
    setTimeout(() => router.push(`/conversacion/${conversation}`), 200);
  };

  return (
    <ScrollView
      testID="reserva-sheet"
      style={glassAvailable() ? undefined : { backgroundColor: colors.background }}
      contentContainerStyle={styles.content}
      contentInsetAdjustmentBehavior="automatic"
    >
      {r && config.data && today && step === "cancel" ? (
        <CancelPanel
          r={r}
          mode={config.data.mode}
          preview={preview.data ?? null}
          previewLoading={services && preview.isPending && preview.fetchStatus !== "idle"}
          leadHours={config.data.waitlist.leadHours}
          today={today}
          onBack={() => setStep("detail")}
          onConfirm={(opts) => {
            const target = r;
            haptics.warning();
            const undo = deferCancel(target, opts, (e) => {
              haptics.warning();
              toast.show({ text: e instanceof ApiError && e.offline ? t("reservas.error.offline") : t("reservas.cancel.failed"), tone: "warn" });
            });
            router.back();
            toast.show({
              text: opts.offerSlot ? t("reservas.cancel.done.offer") : t("reservas.cancel.done.short"),
              tone: "ok",
              action: {
                label: t("reservas.action.undo"),
                onPress: () => {
                  if (!undo()) return toast.show({ text: t("reservas.undo.late"), tone: "warn" });
                  haptics.light();
                  toast.show({ text: t("reservas.cancel.undone"), tone: "info" });
                },
              },
            });
          }}
          t={t}
          locale={locale}
        />
      ) : r && config.data && today ? (
        <ReservaSheet
          r={r}
          config={config.data}
          today={today}
          online={online}
          busy={busy}
          error={error}
          onAct={(a) => run(a)}
          onMore={more}
          onCancel={() => {
            setError(null);
            setStep("cancel");
          }}
          onChat={hasInbox ? chat : undefined}
          t={t}
          locale={locale}
        />
      ) : one.error instanceof ApiError && one.error.status === 404 ? (
        <EmptyState icon={icons.calendar} title={t("reservas.sheet.notFound")} />
      ) : one.isError || config.isError ? (
        <ErrorState onRetry={() => void one.refetch()} />
      ) : (
        <View>
          <Skeleton rows={3} />
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: 20, paddingTop: 28, gap: 16 },
});
