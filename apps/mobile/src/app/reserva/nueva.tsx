import * as Crypto from "expo-crypto";
import { Stack, useLocalSearchParams } from "expo-router";
import { useRef, useState } from "react";
import { StyleSheet } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";

import { ApiError } from "@/api/errors";
import {
  useBizNow,
  useBizToday,
  useCreateReservation,
  useFreeSlots,
  useMoveReservation,
  useReservasConfig,
  useReservasRange,
  useReservation,
  useUndoCreate,
} from "@/api/reservas-hooks";
import { announceArrival } from "@/features/reservas/arrival";
import { useDiscardGuard } from "@/features/reservas/discard-guard";
import { relativeDay } from "@/features/reservas/format";
import { MoveForm } from "@/features/reservas/move-reservation";
import { NewReservationForm, type NewPrefill, type SlotQuery } from "@/features/reservas/new-reservation";
import { errorText } from "@/features/reservas/screen";
import { useLocale, useT, type Locale, type T } from "@/i18n/t";
import { addDays, hhmm, wallClock, weekStart, type LocalDate } from "@/lib/reservas-model";
import { haptics } from "@/motion/haptics";
import { glassAvailable } from "@/theme/glass";
import { useTheme } from "@/theme/theme";
import { useOnline } from "@/ui/online";
import { ErrorState, Skeleton } from "@/ui/states";
import { useToast } from "@/ui/toast";

type Params = {
  date?: string;
  /** A free slot of the grid (spec 069, R13.3): minutes since midnight. */
  time?: string;
  pro?: string;
  service?: string;
  /** Someone of the waitlist (R16.3). */
  name?: string;
  phone?: string;
  party?: string;
  /** Moving that reservation instead of making one (R14.3). */
  move?: string;
};

/**
 * «Nueva reserva», as a tall sheet (spec 044, Requisito 5, D5; spec 069,
 * Requisito 15) — and «Mover la reserva» with `move=<id>` (R14.3). One key per
 * attempt, so a double tap or a retry never books twice (R5.6); a slot taken
 * meanwhile keeps what was typed and asks for the slots again (R5.7). With
 * something written, closing asks first (R15.3): the X, the swipe and
 * Android's back. Saved, the sheet closes, the booking enters its day (micro
 * 3) and the notice offers «Deshacer» (R15.4).
 */
export default function NuevaRoute() {
  const params = useLocalSearchParams<Params>();
  const t = useT();
  const locale = useLocale();
  const online = useOnline();
  const toast = useToast();
  const { colors } = useTheme();
  const config = useReservasConfig();
  const today = useBizToday(config.data);
  // The business's «now», from the same read as the week on screen (it is cached there).
  const range = useReservasRange(today ? weekStart(today) : null, today ? addDays(weekStart(today), 6) : null);
  // Until that read answers, the business's wall clock: the notice must cut from the first frame.
  const bizNow = useBizNow(range.data?.now);
  const now = bizNow ?? (config.data ? wallClock(config.data.timezone) : null);
  const moving = useReservation(params.move ?? null);
  const [query, setQuery] = useState<SlotQuery | null>(null);
  const slots = useFreeSlots(query);
  const create = useCreateReservation();
  const move = useMoveReservation();
  const undoCreate = useUndoCreate();
  const key = useRef(Crypto.randomUUID());
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  // «¿Salir sin guardar?» from the «X», Android's back and the sheet's swipe (R15.3).
  const guard = useDiscardGuard(dirty, t);
  const { close, leave } = guard;

  const prefill: NewPrefill = {
    ...(params.time && Number.isFinite(Number(params.time)) ? { time: Number(params.time) } : {}),
    ...(params.pro ? { proId: params.pro } : {}),
    ...(params.service ? { serviceId: params.service } : {}),
    ...(params.name ? { name: params.name } : {}),
    ...(params.phone ? { phone: params.phone } : {}),
    ...(params.party && Number.isFinite(Number(params.party)) ? { partySize: Number(params.party) } : {}),
  };
  const initialDate = params.date || today || "";
  const whenOf = (date: LocalDate, start: number, tday: LocalDate, l: Locale, tt: T) =>
    tt("reservas.dayAt", { day: relativeDay(date, tday, l, tt).toLocaleLowerCase(l), time: hhmm(start) });

  return (
    <KeyboardAwareScrollView
      style={glassAvailable() ? undefined : { backgroundColor: colors.background }}
      contentContainerStyle={styles.content}
      contentInsetAdjustmentBehavior="automatic"
      keyboardShouldPersistTaps="handled"
      bottomOffset={24}
      testID="nueva-sheet"
    >
      {/* With something written, the swipe down does not close it silently (R15.3). */}
      <Stack.Screen options={{ gestureEnabled: !dirty || guard.leaving }} />
      {params.move ? (
        moving.data && config.data && today ? (
          <MoveForm
            r={moving.data}
            config={config.data}
            today={today}
            now={now}
            slots={slots.data ?? null}
            slotsLoading={slots.isFetching}
            slotsError={slots.isError}
            onRetrySlots={() => void slots.refetch()}
            onQuery={setQuery}
            saving={move.isPending}
            error={error}
            online={online}
            onClose={leave}
            t={t}
            locale={locale}
            onSave={(body) => {
              setError(null);
              move.mutate(
                { r: moving.data!, body },
                {
                  onSuccess: (r) => {
                    haptics.success();
                    announceArrival(r.id, r.date);
                    // Both sheets go: the reservation's is out of date now.
                    guard.leaveBoth();
                    toast.show({ text: t("reservas.move.done", { when: whenOf(r.date, r.start, today, locale, t) }), tone: "ok" });
                  },
                  onError: (e) => {
                    haptics.warning();
                    setError(errorText(e, t));
                    if (e instanceof ApiError && e.code === "slot_taken") void slots.refetch();
                  },
                },
              );
            }}
          />
        ) : moving.isError || config.isError ? (
          <ErrorState onRetry={() => void moving.refetch()} />
        ) : (
          <Skeleton rows={4} />
        )
      ) : config.data && today ? (
        <NewReservationForm
          config={config.data}
          today={today}
          initialDate={initialDate}
          initial={prefill}
          now={now}
          slots={slots.data ?? null}
          slotsLoading={slots.isFetching}
          slotsError={slots.isError}
          onRetrySlots={() => void slots.refetch()}
          onQuery={setQuery}
          onDirty={setDirty}
          onClose={close}
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
                  announceArrival(r.id, r.date);
                  leave();
                  toast.show({
                    text: t("reservas.form.saved", { when: whenOf(r.date, r.start, today, locale, t) }),
                    tone: "ok",
                    // No inverse in the API: «Deshacer» cancels it, telling the customer if they were told (R15.4).
                    action: {
                      label: t("reservas.action.undo"),
                      onPress: () =>
                        void undoCreate(r).then(
                          () => {
                            haptics.light();
                            toast.show({ text: t("reservas.form.saved.undone"), tone: "info" });
                          },
                          (e: unknown) => toast.show({ text: errorText(e, t), tone: "warn" }),
                        ),
                    },
                  });
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
