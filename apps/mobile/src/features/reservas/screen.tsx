import { router, Stack, useLocalSearchParams } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { Platform, RefreshControl, ScrollView, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ApiError } from "@/api/errors";
import { demo } from "@/api/reservas";
import type { Reservation, ResAction } from "@/api/reservas";
import { useBizNow, useBizToday, useOccupancy, useReservaAction, useReservasConfig, useReservasRange } from "@/api/reservas-hooks";
import { useLocale, useT, type T } from "@/i18n/t";
import { clock } from "@/lib/format";
import { addDays, monthEnd, monthStart, weekStart, type LocalDate } from "@/lib/reservas-model";
import { usePullRefresh } from "@/lib/use-pull-refresh";
import { haptics } from "@/motion/haptics";
import { useTheme } from "@/theme/theme";
import { useActions } from "@/ui/actions";
import { IconButton } from "@/ui/button";
import { Fab } from "@/ui/fab";
import { icons } from "@/ui/icon";
import { useOnline } from "@/ui/online";
import { useToast } from "@/ui/toast";
import { Skeleton } from "@/ui/states";

import { ReservasBody, showsOtherPeriod } from "./body";
import { DayCapacity } from "./day-capacity";
import { DayGrid } from "./day-grid";
import { DayServices } from "./day-services";
import { DayHeader, type DayView, type Period } from "./header";
import { MonthGrid } from "./month";
import { WeekHeat, WeekServices } from "./week";

/**
 * Reservas (spec 044, Historia 1; R1–R3, R5.1, R6.1, R16, R17): the day by
 * default, the week and the month, in the one mode the API says. The way in
 * from Inicio, a contact or a notice is the route itself:
 * `/reservas?date=…&open=<id>&slot=<HH*60+MM>`.
 */
export default function ReservasScreen() {
  const t = useT();
  const locale = useLocale();
  const online = useOnline();
  const params = useLocalSearchParams<{ date?: string; open?: string; slot?: string }>();
  const config = useReservasConfig();
  const today = useBizToday(config.data);
  const [period, setPeriod] = useState<Period>("day");
  const [picked, setPicked] = useState<LocalDate | null>(null);
  const [view, setView] = useState<DayView>("list");
  const [pro, setPro] = useState<string | null>(null);
  const [slot, setSlot] = useState<number | null>(null);
  const date = picked ?? today;

  // A link in (Inicio, the contact, a notice): that day — adjusted while rendering, as React
  // recommends for state that follows a prop — and that reservation's sheet once.
  const [link, setLink] = useState<{ date?: string; slot?: string }>({});
  if (params.date !== link.date || params.slot !== link.slot) {
    setLink({ date: params.date, slot: params.slot });
    if (params.date) {
      setPeriod("day");
      setPicked(params.date);
    }
    if (params.slot) setSlot(Number(params.slot));
  }
  const opened = useRef<string | null>(null);
  useEffect(() => {
    if (params.open && opened.current !== params.open) {
      opened.current = params.open;
      router.push({ pathname: "/reserva/[id]", params: { id: params.open } });
    }
  }, [params.open]);

  const mode = config.data?.mode;
  const [from, to] =
    date === null ? [null, null] : period === "day" ? [date, date] : period === "week" ? [weekStart(date), addDays(weekStart(date), 6)] : [monthStart(date), monthEnd(date)];
  const range = useReservasRange(from, to);
  const occupancy = useOccupancy(from, to, mode === "capacity" || period === "month");
  const now = useBizNow(range.data?.now);
  const act = useActOn(t);

  const open = (r: Reservation) => router.push({ pathname: "/reserva/[id]", params: { id: r.id, date: r.date } });
  const goDay = (d: LocalDate, s: number | null = null) => {
    setPicked(d);
    setPeriod("day");
    setSlot(s);
  };
  const capacityToday = mode === "capacity" && period === "day" && date === today;

  const state: "loading" | "error" | "ready" =
    config.isError || (range.isError && !range.data) ? "error" : config.data && range.data && now && today && date ? "ready" : "loading";
  const offlineSince = !online && range.data ? clock(new Date(range.dataUpdatedAt), locale) : null;

  const pull = usePullRefresh(() => Promise.all([config.refetch(), range.refetch(), occupancy.refetch()]));

  return (
    <View style={styles.fill}>
      <Stack.Screen options={{ title: t("reservas.title") }} />
      <ReservasBar capacity={mode === "capacity"} onNew={() => router.push({ pathname: "/reserva/nueva", params: { date: date ?? "" } })} t={t} />
      <ScrollViewWithRefresh
        refreshing={pull.refreshing}
        onRefresh={pull.onRefresh}
      >
        <ReservasBody
          state={state}
          offline={!online}
          demo={demo !== null}
          offlineSince={offlineSince}
          partial={occupancy.isError && !occupancy.data}
          onRetry={() => {
            void config.refetch();
            void range.refetch();
          }}
          t={t}
        >
          {state === "ready" && config.data && range.data && now && today && date ? (
            <View style={styles.stack}>
              <DayHeader
                period={period}
                onPeriod={(p) => {
                  setPeriod(p);
                  setSlot(null);
                }}
                date={date}
                today={today}
                onDate={(d) => {
                  setPicked(d);
                  setSlot(null);
                }}
                config={config.data}
                view={view}
                onView={setView}
                t={t}
                locale={locale}
              />
              {showsOtherPeriod(range, occupancy, mode === "capacity" || period === "month") ? (
                <Skeleton rows={5} label={t("reservas.loading")} />
              ) : period === "day" && mode === "services" && view === "list" ? (
                <DayServices config={config.data} items={range.data.items} now={now} date={date} pro={pro} onPro={setPro} onOpen={open} t={t} locale={locale} />
              ) : period === "day" && mode === "services" ? (
                <DayGrid config={config.data} items={range.data.items} now={now} date={date} onOpen={open} onList={() => setView("list")} t={t} locale={locale} />
              ) : period === "day" ? (
                <DayCapacity
                  config={config.data}
                  items={range.data.items}
                  slots={occupancy.data?.slots ?? []}
                  now={now}
                  date={date}
                  slot={slot}
                  onSlot={setSlot}
                  onOpen={open}
                  onAct={act}
                  online={online}
                  t={t}
                  locale={locale}
                />
              ) : period === "week" && mode === "services" ? (
                <WeekServices config={config.data} items={range.data.items} from={weekStart(date)} onOpen={open} onDay={goDay} t={t} locale={locale} />
              ) : period === "week" ? (
                <WeekHeat config={config.data} slots={occupancy.data?.slots ?? []} from={weekStart(date)} onCell={goDay} t={t} locale={locale} />
              ) : (
                <MonthGrid month={date} days={occupancy.data?.days ?? []} today={today} onDay={(d) => goDay(d)} t={t} locale={locale} />
              )}
              {/* Room for the floating buttons over the last rows. */}
              <View style={{ height: Platform.OS === "android" ? 96 : capacityToday ? 72 : 0 }} />
            </View>
          ) : null}
        </ReservasBody>
      </ScrollViewWithRefresh>
      <Floating
        capacityToday={capacityToday && online}
        online={online}
        onNew={() => router.push({ pathname: "/reserva/nueva", params: { date: date ?? "" } })}
        onWalkIn={() => router.push("/reserva/llegada")}
        t={t}
      />
    </View>
  );
}

function ScrollViewWithRefresh({ refreshing, onRefresh, children }: { refreshing: boolean; onRefresh: () => void; children: React.ReactNode }) {
  const { colors } = useTheme();
  return (
    <ScrollView
      testID="reservas"
      style={{ backgroundColor: colors.background }}
      contentInsetAdjustmentBehavior="automatic"
      contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primaryText} colors={[colors.primaryDeep]} />}
    >
      {children}
    </ScrollView>
  );
}

/**
 * The bar of Reservas (research D6): on iOS the system's bar buttons — «Nueva
 * reserva» with a calendar and a plus (never a bare «+», which is the walk-in's),
 * the «⋯» menu and Ajustes; on Android «⋯» and Ajustes in the header, and the
 * floating buttons below.
 */
function ReservasBar({ capacity, onNew, t }: { capacity: boolean; onNew: () => void; t: T }) {
  const { colors } = useTheme();
  const actions = useActions();
  const items = [
    ...(capacity ? [{ label: t("reservas.menu.walkin"), icon: icons.walkIn, onPress: () => router.push("/reserva/llegada") }] : []),
    { label: t("reservas.menu.waitlist"), icon: icons.waitlist, onPress: () => router.push("/reservas/espera") },
    { label: t("reservas.menu.settings"), icon: icons.sliders, onPress: () => router.push("/reservas/ajustes") },
    ...(capacity ? [{ label: t("reservas.menu.block"), icon: icons.block, onPress: () => router.push("/reserva/bloquear") }] : []),
  ];
  if (Platform.OS === "ios") {
    return (
      <Stack.Toolbar placement="right">
        <Stack.Toolbar.Button icon={icons.calendarAdd.ios} tintColor={colors.primaryText} accessibilityLabel={t("reservas.new")} onPress={onNew} />
        <Stack.Toolbar.Menu icon={icons.more.ios} tintColor={colors.primaryText} accessibilityLabel={t("reservas.menu")}>
          {items.map((a) => (
            <Stack.Toolbar.MenuAction key={a.label} icon={a.icon.ios} onPress={a.onPress}>
              {a.label}
            </Stack.Toolbar.MenuAction>
          ))}
        </Stack.Toolbar.Menu>
        <Stack.Toolbar.Button icon={icons.settings.ios} tintColor={colors.primaryText} accessibilityLabel={t("app.settings.open")} onPress={() => router.push("/ajustes")} />
      </Stack.Toolbar>
    );
  }
  return (
    <Stack.Screen
      options={{
        headerRight: () => (
          <View style={styles.headerRight}>
            <IconButton icon={icons.more} label={t("reservas.menu")} onPress={() => actions(undefined, items.map(({ label, onPress }) => ({ label, onPress })))} />
            <IconButton icon={icons.settings} label={t("app.settings.open")} onPress={() => router.push("/ajustes")} />
          </View>
        ),
      }}
    />
  );
}

/** The floating buttons (R5.1, R6.1, research D6). */
function Floating({ capacityToday, online, onNew, onWalkIn, t }: { capacityToday: boolean; online: boolean; onNew: () => void; onWalkIn: () => void; t: T }) {
  const insets = useSafeAreaInsets();
  if (Platform.OS === "ios") {
    if (!capacityToday) return null;
    return (
      // Inside a native tab the bottom inset already counts the bar: 16 pt above it (first iOS pass).
      <View pointerEvents="box-none" style={[styles.fabs, { bottom: insets.bottom + 16 }]}>
        <Fab icon={icons.plus} label={t("reservas.walkin.title")} onPress={onWalkIn} testID="fab-walkin" />
      </View>
    );
  }
  if (!online) return null;
  return (
    <View pointerEvents="box-none" style={[styles.fabs, { bottom: 16 }]}>
      {capacityToday ? <Fab icon={icons.plus} label={t("reservas.walkin.title")} small onPress={onWalkIn} testID="fab-walkin" /> : null}
      <Fab icon={icons.calendarAdd} label={t("reservas.new")} extended onPress={onNew} testID="fab-new" />
    </View>
  );
}

/** «Llegó», «No vino» and «Marcar confirmada» from a row or the sheet, with the brief notice and «Deshacer» (R4.4, R16.7). */
export function useActOn(t: T) {
  const toast = useToast();
  const mutation = useReservaAction();
  const said: Record<ResAction, Parameters<T>[0]> = {
    confirm: "reservas.done.confirm",
    arrived: "reservas.done.arrived",
    noshow: "reservas.done.noshow",
    undo: "reservas.done.undo",
    cancel: "reservas.done.cancel",
  };
  // `onError`: where the screen says a refusal itself. A sheet passes it — the notice lives at the
  // root and would sit under an iOS sheet (gate review); a row of the day leaves it to the notice.
  return (r: Reservation, action: ResAction, opts: { after?: () => void; text?: string; onError?: (text: string) => void } = {}) =>
    mutation.mutate(
      { r, action },
      {
        onSuccess: (next) => {
          haptics.success();
          opts.after?.();
          const undoable = (action === "arrived" || action === "noshow") && next.actions.includes("undo");
          toast.show({
            text: opts.text ?? t(said[action]),
            action: undoable
              ? { label: t("reservas.action.undo"), onPress: () => mutation.mutate({ r: next, action: "undo" }, { onSuccess: () => toast.show({ text: t("reservas.done.undo") }) }) }
              : undefined,
          });
        },
        onError: (e) => {
          haptics.warning();
          if (opts.onError) opts.onError(errorText(e, t));
          else toast.show({ text: errorText(e, t) });
        },
      },
    );
}

export function errorText(e: unknown, t: T): string {
  if (e instanceof ApiError && e.offline) return t("reservas.error.offline");
  if (e instanceof ApiError && (e.code === "stale" || e.code === "invalid_transition")) return t("reservas.error.stale");
  if (e instanceof ApiError && e.code === "slot_taken") return t("reservas.new.taken");
  if (e instanceof ApiError && e.code === "closed") return t("reservas.new.closed");
  return t("reservas.error.generic");
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { padding: 16, gap: 16, paddingBottom: 32 },
  stack: { gap: 16 },
  headerRight: { flexDirection: "row", alignItems: "center" },
  fabs: { position: "absolute", right: 16, alignItems: "flex-end", gap: 16 },
});
