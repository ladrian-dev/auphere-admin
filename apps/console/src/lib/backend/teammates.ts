import type { Call } from "../backend";

/**
 * Lane `teammates` — el roster que vive en la aplicación de escritorio
 * (spec 003). La consola **no** pinta nada de esto: solo lo proxea por el
 * BFF para que la app hable con la plataforma con la sesión de la persona.
 * Los tipos reflejan `api/console/schemas_teammates.py`: nunca ids de partner
 * ni de tenant; los estados son identificadores estables.
 */

export type MyState = "en_marcha" | "esperandote" | "en_pausa_por_tope" | "en_espera";

export type TeammatePermissions = {
  read: boolean;
  write: boolean;
  spend: boolean;
  publish: boolean;
  contact: boolean;
};

export type TeammateOut = {
  id: string;
  name: string;
  job: string;
  model: string;
  tool_names: string[];
  permissions: TeammatePermissions;
  local_exec: boolean;
  status: "active" | "archived";
  created_at: string;
  archived_at: string | null;
  my_state: MyState;
  my_unread: boolean;
  my_thread_id: string | null;
  last_done: string | null;
};

export type TeammateIn = {
  name: string;
  job: string;
  model: string;
  permissions?: Partial<TeammatePermissions>;
  local_exec?: boolean;
};

export type ModelChoiceOut = { id: string; note: string; cost_label: string };
export type TeammateJobsOut = { jobs: string[]; models: ModelChoiceOut[] };

export function teammatesApi(call: Call) {
  const enc = encodeURIComponent;
  const base = "/console/teammates";
  return {
    listTeammates: (includeArchived = false) =>
      call<TeammateOut[]>(`${base}${includeArchived ? "?include_archived=true" : ""}`),
    teammateJobs: () => call<TeammateJobsOut>(`${base}/jobs`),
    createTeammate: (body: TeammateIn) => call<TeammateOut>(base, { method: "POST", body }),
    patchTeammate: (id: string, body: Partial<TeammateIn>) =>
      call<TeammateOut>(`${base}/${enc(id)}`, { method: "PATCH", body }),
    archiveTeammate: (id: string) => call<void>(`${base}/${enc(id)}`, { method: "DELETE" }),
  };
}
