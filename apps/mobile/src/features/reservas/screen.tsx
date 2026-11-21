import { useQueryClient } from "@tanstack/react-query";
import { router, Stack, useLocalSearchParams } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { Platform, Pressable, RefreshControl, ScrollView, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ApiError } from "@/api/errors";
import { invalidateReservas } from "@/api/query";
import { demo, reservasSource } from "@/api/reservas";
import type { Reservation, ResAction } from "@/api/reservas";
import {
  useBizNow,
  useBizToday,
  useOccupancy,
  useReservaAction,
  useReservasConfig,
  useReservasRange,
  useWaitlist,
  useWithPendingCancels,
  useWithPendingRemovals,
} from "@/api/reservas-hooks";
import { useLocale, useT, type T } from "@/i18n/t";
import { clock } from "@/lib/format";
import { addDays, monthEnd, monthStart, weekStart, type LocalDate, type Minutes } from "@/lib/reservas-model";
import { usePullRefresh } from "@/lib/use-pull-refresh";
import { haptics } from "@/motion/haptics";
import { RADII, useTheme } from "@/theme/theme";
import { useActions } from "@/ui/actions";
import { IconButton } from "@/ui/button";
import { Fab } from "@/ui/fab";
import { Icon, icons } from "@/ui/icon";
import { Text } from "@/ui/text";
import { useOnline } from "@/ui/online";
import { useToast } from "@/ui/toast";
import { Skeleton } from "@/ui/states";

import { arrives, useArrivalSignal } from "./arrival";
import { WaitlistCard } from "./waitlist-card";
import { ReservasBody, showsOtherPeriod } from "./body";
import { DayCapacity } from "./day-capacity";
import { DayGrid } from "./day-grid";
import { DayServices } from "./day-services";
import { calendarNeedsAttention, calendarText, firstName } from "./format";
import { DayHeader, type DayView, type Period } from "./header";
import { MonthGrid } from "./month";
import { WeekHeat, WeekServices } from "./week";

/**
 * Reservas (spec 044, Historia 1; R1–R3, R5.1, R6.1, R16, R17; spec 069,
 * Requisito 13): the day by default — its week read at once, so the strip
 * marks the days with bookings —, the week and the month, in the one mode the
 * API says. A free band of the grid books that time (R13.3); an empty day
 * offers to book it; the waitlist is a card after the bookings; a calendar
 * that needs someone is said on the day. A booking just saved enters its day
 * (micro 3); one being cancelled shows cancelled while «Deshacer» lasts. The
 * way in from Inicio, a contact or a notice is the route itself:
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

  // A booking just saved or moved: Reservas goes to its day, and that one row arrives (micro 3).
  const arrival = useArrivalSignal();
  const [seen, setSeen] = useState(0);
  if (arrival && arrival.seq !== seen) {
    setSeen(arrival.seq);
    setPeriod("day");
    setPicked(arrival.date);
  }

  const mode = config.data?.mode;
  // The day reads its whole week: the strip marks the days with bookings, and moving within it is instant.
  const [from, to] =
    date === null ? [null, null] : period === "month" ? [monthStart(date), monthEnd(date)] : [weekStart(date), addDays(weekStart(date), 6)];
  const range = useReservasRange(from, to);
  const occupancy = useOccupancy(from, to, mode === "capacity" || period !== "day");
  const now = useBizNow(range.data?.now);
  const act = useActOn(t);
  const items = useWithPendingCancels(range.data?.items) ?? [];
  const waitlist = useWithPendingRemovals(useWaitlist(config.data?.waitlist.enabled ?? false).data) ?? [];
  const live = items.filter((r) => r.state !== "cancelled");
  const marks = new Set(live.map((r) => r.date));
  const counts: Record<LocalDate, number> = {};
  for (const r of live) counts[r.date] = (counts[r.date] ?? 0) + 1;
  const arrivedId = arrival && arrives(arrival, arrival.id) ? arrival.id : null;

  const open = (r: Reservation) => router.push({ pathname: "/reserva/[id]", params: { id: r.id, date: r.date } });
  const book = (d: LocalDate, time: Minutes | null = null, proId: string | null = null) =>
    router.push({ pathname: "/reserva/nueva", params: { date: d, ...(time !== null ? { time: String(time) } : {}), ...(proId ? { pro: proId } : {}) } });
  const attention = mode === "services" && period === "day" ? (config.data?.services?.team ?? []).filter(calendarNeedsAttention) : [];
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
          skeleton="day"
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
                marks={marks}
                t={t}
                locale={locale}
              />
              {attention.map((p) => (
                <CalendarNotice key={p.id} text={t("reservas.calendar.attention", { name: firstName(p.name), state: calendarText(p, t) })} t={t} />
              ))}
              {showsOtherPeriod(range, occupancy, mode === "capacity" || period !== "day") ? (
                <Skeleton rows={5} label={t("reservas.loading")} />
              ) : period === "day" && mode === "services" && view === "list" ? (
                <DayServices
                  config={config.data}
                  items={items}
                  now={now}
                  date={date}
                  pro={pro}
                  onPro={setPro}
                  onOpen={open}
                  onNew={online ? (d) => book(d) : undefined}
                  onDay={(d) => setPicked(d)}
                  arrivedId={arrivedId}
                  t={t}
                  locale={locale}
                />
              ) : period === "day" && mode === "services" ? (
                <DayGrid
                  config={config.data}
                  items={items}
                  now={now}
                  date={date}
                  pro={pro}
                  onPro={setPro}
                  onOpen={open}
                  onList={() => setView("list")}
                  onFree={online ? (d, time, p) => book(d, time, p) : undefined}
                  arrivedId={arrivedId}
                  t={t}
                  locale={locale}
                />
              ) : period === "day" ? (
                <DayCapacity
                  config={config.data}
                  items={items}
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
                <WeekServices config={config.data} items={items} days={occupancy.data?.days ?? []} from={weekStart(date)} today={today} onDay={goDay} t={t} locale={locale} />
              ) : period === "week" ? (
                <WeekHeat config={config.data} slots={occupancy.data?.slots ?? []} from={weekStart(date)} onCell={goDay} t={t} locale={locale} />
              ) : (
                <MonthGrid month={date} days={occupancy.data?.days ?? []} counts={counts} today={today} selected={date} onDay={(d) => goDay(d)} t={t} locale={locale} />
              )}
              {waitlist.length > 0 ? <WaitlistCard items={waitlist} onPress={() => router.push("/reservas/espera")} t={t} /> : null}
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

/** A professional's calendar that needs someone (spec 069, R13.7): said on the day, with the way to see it. */
function CalendarNotice({ text, t }: { text: string; t: T }) {
  const { colors } = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={text}
      accessibilityHint={t("reservas.calendar.attention.open")}
      onPress={() => router.push("/reservas/ajustes")}
      style={({ pressed }) => [styles.notice, { backgroundColor: pressed ? colors.muted : colors.warningBg, borderRadius: RADII.md }]}
    >
      <Icon name={icons.warning} size={18} tone="warningText" />
      <Text variant="footnote" tone="warningText" style={styles.flex}>
        {text}
      </Text>
      <Icon name={icons.chevron} size={16} tone="warningText" />
    </Pressable>
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
  const qc = useQueryClient();
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
              ? {
                  label: t("reservas.action.undo"),
                  // A plain promise: from a sheet, the mutation's caller is gone by the time «Deshacer» is tapped (spec 069).
                  onPress: () =>
                    void reservasSource()
                      .act(next, "undo")
                      .then(
                        () => toast.show({ text: t("reservas.done.undo") }),
                        (e: unknown) => toast.show({ text: errorText(e, t), tone: "warn" }),
                      )
                      .finally(() => invalidateReservas(qc)),
                }
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
  flex: { flex: 1, minWidth: 0 },
  notice: { flexDirection: "row", alignItems: "center", gap: 10, padding: 12 },
  fabs: { position: "absolute", right: 16, alignItems: "flex-end", gap: 16 },
});
