import * as Crypto from "expo-crypto";
import { router, useLocalSearchParams } from "expo-router";
import { useRef, useState } from "react";
import { StyleSheet } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";

import { ApiError } from "@/api/errors";
import { useBizToday, useCreateReservation, useFreeSlots, useReservasConfig } from "@/api/reservas-hooks";
import { NewReservationForm, type SlotQuery } from "@/features/reservas/new-reservation";
import { errorText } from "@/features/reservas/screen";
import { relativeDay } from "@/features/reservas/format";
import { useLocale, useT } from "@/i18n/t";
import { hhmm } from "@/lib/reservas-model";
import { haptics } from "@/motion/haptics";
import { glassAvailable } from "@/theme/glass";
import { useTheme } from "@/theme/theme";
import { useOnline } from "@/ui/online";
import { ErrorState, Skeleton } from "@/ui/states";
import { useToast } from "@/ui/toast";

/**
 * «Nueva reserva», as a tall sheet (spec 044, Requisito 5, D5). One key per
 * attempt, so a double tap or a retry never books twice (R5.6); a slot taken
 * meanwhile keeps what was typed and asks for the slots again (R5.7).
 */
export default function NuevaRoute() {
  const { date } = useLocalSearchParams<{ date?: string }>();
  const t = useT();
  const locale = useLocale();
  const online = useOnline();
  const toast = useToast();
  const { colors } = useTheme();
  const config = useReservasConfig();
  const today = useBizToday(config.data);
  const [query, setQuery] = useState<SlotQuery | null>(null);
  const slots = useFreeSlots(query);
  const create = useCreateReservation();
  const key = useRef(Crypto.randomUUID());
  const [error, setError] = useState<string | null>(null);

  return (
    <KeyboardAwareScrollView
      style={glassAvailable() ? undefined : { backgroundColor: colors.background }}
      contentContainerStyle={styles.content}
      contentInsetAdjustmentBehavior="automatic"
      keyboardShouldPersistTaps="handled"
      bottomOffset={24}
      testID="nueva-sheet"
    >
      {config.data && today ? (
        <NewReservationForm
          config={config.data}
          today={today}
          initialDate={date || today}
          slots={slots.data ?? null}
          slotsLoading={slots.isFetching}
          slotsError={slots.isError}
          onRetrySlots={() => void slots.refetch()}
          onQuery={setQuery}
          saving={create.isPending}
          error={error}
          online={online}
          t={t}
          locale={locale}
          onSave={(body) => {
            setError(null);
            create.mutate(
              { body, key: key.current },
              {
                onSuccess: (r) => {
                  haptics.success();
                  const when = t("reservas.dayAt", { day: relativeDay(r.date, today, locale, t).toLocaleLowerCase(locale), time: hhmm(r.start) });
                  toast.show({ text: r.customer.phone ? t("reservas.new.saved.whatsapp", { when }) : t("reservas.new.saved", { when }) });
                  router.back();
                },
                onError: (e) => {
                  haptics.warning();
                  key.current = Crypto.randomUUID();
                  setError(errorText(e, t));
                  if (e instanceof ApiError && e.code === "slot_taken") void slots.refetch();
                },
              },
            );
          }}
        />
      ) : config.isError ? (
        <ErrorState onRetry={() => void config.refetch()} />
      ) : (
        <Skeleton rows={4} />
      )}
    </KeyboardAwareScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: 20, paddingTop: 28, paddingBottom: 48 },
});
