import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Alert, ScrollView, StyleSheet, View } from "react-native";

import { ApiError } from "@/api/errors";
import type { ResAction } from "@/api/reservas";
import { useBizToday, useReservasConfig, useReservation } from "@/api/reservas-hooks";
import { cancelCopy, ReservaSheet } from "@/features/reservas/sheet";
import { useActOn } from "@/features/reservas/screen";
import { useLocale, useT } from "@/i18n/t";
import { glassAvailable } from "@/theme/glass";
import { useTheme } from "@/theme/theme";
import { icons } from "@/ui/icon";
import { useOnline } from "@/ui/online";
import { EmptyState, ErrorState, Skeleton } from "@/ui/states";

/**
 * One reservation, as a sheet over Reservas (spec 044, Requisito 4, D5): the
 * detail read, with its history, by id — a notice or a link brings nothing
 * else — and every action through the API with its version; cancelling asks
 * first (clarification 2).
 */
export default function ReservaRoute() {
  const { id } = useLocalSearchParams<{ id: string; date?: string }>();
  const t = useT();
  const locale = useLocale();
  const online = useOnline();
  const { colors } = useTheme();
  const config = useReservasConfig();
  const today = useBizToday(config.data);
  // The detail read: the reservation and its history (043 §4). A notice or a link brings only the id.
  const one = useReservation(id ?? null);
  const act = useActOn(t);
  const r = one.data ?? null;
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
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

  const cancel = () => {
    if (!r) return;
    const copy = cancelCopy(r, t);
    Alert.alert(copy.title, copy.body, [
      { text: t("reservas.cancel.keep"), style: "cancel" },
      {
        text: t("reservas.action.cancel"),
        style: "destructive",
        onPress: () => run("cancel", { text: config.data?.waitlist.enabled ? t("reservas.done.cancel.waitlist") : t("reservas.done.cancel") }),
      },
    ]);
  };

  return (
    <ScrollView
      testID="reserva-sheet"
      style={glassAvailable() ? undefined : { backgroundColor: colors.background }}
      contentContainerStyle={styles.content}
      contentInsetAdjustmentBehavior="automatic"
    >
      {r && config.data && today ? (
        <ReservaSheet r={r} config={config.data} today={today} online={online} busy={busy} error={error} onAct={(a) => run(a)} onCancel={cancel} t={t} locale={locale} />
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
