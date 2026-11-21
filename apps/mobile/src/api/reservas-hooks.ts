import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";
import { AppState } from "react-native";

import { sinceMinutes, wallClock, type BizNow, type LocalDate, type WallTime } from "@/lib/reservas-model";
import { useNowMs } from "@/lib/use-now";
import { TOAST_UNDO_MS, undoMs } from "@/ui/toast";

import { useForbiddenRereadsMe, useMe } from "./hooks";
import { invalidateReservas, keys } from "./query";
import {
  reservasSource,
  type CancelOptions,
  type ConfigPatch,
  type JoinWaitlist,
  type MoveRequest,
  type NewReservation,
  type ResAction,
  type ResConfig,
  type Reservation,
  type WaitEntry,
} from "./reservas";

/**
 * Reservas' reads and writes on the phone (spec 044, R1, R17). Memory only,
 * like the rest (031): nothing about the business's customers goes to disk.
 * Every write re-reads what it changes — the day, Inicio, the contact — and a
 * 403 means the module went away: `/me` is re-read and the tab follows.
 */

/** Whether this client has Reservas at all (R1.1, R1.2). */
export function useHasReservas(): boolean {
  return useMe().data?.nav.includes("reservas") ?? false;
}

export function useReservasConfig(enabled = true) {
  const q = useQuery({ queryKey: keys.reservasConfig, queryFn: () => reservasSource().config(), enabled, staleTime: 60_000 });
  useForbiddenRereadsMe(q.error);
  return q;
}

export function useReservasRange(from: LocalDate | null, to: LocalDate | null) {
  const q = useQuery({
    queryKey: keys.reservasRange(from ?? "", to ?? ""),
    queryFn: () => reservasSource().range(from!, to!),
    enabled: from !== null && to !== null,
    placeholderData: (prev) => prev,
  });
  useForbiddenRereadsMe(q.error);
  return q;
}

export function useOccupancy(from: LocalDate | null, to: LocalDate | null, enabled = true) {
  const q = useQuery({
    queryKey: keys.reservasOccupancy(from ?? "", to ?? ""),
    queryFn: () => reservasSource().occupancy(from!, to!),
    enabled: enabled && from !== null && to !== null,
    placeholderData: (prev) => prev,
  });
  useForbiddenRereadsMe(q.error);
  return q;
}

export function useFreeSlots(p: { date: LocalDate; serviceId?: string; proId?: string | null; partySize?: number; exclude?: string } | null) {
  return useQuery({
    // `exclude` (a reservation being moved) is its own read: its time counts as free there.
    queryKey: [...keys.reservasSlots(p?.date ?? "", p?.serviceId ?? null, p?.proId ?? null, p?.partySize ?? null), p?.exclude ?? null],
    queryFn: () => reservasSource().freeSlots(p!),
    enabled: p !== null,
    staleTime: 0,
  });
}

export function useWaitlist(enabled = true) {
  const q = useQuery({ queryKey: keys.reservasWaitlist, queryFn: () => reservasSource().waitlist(), enabled });
  useForbiddenRereadsMe(q.error);
  return q;
}

/*
 * The phone's clock is state here, and the time is passed in: React Compiler
 * memoises on what a computation reads, so a `useMemo` with a tick it never
 * reads froze «Ahora» at the minute of the read (first iOS pass, H-R6).
 */

/** The business's today, from its own zone (research D3); moves on at midnight there. */
export function useBizToday(config: ResConfig | undefined): LocalDate | null {
  const at = useNowMs();
  return config ? wallClock(config.timezone, new Date(at)).date : null;
}

/** «Now» in the business, from the server's last word, moving with the phone's clock. */
export function useBizNow(now: BizNow | undefined): WallTime | null {
  const at = useNowMs();
  return now ? sinceMinutes(now, at) : null;
}

// ── writes ────────────────────────────────────────────────────────────

function useInvalidating<V, R>(fn: (v: V) => Promise<R>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSettled: () => invalidateReservas(qc) });
}

export function useReservaAction() {
  return useInvalidating(({ r, action }: { r: Pick<Reservation, "id" | "version">; action: ResAction }) => reservasSource().act(r, action));
}

export function useCreateReservation() {
  return useInvalidating(({ body, key }: { body: NewReservation; key: string }) => reservasSource().create(body, key));
}

export function useWalkIn() {
  return useInvalidating(({ partySize, name, key }: { partySize: number; name: string | null; key: string }) =>
    reservasSource().walkIn({ partySize, name }, key),
  );
}

export function useJoinWaitlist() {
  return useInvalidating(({ key, ...b }: JoinWaitlist & { key: string }) => reservasSource().joinWaitlist(b, key));
}

export function useWaitlistOffer() {
  return useInvalidating((id: string) => reservasSource().offer(id));
}

export function useWaitlistRemove() {
  return useInvalidating((id: string) => reservasSource().removeWait(id));
}

export function usePatchReservasConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ patch, version }: { patch: ConfigPatch; version: number }) => reservasSource().patchConfig(patch, version),
    onSuccess: (config) => qc.setQueryData(keys.reservasConfig, config),
    onSettled: () => invalidateReservas(qc),
  });
}

export function useBlock() {
  return useInvalidating(({ key, ...b }: { date: LocalDate; from: number; until: number; reason: string; key: string }) => reservasSource().block(b, key));
}

/** One reservation with its history (043 §4): the sheet's read. */
export function useReservation(id: string | null) {
  const q = useQuery({ queryKey: [...keys.reservas, "booking", id ?? ""], queryFn: () => reservasSource().booking(id!), enabled: id !== null });
  useForbiddenRereadsMe(q.error);
  return q;
}

export function useUnblock() {
  return useInvalidating((id: string) => reservasSource().unblock(id));
}

// ── spec 069: what the web already did ────────────────────────────────

/** Whether the client also has the Bandeja: «Abrir el chat» only then (constitution §V). */
export function useHasInbox(): boolean {
  return useMe().data?.nav.includes("inbox") ?? false;
}

/** Whether a cancellation's slot can go to the waitlist (Servicios; spec 069 R14.2). */
export function useCancelPreview(id: string | null, enabled: boolean) {
  return useQuery({
    queryKey: [...keys.reservas, "cancel-preview", id ?? ""],
    queryFn: () => reservasSource().cancelPreview(id!),
    enabled: enabled && id !== null,
    staleTime: 0,
    retry: false,
  });
}

/** The slots being offered to the waitlist now (spec 069 R16.2). */
export function useOffers(enabled = true) {
  const q = useQuery({ queryKey: [...keys.reservas, "offers"], queryFn: () => reservasSource().offers(), enabled });
  useForbiddenRereadsMe(q.error);
  return q;
}

export function useStopOffer() {
  return useInvalidating((id: string) => reservasSource().stopOffer(id));
}

export function useMoveReservation() {
  return useInvalidating(({ r, body }: { r: Pick<Reservation, "id" | "version">; body: MoveRequest }) => reservasSource().move(r, body));
}

export function useRequestConfirmation() {
  return useInvalidating((r: Pick<Reservation, "id" | "version">) => reservasSource().requestConfirmation(r));
}

// ── writes that wait for «Deshacer» (spec 069, micro 6) ───────────────

/**
 * Cancelling a reservation and taking someone off the waitlist have no
 * inverse in the API, and a cancellation tells the customer on WhatsApp: a
 * message cannot be unsent. So «Deshacer» is honest only if nothing went out
 * yet — the write waits while the notice offers it (`undoMs()`, the toast's own
 * time, longer with a screen reader) and the screens show it done meanwhile. «Deshacer» drops it; at the
 * end it goes to the API, and a refusal is said and the truth re-read.
 * Module state on purpose: the write outlives the sheet that started it.
 */
/** The usual wait, without a screen reader (tests). */
export const UNDO_MS = TOAST_UNDO_MS;

type Pending = { timer: ReturnType<typeof setTimeout>; commit: () => void };
const cancels = new Map<string, Pending>();
const removals = new Map<string, Pending>();

/**
 * What the screens read: an immutable snapshot, a new one per change, so a
 * memoised render (React Compiler) sees the change in what it reads.
 */
type Snapshot = { cancels: ReadonlySet<string>; removals: ReadonlySet<string> };
let snapshot: Snapshot = { cancels: new Set(), removals: new Set() };
const listeners = new Set<() => void>();
const emit = () => {
  snapshot = { cancels: new Set(cancels.keys()), removals: new Set(removals.keys()) };
  for (const l of listeners) l();
};
const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
};

function usePending(): Snapshot {
  return useSyncExternalStore(subscribe, () => snapshot, () => snapshot);
}

/** A day's reservations with those being cancelled shown cancelled (and nothing left to do with them). */
export function useWithPendingCancels(items: Reservation[] | undefined): Reservation[] | undefined {
  return withCancels(items, usePending().cancels);
}

function withCancels(items: Reservation[] | undefined, pending: ReadonlySet<string>): Reservation[] | undefined {
  if (!items || pending.size === 0) return items;
  return items.map((r) => (pending.has(r.id) ? { ...r, state: "cancelled", actions: [], moreActions: [] } : r));
}

/** The waitlist without those being taken off it. */
export function useWithPendingRemovals(items: WaitEntry[] | undefined): WaitEntry[] | undefined {
  const pending = usePending().removals;
  if (!items || pending.size === 0) return items;
  return items.filter((w) => !pending.has(w.id));
}

/**
 * Leaving the app sends what was waiting: a write the person was told went
 * through is not lost because the phone locked or the app was closed in the
 * window (iOS goes «inactive» on the way to the switcher, before it may be
 * killed). «Deshacer» after that says it is too late.
 */
let watching = false;
function watchAppState() {
  if (watching) return;
  watching = true;
  AppState.addEventListener("change", (state) => {
    if (state === "background" || state === "inactive") flushPendingWrites();
  });
}

export function flushPendingWrites(): void {
  for (const map of [cancels, removals]) {
    for (const p of [...map.values()]) {
      clearTimeout(p.timer);
      p.commit();
    }
  }
}

/** Returns the undo: `true` when it dropped the write, `false` when it had gone out already. */
function defer(map: Map<string, Pending>, id: string, qc: QueryClient, send: () => Promise<unknown>, onFail: (e: unknown) => void): () => boolean {
  watchAppState();
  const prev = map.get(id);
  if (prev) clearTimeout(prev.timer);
  let sent = false;
  const done = () => {
    if (map.get(id)?.commit === commit) map.delete(id);
    emit();
  };
  const commit = () => {
    if (sent) return;
    sent = true;
    void send().then(
      // Done: it stays shown as done until the re-read brings the truth, so it never flickers back.
      () =>
        qc
          .invalidateQueries({ queryKey: keys.reservas })
          .catch(() => undefined)
          .finally(done),
      // Refused: back as it was at once, said, and re-read.
      (e: unknown) => {
        onFail(e);
        done();
        invalidateReservas(qc);
      },
    );
  };
  // The notice's own time, longer with a screen reader: «Deshacer» never outlives the wait.
  map.set(id, { timer: setTimeout(commit, undoMs()), commit });
  emit();
  return () => {
    const p = map.get(id);
    if (!p || p.commit !== commit || sent) return false;
    clearTimeout(p.timer);
    map.delete(id);
    emit();
    return true;
  };
}

/** Cancel after the notice's «Deshacer»; returns the undo. */
export function useDeferredCancel() {
  const qc = useQueryClient();
  return (r: Pick<Reservation, "id" | "version">, opts: CancelOptions, onFail: (e: unknown) => void) =>
    defer(cancels, r.id, qc, () => reservasSource().cancel(r, opts), onFail);
}

/** Take someone off the waitlist after the notice's «Deshacer»; returns the undo. */
export function useDeferredRemoveWait() {
  const qc = useQueryClient();
  return (id: string, onFail: (e: unknown) => void) => defer(removals, id, qc, () => reservasSource().removeWait(id), onFail);
}

/**
 * «Deshacer» of a booking just saved (R15.4): there is no inverse, so it is
 * cancelled — telling the customer when they were told it was made. A plain
 * promise, not a mutation's callbacks: the form that saved it is gone by the
 * time the notice is tapped, and a mutation would not call back then.
 */
export function useUndoCreate() {
  const qc = useQueryClient();
  return (r: Pick<Reservation, "id" | "version" | "customer">): Promise<void> =>
    reservasSource()
      .cancel(r, { notify: !!r.customer.phone, offerSlot: false })
      .then(() => undefined)
      .finally(() => invalidateReservas(qc));
}

/** For tests: nothing waiting. */
export function resetPendingWrites(): void {
  for (const p of [...cancels.values(), ...removals.values()]) clearTimeout(p.timer);
  cancels.clear();
  removals.clear();
  emit();
}
