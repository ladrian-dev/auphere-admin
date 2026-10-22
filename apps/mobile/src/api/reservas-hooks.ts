import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { sinceMinutes, wallClock, type BizNow, type LocalDate, type WallTime } from "@/lib/reservas-model";
import { useNowMs } from "@/lib/use-now";

import { useForbiddenRereadsMe, useMe } from "./hooks";
import { invalidateReservas, keys } from "./query";
import { reservasSource, type ConfigPatch, type NewReservation, type ResAction, type ResConfig, type Reservation } from "./reservas";

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

export function useFreeSlots(p: { date: LocalDate; serviceId?: string; proId?: string | null; partySize?: number } | null) {
  return useQuery({
    queryKey: keys.reservasSlots(p?.date ?? "", p?.serviceId ?? null, p?.proId ?? null, p?.partySize ?? null),
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
  return useInvalidating(({ key, ...b }: { partySize: number; name: string | null; date: LocalDate; time: number | null; key: string }) =>
    reservasSource().joinWaitlist(b, key),
  );
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
