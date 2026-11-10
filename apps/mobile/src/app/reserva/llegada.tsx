import * as Crypto from "expo-crypto";
import { router } from "expo-router";
import { useRef, useState } from "react";
import { StyleSheet } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";

import { ApiError } from "@/api/errors";
import {
  useBizNow,
  useBizToday,
  useJoinWaitlist,
  useOccupancy,
  useReservasConfig,
  useReservasRange,
  useWalkIn,
} from "@/api/reservas-hooks";
import { errorText } from "@/features/reservas/screen";
import { WalkIn } from "@/features/reservas/walk-in";
import { useT } from "@/i18n/t";
import { currentSlot } from "@/lib/reservas-model";
import { haptics } from "@/motion/haptics";
import { glassAvailable } from "@/theme/glass";
import { useTheme } from "@/theme/theme";
import { useOnline } from "@/ui/online";
import { ErrorState, Skeleton } from "@/ui/states";
import { useToast } from "@/ui/toast";

/**
 * «Llegada sin reserva», as a sheet over Reservas (spec 044, Requisito 6, D5):
 * it reads today's slots (who is inside) and the server's «now», and records
 * the arrival in the slot under way — or puts them on the waitlist.
 */
export default function LlegadaRoute() {
  const t = useT();
  const online = useOnline();
  const toast = useToast();
  const { colors } = useTheme();
  const config = useReservasConfig();
  const today = useBizToday(config.data);
  const range = useReservasRange(today, today);
  const occupancy = useOccupancy(today, today);
  const now = useBizNow(range.data?.now);
  const walkIn = useWalkIn();
  const join = useJoinWaitlist();
  const key = useRef(Crypto.randomUUID());
  const unit = config.data?.capacity?.unit ?? "";
  // A refusal is said in the sheet: the notice lives at the root, under an iOS sheet (gate review).
  const [error, setError] = useState<string | null>(null);

  return (
    <KeyboardAwareScrollView
      style={glassAvailable() ? undefined : { backgroundColor: colors.background }}
      contentContainerStyle={styles.content}
      contentInsetAdjustmentBehavior="automatic"
      keyboardShouldPersistTaps="handled"
      bottomOffset={24}
      testID="llegada-sheet"
    >
      {config.data && now && occupancy.data ? (
        <WalkIn
          config={config.data}
          slots={occupancy.data.slots}
          now={now}
          online={online}
          busy={walkIn.isPending || join.isPending}
          error={error}
          t={t}
          onRegister={(party, name) => {
            setError(null);
            walkIn.mutate(
              { partySize: party, name, key: key.current },
              {
                onSuccess: () => {
                  haptics.success();
                  toast.show({ text: t("reservas.walkin.done", { n: party, unit }) });
                  router.back();
                },
                onError: (e) => {
                  haptics.warning();
                  key.current = Crypto.randomUUID();
                  setError(e instanceof ApiError && e.code === "no_room" ? t("reservas.walkin.full") : e instanceof ApiError && e.code === "closed" ? t("reservas.walkin.closed") : errorText(e, t));
                  void occupancy.refetch();
                },
              },
            );
          }}
          onWait={(party, name) => {
            setError(null);
            join.mutate(
              { partySize: party, name, date: now.date, time: config.data ? currentSlot(config.data, now.date, now.minutes) : null, key: Crypto.randomUUID() },
              {
                onSuccess: () => {
                  haptics.success();
                  toast.show({ text: t("reservas.walkin.waited") });
                  router.back();
                },
                onError: (e) => {
                  haptics.warning();
                  setError(errorText(e, t));
                },
              },
            );
          }}
        />
      ) : config.isError || range.isError || occupancy.isError ? (
        <ErrorState
          onRetry={() => {
            void config.refetch();
            void range.refetch();
            void occupancy.refetch();
          }}
        />
      ) : (
        <Skeleton rows={3} />
      )}
    </KeyboardAwareScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: 20, paddingTop: 28, paddingBottom: 48 },
});
