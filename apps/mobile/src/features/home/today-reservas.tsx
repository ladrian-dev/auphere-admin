import type { Reservation, ResConfig } from "@/api/reservas";
import type { WallTime } from "@/lib/reservas-model";

/**
 * Today in Reservas, for Inicio's «Hoy» tile (spec 044, research D4; spec 069,
 * R8.1): counted from the very read the Reservas tab makes for today, so the
 * two never disagree. `null` is a client without the module: no tile at all
 * (R8.2).
 */
export type TodayReservas =
  | { state: "loading" }
  | { state: "error"; retry: () => void }
  | { state: "ready"; config: ResConfig; items: Reservation[]; now: WallTime; waitlist: number | null };
