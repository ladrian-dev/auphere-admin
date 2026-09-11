/**
 * El transporte real del puente, versión 2 — `contracts/device-bridge-v2.md`.
 *
 * **Solo sale.** Seis llamadas y todas salientes: el canje del código, y las
 * cinco operaciones de la credencial —latir, sondear, devolver resultado,
 * renovar y declarar un directorio—. No hay `listen` ni nada que se le parezca,
 * y hay un test que lo afirma.
 *
 * **Un fallo se levanta, no se convierte en silencio.** Y **un rechazo se
 * distingue de un fallo**: la plataforma dice por qué una credencial dejó de
 * valer (§V), y la barra necesita esa diferencia para pasar a
 * `volver_a_emparejar` o `archivada_desde_consola` en vez de a `reconectando`.
 */
import type { Inbound, Outbound, OutboundTransport } from "./bridge.js";
import { STDOUT_SAMPLE_LIMIT } from "./executor.js";
import type { DirectoryChecks } from "./directory-declare.js";

type FetchLike = (
  url: string,
  init?: { method?: string; headers?: Record<string, string>; body?: string },
) => Promise<{ ok: boolean; status: number; json(): Promise<unknown> }>;

export type HttpTransportOptions = {
  baseUrl: string;
  /** La credencial de la máquina. Se puede rotar tras `renew`. */
  token?: string;
  fetch?: FetchLike;
  appVersion?: string;
};

export type PairedCredential = {
  deviceId: string;
  credential: string;
  generation: number;
  expiresAt: string;
  partnerSlug: string;
  principalId: string;
  displayName: string;
};

export type PolledLink = {
  clientRef: string;
  clientName: string | null;
  workdir: string | null;
  needsDirectory: boolean;
};

export type PollResult = { work: Inbound[]; links: PolledLink[] };

/** La plataforma no contestó, o contestó con algo que no es una decisión. */
export class BridgeUnavailable extends Error {
  constructor(message: string) {
    super(message);
    this.name = "BridgeUnavailable";
  }
}

/** La plataforma decidió que esta credencial ya no vale, y dijo por qué. */
export class BridgeRejected extends Error {
  constructor(
    readonly reason: "unauthorized" | "device_archived" | "pairing_required",
    readonly detail?: string,
  ) {
    super(`la plataforma rechazó la credencial: ${reason}`);
    this.name = "BridgeRejected";
  }
}

/** El canje del código no valió. Un solo motivo visible, a propósito (3.3). */
export class PairingFailed extends Error {
  constructor(
    readonly code: "pairing_code_invalid" | "pairing_rate_limited",
    readonly retryAfterSeconds?: number,
  ) {
    super(code);
    this.name = "PairingFailed";
  }
}

/**
 * Un elemento de `work[]` tal como llega, traducido a lo que la aplicación
 * entiende. Lo que no venga completo se **descarta**: ejecutar algo a medio
 * entender en el ordenador de alguien es exactamente lo que no se hace.
 */
function toInbound(raw: unknown): Inbound | null {
  if (!raw || typeof raw !== "object") return null;
  const w = raw as Record<string, unknown>;
  const executionId = typeof w.execution_id === "string" ? w.execution_id : null;
  const executable = typeof w.executable === "string" ? w.executable : null;
  if (!executionId || !executable) return null;
  const args = Array.isArray(w.args) ? w.args.filter((a): a is string => typeof a === "string") : [];
  if (Array.isArray(w.args) && args.length !== w.args.length) return null;
  return {
    kind: "execute",
    executionId,
    executable,
    args,
    cwdRelative: typeof w.cwd_relative === "string" ? w.cwd_relative : null,
    timeoutMs: typeof w.timeout_ms === "number" ? w.timeout_ms : 0,
    ...(typeof w.client_ref === "string" ? { clientRef: w.client_ref } : {}),
    ...(typeof w.task_id === "string" ? { taskId: w.task_id } : {}),
  };
}

export class HttpTransport implements OutboundTransport {
  private readonly baseUrl: string;
  private token: string;
  private readonly fetch: FetchLike;
  private readonly appVersion: string | undefined;

  constructor(options: HttpTransportOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.token = options.token ?? "";
    this.fetch = options.fetch ?? (globalThis.fetch as unknown as FetchLike);
    this.appVersion = options.appVersion;
  }

  /** Tras `pair` o `renew`. Nunca se persiste aquí: eso es del almacén. */
  useToken(token: string): void {
    this.token = token;
  }

  private get headers(): Record<string, string> {
    return { Authorization: `Bearer ${this.token}`, "Content-Type": "application/json" };
  }

  // ── el canje, sin credencial ────────────────────────────────────────────

  async pair(input: { code: string; hostname: string; platform: "macos" | "windows" }): Promise<PairedCredential> {
    const response = await this.fetch(`${this.baseUrl}/device/pair`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code: input.code,
        hostname: input.hostname,
        platform: input.platform,
        app_version: this.appVersion,
      }),
    });
    if (response.status === 404) throw new PairingFailed("pairing_code_invalid");
    if (response.status === 429) throw new PairingFailed("pairing_rate_limited");
    if (!response.ok) throw new BridgeUnavailable(`/device/pair respondió ${response.status}`);
    const body = (await response.json()) as Record<string, unknown>;
    return {
      deviceId: String(body.device_id),
      credential: String(body.credential),
      generation: Number(body.generation),
      expiresAt: String(body.expires_at),
      partnerSlug: String(body.partner_slug),
      principalId: String(body.principal_id),
      displayName: String(body.display_name),
    };
  }

  // ── las cinco operaciones ───────────────────────────────────────────────

  async send(message: Outbound): Promise<void> {
    const [path, body] = this.encode(message);
    if (path === null) return; // progreso: no viaja todavía, y callarse es correcto
    const response = await this.fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(body),
    });
    await this.assertAccepted(response, path);
  }

  async poll(): Promise<Inbound[]> {
    return (await this.pollAll()).work;
  }

  async pollAll(): Promise<PollResult> {
    const response = await this.fetch(`${this.baseUrl}/device/poll`, {
      method: "GET",
      headers: this.headers,
    });
    await this.assertAccepted(response, "/device/poll");
    const body = (await response.json()) as { work?: Inbound[]; links?: Array<Record<string, unknown>> };
    return {
      // El cable habla `snake_case` (`contracts/local-dispatch.md`) y el resto
      // de la aplicación, `camelCase`. La traducción vive **aquí**, en el
      // límite, y no en quien ejecuta: así el ejecutor no sabe de HTTP.
      work: (Array.isArray(body.work) ? body.work : []).map(toInbound).filter((w): w is Inbound => w !== null),
      links: (body.links ?? []).map((l) => ({
        clientRef: String(l.client_ref),
        clientName: l.client_name === null || l.client_name === undefined ? null : String(l.client_name),
        workdir: l.workdir === null || l.workdir === undefined ? null : String(l.workdir),
        needsDirectory: Boolean(l.needs_directory),
      })),
    };
  }

  async renew(): Promise<{ credential: string; generation: number; expiresAt: string }> {
    const response = await this.fetch(`${this.baseUrl}/device/renew`, {
      method: "POST",
      headers: this.headers,
    });
    await this.assertAccepted(response, "/device/renew");
    const body = (await response.json()) as Record<string, unknown>;
    const renewed = {
      credential: String(body.credential),
      generation: Number(body.generation),
      expiresAt: String(body.expires_at),
    };
    this.token = renewed.credential;
    return renewed;
  }

  async declareLink(input: { clientRef: string; workdir: string; checks: DirectoryChecks }): Promise<void> {
    const response = await this.fetch(`${this.baseUrl}/device/links`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify({ client_ref: input.clientRef, workdir: input.workdir, checks: input.checks }),
    });
    await this.assertAccepted(response, "/device/links");
  }

  // ── rechazo ≠ fallo ─────────────────────────────────────────────────────

  private async assertAccepted(
    response: { ok: boolean; status: number; json(): Promise<unknown> },
    path: string,
  ): Promise<void> {
    if (response.ok) return;
    if (response.status === 401) throw new BridgeRejected("unauthorized");
    if (response.status === 403) {
      const body = (await response.json().catch(() => ({}))) as { code?: string; reason?: string };
      if (body.code === "device_archived") throw new BridgeRejected("device_archived", body.reason);
      if (body.code === "pairing_required") throw new BridgeRejected("pairing_required");
    }
    throw new BridgeUnavailable(`${path} respondió ${response.status}`);
  }

  /** Traduce el mensaje del contrato al cuerpo que espera la API. */
  private encode(message: Outbound): [string | null, Record<string, unknown>] {
    switch (message.kind) {
      case "heartbeat":
        return ["/device/heartbeat", {}];
      case "enrol":
        return ["/device/heartbeat", { app_version: message.appVersion }];
      case "execution_result":
        return [
          "/device/result",
          {
            execution_id: message.executionId,
            outcome: message.outcome,
            exit_code: message.exitCode,
            children_reaped: message.childrenReaped,
            // El servidor la acota a 2 KB; aquí se acota igual para que un
            // cambio de un lado no dependa del otro.
            stdout_sample: (message.stdoutSample ?? "").slice(0, STDOUT_SAMPLE_LIMIT) || undefined,
            denial_code: message.denialCode,
          },
        ];
      case "execution_progress":
        return [null, {}];
    }
  }
}
