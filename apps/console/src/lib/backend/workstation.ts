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
  workdir: string;
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
