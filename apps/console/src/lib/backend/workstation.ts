import type { Call } from "../backend";

/**
 * Lane `workstation` — el puesto de trabajo en la máquina del partner
 * (spec 001, superficie 3a). Los tipos reflejan
 * `api/console/schemas_workstation.py`: metadatos, nunca ids internos de
 * tenant, y **nunca la salida de un comando** — la auditoría dice qué pasó,
 * no qué dijo. Se difunde en `backendFor` desde `lib/backend.ts`.
 */

/** Derivada del latido, nunca almacenada: si el proceso muere, decae sola. */
export type Presence = "presente" | "ausente";

export type DeviceOut = {
  id: string;
  display_name: string;
  platform: "macos" | "windows";
  /** Del vínculo con este cliente; `null` mientras la máquina no lo declare. */
  workdir: string | null;
  app_version: string | null;
  last_heartbeat_at: string | null;
  presence: Presence;
  enrolled_at: string;
};

export type ExecutableOut = {
  id: string;
  executable: string;
  added_by: string;
  added_at: string;
};

/**
 * `denial_code` y no `reason`: es vocabulario cerrado, no prosa. Los
 * esquemas de `/console/*` no pueden llevar cuerpos de mensaje (decisión C8).
 */
export type ExecutionOut = {
  id: string;
  executable: string;
  outcome: "completada" | "expirada" | "terminada" | "denegada";
  denial_code: string | null;
  started_at: string;
  ended_at: string | null;
  exit_code: number | null;
  children_reaped: number;
};

export function workstationApi(call: Call) {
  const enc = encodeURIComponent;
  const base = (ref: string) => `/console/clients/${enc(ref)}/workstation`;
  return {
    listDevices: (ref: string) => call<DeviceOut[]>(`${base(ref)}/devices`),
    listExecutables: (ref: string) => call<ExecutableOut[]>(`${base(ref)}/executables`),
    addExecutable: (ref: string, executable: string) =>
      call<ExecutableOut>(`${base(ref)}/executables`, { method: "POST", body: { executable } }),
    archiveExecutable: (ref: string, id: string) =>
      call<void>(`${base(ref)}/executables/${enc(id)}`, { method: "DELETE" }),
    listExecutions: (ref: string) => call<ExecutionOut[]>(`${base(ref)}/executions`),
  };
}

// ── spec 002: el puesto de trabajo a nivel de partner ───────────────────
//
// La máquina es del partner y de la persona que la emparejó; los ejecutables
// siguen siendo del cliente (arriba). Ninguna llamada lleva `partner_id`,
// `principal_id` ni `tenant_id`, y ninguna acepta un `workdir`: la consola no
// teclea rutas — las declara la máquina por el puente.

export type MachineClientOut = {
  ref: string;
  name: string | null;
  workdir: string | null;
  needs_directory: boolean;
};

export type MachineOut = {
  id: string;
  display_name: string;
  hostname: string;
  platform: "macos" | "windows";
  app_version: string | null;
  presence: Presence;
  last_heartbeat_at: string | null;
  enrolled_at: string;
  owner_user_id: string;
  owner_display_name: string | null;
  mine: boolean;
  archived_at: string | null;
  archived_reason: string | null;
  clients: MachineClientOut[];
};

/** El código, una sola vez. `ttl_seconds` es lo que la cuenta atrás muestra. */
export type PairingCodeOut = { code: string; expires_at: string; ttl_seconds: number };

export type SetupStepKey = "paired" | "clients" | "directories" | "executables";
export type SetupStepOut = { key: SetupStepKey; done: boolean; pending: number };
export type SetupOut = { complete: boolean; steps: SetupStepOut[] };

export function workstationPartnerApi(call: Call) {
  const enc = encodeURIComponent;
  const base = "/console/workstation";
  return {
    issuePairingCode: () => call<PairingCodeOut>(`${base}/pairing-codes`, { method: "POST" }),
    listMachines: (includeArchived = false) =>
      call<MachineOut[]>(`${base}/devices${includeArchived ? "?include_archived=true" : ""}`),
    renameMachine: (id: string, display_name: string) =>
      call<MachineOut>(`${base}/devices/${enc(id)}`, { method: "PATCH", body: { display_name } }),
    archiveMachine: (id: string) => call<void>(`${base}/devices/${enc(id)}`, { method: "DELETE" }),
    linkClient: (id: string, client_ref: string) =>
      call<MachineClientOut>(`${base}/devices/${enc(id)}/clients`, { method: "POST", body: { client_ref } }),
    unlinkClient: (id: string, ref: string) =>
      call<void>(`${base}/devices/${enc(id)}/clients/${enc(ref)}`, { method: "DELETE" }),
    workstationSetup: () => call<SetupOut>(`${base}/setup`),
  };
}
