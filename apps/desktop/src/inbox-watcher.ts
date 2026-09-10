/**
 * La bandeja, vigilada desde el proceso principal — spec 003, Requisitos 5.3 y 7.
 *
 * Dos cosas que no son obvias y por eso están aquí, puras y probadas:
 *
 * 1. **El stream no tiene historia.** El proxy corta a los cinco minutos y un
 *    aviso publicado en ese hueco se pierde. Por eso, en **cada (re)conexión**
 *    se vuelve a pedir la bandeja entera: la verdad es `GET /inbox`, el stream
 *    solo acelera. Sin esto, una tarjeta decidida en otra pantalla se quedaría
 *    en la de aquí hasta que alguien recargara.
 * 2. **Lo que llega nuevo suena; lo que ya estaba, no.** Al reconciliar se
 *    comparan las tarjetas contra las que ya se conocían, y solo las nuevas
 *    pasan por la política de avisos.
 */
import { type Effect, type Level, type Pending, type Prefs, onArrival, onOpen } from "./notifications-policy.js";

export type InboxItem = {
  action_id: string;
  task_id: string | null;
  thread_id: string;
  run_id: string | null;
  teammate: { id: string; name: string };
  title: string;
  kind: string;
  level: Level;
  client_ref: string | null;
  proposed_at: string;
  can_decide: boolean;
};

export type WatcherPorts = {
  /** `GET /api/teammates/inbox` — la verdad. */
  fetchInbox(): Promise<InboxItem[]>;
  /** Abre el SSE; resuelve al terminar la conexión, rechaza si no se pudo abrir. */
  openStream(onEvent: (event: string, data: Record<string, unknown>) => void, signal: AbortSignal): Promise<void>;
  /** Lo que hay que hacer: avisar, marcar la bandeja. */
  apply(effects: Effect[]): void;
  /** Empuja a la pantalla. */
  push(channel: "app:inbox" | "app:inbox.changed" | "app:task.state", payload: unknown): void;
  prefs(): Prefs;
  wait(ms: number): Promise<void>;
};

const asPending = (item: InboxItem): Pending => ({
  action_id: item.action_id,
  level: item.level,
  teammate: item.teammate.name,
  title: item.title,
});

export class InboxWatcher {
  private known = new Map<string, InboxItem>();
  private controller: AbortController | null = null;
  private running = false;
  private firstPass = true;

  constructor(private readonly ports: WatcherPorts) {}

  get items(): InboxItem[] {
    return [...this.known.values()];
  }

  /** Reconcilia contra la verdad y devuelve lo que era nuevo. */
  async reconcile(): Promise<InboxItem[]> {
    const fresh = await this.ports.fetchInbox();
    const before = this.known;
    this.known = new Map(fresh.map((i) => [i.action_id, i]));
    this.ports.push("app:inbox", fresh);
    const added = fresh.filter((i) => !before.has(i.action_id));
    if (this.firstPass) {
      // Al abrir: un resumen, no una notificación por tarjeta (R7.3).
      this.firstPass = false;
      this.ports.apply(onOpen(fresh.map(asPending), this.ports.prefs()));
      return added;
    }
    for (const item of added) {
      this.ports.apply(onArrival(asPending(item), this.ports.prefs(), fresh.map(asPending)));
    }
    if (added.length === 0) this.ports.apply(onOpen([], this.ports.prefs()).filter((e) => e.kind === "badge"));
    return added;
  }

  /** Aplica un aviso del stream. La tarjeta desaparece sin recargar (R5.3). */
  onChanged(actionId: string): void {
    if (!this.known.delete(actionId)) return;
    this.ports.push("app:inbox.changed", { action_id: actionId });
    this.ports.push("app:inbox", this.items);
    this.ports.apply(onOpen([], this.ports.prefs()).filter((e) => e.kind === "badge"));
  }

  /** Bucle: conectar → reconciliar → escuchar → reconectar. */
  async start(): Promise<void> {
    if (this.running) return;
    this.running = true;
    let backoff = 400;
    while (this.running) {
      const controller = new AbortController();
      this.controller = controller;
      try {
        await this.reconcile();
        backoff = 400;
        await this.ports.openStream((event, data) => {
          if (event === "inbox.changed") this.onChanged(String(data.action_id ?? ""));
          else if (event === "task.state") this.ports.push("app:task.state", data);
        }, controller.signal);
      } catch {
        // Sin red o sin sesión: se reintenta con espera creciente. No se dice
        // nada a la pantalla: la bandeja que ya tiene sigue siendo lo último
        // que se supo, y eso es más honesto que vaciarla.
      }
      if (!this.running) break;
      await this.ports.wait(backoff);
      backoff = Math.min(backoff * 2, 30_000);
    }
  }

  stop(): void {
    this.running = false;
    this.controller?.abort();
    this.controller = null;
  }

  /** La bandeja se olvida al perder la sesión: no es de nadie hasta que alguien entra. */
  reset(): void {
    this.known = new Map();
    this.firstPass = true;
    this.ports.push("app:inbox", []);
  }
}
