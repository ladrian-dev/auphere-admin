/**
 * La segunda superficie propia — spec 003, Requisito 12 (D9).
 *
 * Todo lo que el renderer puede pedir pasa por aquí, y todo lo que se le
 * contesta sale **redactado** (`app-ipc.ts`). Este módulo no sabe de Electron
 * más que lo justo: recibe el `PlatformClient`, el `StreamHub` y la función
 * que empuja al renderer; las decisiones viven en módulos puros con test.
 */
import type { IpcMain } from "electron";

import { InvalidIpcInput, redact, validateInput } from "../app-ipc.js";
import type { Section } from "../sections.js";

/** Las comodidades de ventana; su forma y sus defectos viven en el módulo puro. */
import type { ShellPrefs } from "../shell-prefs.js";

export type { ShellPrefs };
import { PlatformClient, SessionLost } from "../platform-client.js";
import type { GateDecision, WhoamiClient } from "../session-gate.js";
import type { InboxWatcher } from "../inbox-watcher.js";
import type { Prefs } from "../notifications-policy.js";
import type { StreamHub } from "../stream-hub.js";

export type Push = (channel: string, payload: unknown) => void;

export type AppSurfaceOptions = {
  ipcMain: IpcMain;
  platform: PlatformClient;
  streams: StreamHub;
  whoami: WhoamiClient;
  push: Push;
  showConsole: (path: string) => void;
  /* ── El armazón — spec 010 ────────────────────────────────────────────── */
  /** Muestra una sección: la pinta la pantalla o la consola, según cuál sea. */
  showSection: (section: Section) => void;
  /** Dónde cabe el panel, medido por la pantalla (R1.3). Sólo números. */
  setPanelBounds: (rect: { x: number; y: number; width: number; height: number }) => void;
  /** Comodidades de ventana; la lista de claves persistibles es cerrada. */
  shellPrefs: { read(): ShellPrefs; write(next: Partial<ShellPrefs>): ShellPrefs };
  /** El puesto de trabajo, absorbido en el armazón (enmienda de la spec 002). */
  workstation: { state(): unknown };
  onSessionLost: (reason: "anonymous" | "no_membership") => void;
  inbox: InboxWatcher;
  notificationPrefs: { read(): Prefs; write(next: Prefs): Prefs };
  /** Lo que esta máquina sabe: dónde trabaja cada cliente y qué nombraron los
   *  comandos de cada tarea (R11). Lo pone el runtime del puente. */
  machine: {
    presence(): { machine: { displayName: string; hostname: string } | null; presence: "presente" | "ausente" };
    links(): Array<{ clientRef: string; clientName: string | null; workdir: string | null }>;
    filesForTask(taskId: string | null): string[];
  };
};

const q = encodeURIComponent;

export function registerAppSurface(o: AppSurfaceOptions): void {
  // `never` en el parámetro es lo que deja registrar manejadores con formas de
  // entrada distintas sin `any`: por contravarianza, cualquier `(input: X) =>`
  // es asignable aquí. La entrada real la valida `validateInput` antes de
  // llamar, que es donde vive la garantía.
  const handle = (channel: string, fn: (input: never) => Promise<unknown> | unknown) => {
    o.ipcMain.handle(channel, async (_event, input: unknown) => {
      validateInput(channel, input);
      try {
        return redact(await fn(input as never));
      } catch (error) {
        if (error instanceof SessionLost) {
          o.onSessionLost(error.reason);
          return { ok: false, status: 401, detail: "session_lost", code: error.reason, body: null };
        }
        if (error instanceof InvalidIpcInput) throw error;
        return { ok: false, status: 0, detail: "network", code: null, body: null };
      }
    });
  };

  handle("app:whoami", async () => {
    const who = await o.whoami.whoami();
    if (who.kind !== "member") return { kind: who.kind };
    return {
      kind: "member",
      user_id: who.userId,
      partner_slug: who.partnerSlug,
      locale: who.locale ?? null,
      permissions: who.permissions ?? [],
    };
  });

  handle("app:roster.list", () => o.platform.request("/api/teammates"));
  handle("app:roster.jobs", () => o.platform.request("/api/teammates/jobs"));
  handle("app:roster.create", (input: { name: string; job: string; model: string; permissions?: unknown; local_exec?: boolean }) =>
    o.platform.request("/api/teammates", { method: "POST", body: input }),
  );
  handle("app:roster.update", (input: { id: string; patch: Record<string, unknown> }) =>
    o.platform.request(`/api/teammates/${q(input.id)}`, { method: "PATCH", body: input.patch }),
  );
  handle("app:roster.archive", (input: { id: string }) =>
    o.platform.request(`/api/teammates/${q(input.id)}`, { method: "DELETE" }),
  );
  // Las notas de «este teammate cambió» (R2.4). Se leen al abrir el hilo: no
  // hay evento nuevo, y quien no estaba mirando las ve igual.
  handle("app:roster.changes", (input: { id: string }) =>
    o.platform.request(`/api/teammates/${q(input.id)}/changes`),
  );

  // El hilo de la persona con ese teammate: se busca, y si no hay, se abre.
  handle("app:thread.open", async (input: { teammate_id: string }) => {
    const listed = await o.platform.request<Array<{ id: string; archived_at: string | null }>>(
      `/api/companion/threads?teammate_id=${q(input.teammate_id)}`,
    );
    if (listed.ok) {
      const open = listed.data.find((t) => !t.archived_at);
      if (open) return { ok: true, data: { thread_id: open.id } };
    }
    const created = await o.platform.request<{ id: string }>("/api/companion/threads", {
      method: "POST",
      body: { title: "Hilo", mode: "build", teammate_id: input.teammate_id },
    });
    return created.ok ? { ok: true, data: { thread_id: created.data.id } } : created;
  });
  handle("app:thread.runs", (input: { thread_id: string }) =>
    o.platform.request(`/api/companion/threads/${q(input.thread_id)}/runs`),
  );
  handle("app:run.events", (input: { run_id: string; since_seq?: number }) =>
    o.platform.request(`/api/companion/runs/${q(input.run_id)}/events?since_seq=${input.since_seq ?? 0}`),
  );
  handle("app:thread.send", (input: { thread_id: string; text: string; client_ref?: string }) =>
    o.platform.request(`/api/companion/threads/${q(input.thread_id)}/runs`, {
      method: "POST",
      body: { prompt: input.text, page_context: input.client_ref ? { client_ref: input.client_ref } : null },
    }),
  );
  handle("app:thread.cancel", (input: { run_id: string }) =>
    o.platform.request(`/api/companion/runs/${q(input.run_id)}`, { method: "DELETE" }),
  );
  handle(
    "app:inbox.decide",
    async (input: { action_id: string; run_id: string; decision: string; note?: string }) => {
      const result = await o.platform.request(`/api/companion/runs/${q(input.run_id)}/resume`, {
        method: "POST",
        body: {
          action_id: input.action_id,
          decision: input.decision,
          ...(input.note ? { note: input.note } : {}),
        },
      });
      // La tarjeta se retira aquí y no esperando al aviso: quien decide ve el
      // efecto ya (R5.3). El aviso del canal es para las **otras** pantallas.
      if (result.ok) o.inbox.onChanged(input.action_id);
      return result;
    },
  );
  handle("app:inbox.list", () => ({ ok: true, data: o.inbox.items }));
  handle("app:tasks.list", (input: { state?: string } | undefined) =>
    o.platform.request(`/api/teammates/tasks${input?.state ? `?state=${q(input.state)}` : ""}`),
  );
  handle("app:tasks.cancel", (input: { id: string }) =>
    o.platform.request(`/api/teammates/tasks/${q(input.id)}/cancel`, { method: "POST" }),
  );
  handle("app:notifications.prefs", (input: { silence_aviso?: boolean } | undefined) =>
    input === undefined
      ? o.notificationPrefs.read()
      : o.notificationPrefs.write({ silenceAviso: input.silence_aviso === true }),
  );
  handle("app:policy.prefs", () => o.platform.request("/api/teammates/local-exec-prefs"));
  handle("app:policy.setPref", (input: { executable: string | null; mode: string }) =>
    o.platform.request("/api/teammates/local-exec-prefs", {
      method: "PUT",
      body: { executable: input.executable, mode: input.mode },
    }),
  );
  // El consumo del mes con su reparto. Hasta la US5 esto contestaba el
  // presupuesto del Companion con `by_teammate: []` — un hueco honesto mientras
  // la ruta no existía; ahora existe y se pregunta por ella.
  handle("app:usage", () => o.platform.request("/api/teammates/usage"));
  handle("app:team", () => o.platform.request("/api/team"));

  /**
   * El entorno de un hilo — Requisito 11.
   *
   * Junta dos mundos que no se ven entre sí: la plataforma sabe de **tareas**
   * (cuál está abierta en este hilo) y esta máquina sabe de **directorios** y
   * de lo que los comandos nombraron. Ninguno de los dos datos viaja al otro:
   * la lista de ficheros no sube, y el directorio no baja a ningún cliente.
   *
   * `files` es «lo que los comandos nombraron», no lo que se escribió: la
   * plataforma nunca recibe esa lista (§III) y la aplicación no mira el disco
   * para adivinarla. El panel lo dice con esas palabras.
   */
  handle("app:env.forThread", async (input: { thread_id: string }) => {
    const tasks = await o.platform.request<Array<{ id: string; thread_id: string; state: string }>>(
      "/api/teammates/tasks",
    );
    const task = tasks.ok
      ? (tasks.data.find((row) => row.thread_id === input.thread_id && row.state === "en_marcha") ??
        tasks.data.find((row) => row.thread_id === input.thread_id) ??
        null)
      : null;
    const { machine, presence } = o.machine.presence();
    return {
      ok: true,
      data: {
        machine,
        presence,
        links: o.machine.links(),
        task_id: task?.id ?? null,
        files: o.machine.filesForTask(task?.id ?? null),
      },
    };
  });

  handle("app:stream.open", (input: { run_id: string; since_seq: number }) => ({
    stream_id: o.streams.start(`/api/companion/runs/${q(input.run_id)}/stream?since_seq=${input.since_seq}`),
  }));
  handle("app:stream.close", (input: { stream_id: string }) => {
    o.streams.close(input.stream_id);
    return null;
  });

  handle("app:openConsole", (input: { path: string }) => {
    o.showConsole(input.path);
    return null;
  });

  /* ── El armazón — spec 010 ────────────────────────────────────────────── */

  handle("app:shell.showSection", (input: { section: Section }) => {
    o.showSection(input.section);
    return null;
  });

  handle("app:shell.contentBounds", (input: { x: number; y: number; width: number; height: number }) => {
    o.setPanelBounds(input);
    return null;
  });

  handle("app:shell.prefs", (input: Partial<ShellPrefs> | undefined) => o.shellPrefs.write(input ?? {}));

  /**
   * El estado del puesto, a petición (R3.6).
   *
   * El empuje llega con cada cambio, pero la pantalla necesita saberlo también
   * al montarse — si no, hasta el primer cambio no tendría nada que pintar y
   * volvería a inventarse un estado, que es de lo que veníamos.
   */
  handle("app:workstation.state", () => o.workstation.state());
}

/**
 * La decisión de la puerta de sesión, para la pantalla. Sin credencial dentro.
 *
 * `unconfirmed` (spec 010 R3.2) devuelve `null` **a propósito**: no se pudo
 * preguntar, así que no hay nada nuevo que empujar. Lo que la pantalla tiene
 * que enterarse en ese caso es de la conexión, y eso viaja por `app:connectivity`.
 */
export function sessionForRenderer(
  decision: GateDecision,
): { kind: string; locale?: "es" | "en"; reason?: string } | null {
  if (decision.kind === "unconfirmed") return null;
  if (decision.kind === "start") return { kind: "start", ...(decision.locale ? { locale: decision.locale } : {}) };
  if (decision.kind === "stop") return { kind: "stop", reason: decision.reason };
  return { kind: "pair_needed", ...(decision.locale ? { locale: decision.locale } : {}) };
}
