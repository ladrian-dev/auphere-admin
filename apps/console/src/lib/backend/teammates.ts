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

export type TaskState =
  | "en_marcha"
  | "esperandote"
  | "pausada_por_tope"
  | "terminada"
  | "cancelada"
  | "caducada";

export type TaskOut = {
  id: string;
  thread_id: string;
  teammate_id: string;
  title: string;
  state: TaskState;
  expires_at: string;
  current_run_id: string | null;
  pending_action_id: string | null;
  created_at: string;
  updated_at: string;
  ended_at: string | null;
};

export type ActionLevel = "critico" | "aviso" | "informativo";

export type InboxItemOut = {
  action_id: string;
  task_id: string | null;
  thread_id: string;
  run_id: string | null;
  teammate: { id: string; name: string };
  title: string;
  kind: string;
  level: ActionLevel;
  client_ref: string | null;
  proposed_at: string;
  /** `false` cuando el rol no puede aplicar lo que hay detrás: la tarjeta lo dice antes. */
  can_decide: boolean;
};

export type LocalExecCeiling = { ceiling: ExecMode; updated_by: string | null };
export type ExecMode = "ask" | "always" | "never";

export type LocalExecPref = {
  executable: string;
  mode: ExecMode;
  effective: ExecMode;
  capped: boolean;
};

export type LocalExecPolicy = {
  ceiling: ExecMode;
  global_mode: ExecMode;
  per_executable: LocalExecPref[];
  /** Lo que de verdad se aplica, con el techo ya puesto. */
  effective: ExecMode;
  /** El techo bajó lo que la persona pidió (R10.4). */
  capped: boolean;
};

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
    teammateInbox: () => call<InboxItemOut[]>(`${base}/inbox`),
    teammateTasks: (state?: string) =>
      call<TaskOut[]>(`${base}/tasks${state ? `?state=${enc(state)}` : ""}`),
    cancelTeammateTask: (id: string) =>
      call<TaskOut>(`${base}/tasks/${enc(id)}/cancel`, { method: "POST" }),
    // El techo vive en la página de equipo: es una decisión del partner, no una
    // preferencia de quien opera (spec 003, R10.1).
    localExecPrefs: () => call<LocalExecPolicy>(`${base}/local-exec-prefs`),
    setLocalExecPref: (pref: { executable: string | null; mode: ExecMode }) =>
      call<LocalExecPolicy>(`${base}/local-exec-prefs`, { method: "PUT", body: pref }),
    localExecCeiling: () => call<LocalExecCeiling>("/console/team/local-exec-ceiling"),
    setLocalExecCeiling: (ceiling: ExecMode) =>
      call<LocalExecCeiling>("/console/team/local-exec-ceiling", { method: "PUT", body: { ceiling } }),
  };
}
