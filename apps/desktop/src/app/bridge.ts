/**
 * El puente tipado sobre `window.auphere` — lo que el preload expone
 * (`app-ipc.ts`). El renderer no sabe de red: pregunta y recibe.
 */
import type { Section } from "../sections";
import type {
  CompanionEvents,
  CompanionResumed,
  CompanionRunStarted,
  CompanionThreadRuns,
  Result,
  WireEvent,
} from "@nexus/companion-ui";

/** Los cinco estados. El vocabulario vive en `app-state.ts`, que es donde se
 *  comprueba cuál de ellos es ocio (R4.7). */
import type { MyState } from "../app-state";

export type { MyState };
export type Teammate = {
  id: string;
  name: string;
  job: string;
  model: string;
  tool_names: string[];
  permissions: { read: boolean; write: boolean; spend: boolean; publish: boolean; contact: boolean };
  local_exec: boolean;
  status: "active" | "archived";
  my_state: MyState;
  my_unread: boolean;
  my_thread_id: string | null;
  last_done: string | null;
};
export type Whoami =
  | { kind: "anonymous" | "no_membership" }
  | { kind: "member"; user_id: string; partner_slug: string; locale: "es" | "en" | null; permissions: string[] };
export type SessionPush = { kind: "start" | "stop" | "pair_needed"; locale?: "es" | "en"; reason?: string };
export type PresencePush = {
  machine: { displayName: string; hostname: string } | null;
  presence: "presente" | "ausente";
  links: Array<{ clientRef: string; clientName: string | null; needsDirectory: boolean }>;
};
export type ExecMode = "ask" | "always" | "never";
export type LocalExecPolicy = {
  ceiling: ExecMode;
  global_mode: ExecMode;
  per_executable: Array<{ executable: string; mode: ExecMode; effective: ExecMode; capped: boolean }>;
  effective: ExecMode;
  capped: boolean;
};

/** `cost_label` es relativo a la oferta del partner, no un precio (R2.1). */
export type CostLabel = "bajo" | "medio" | "alto" | "desconocido";
export type Jobs = { jobs: string[]; models: Array<{ id: string; note: string; cost_label: CostLabel }> };

/** Una nota de «este teammate cambió» (R2.4). Sin valores: solo qué y quién. */
export type TeammateChange = {
  id: string;
  fields: Array<"job" | "permissions" | "local_exec" | "model">;
  by: string | null;
  at: string;
};

/** El consumo del mes (R8.1): el medidor del partner y el reparto por teammate. */
export type Budget = {
  used: number;
  cap: number;
  remaining: number;
  percent: number;
  exhausted: boolean;
  period: string;
  resets_at: string;
};
export type UsageRow = {
  teammate_id: string;
  name: string;
  input_tokens: number;
  output_tokens: number;
  runs: number;
};
export type Usage = { budget: Budget; by_teammate: UsageRow[] };

/** El equipo, solo para leerlo: administrar es de la consola (R8.2). */
export type TeamMember = {
  id: string;
  email: string;
  display_name: string | null;
  role: string;
  status: string;
  is_you: boolean;
};
export type Team = { members: TeamMember[] };

/** El entorno de un hilo (R11): mitad plataforma (la tarea), mitad máquina. */
export type ThreadEnv = {
  machine: { displayName: string; hostname: string } | null;
  presence: "presente" | "ausente";
  links: Array<{ clientRef: string; clientName: string | null; workdir: string | null }>;
  task_id: string | null;
  /** Lo que los comandos de esa tarea nombraron. Nunca contenido. */
  files: string[];
};

export type Level = "critico" | "aviso" | "informativo";
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
export type TaskState =
  | "en_marcha"
  | "esperandote"
  | "pausada_por_tope"
  | "terminada"
  | "cancelada"
  | "caducada";
export type Task = {
  id: string;
  thread_id: string;
  teammate_id: string;
  title: string;
  state: TaskState;
  expires_at: string;
  pending_action_id: string | null;
  updated_at: string;
};

type Push = {
  "app:event": { stream_id: string; event: WireEvent };
  "app:stream.end": { stream_id: string; ok: boolean };
  "app:inbox.changed": { action_id: string; decision?: string };
  "app:task.state": { task_id: string; state: TaskState; cause: string };
  "app:inbox": InboxItem[];
  "app:inbox.focus": { action_id: string | null };
  "app:session": SessionPush;
  "app:presence": PresencePush;

  /* ── Spec 010 ─────────────────────────────────────────────────────────── */
  /** Dónde está la consola, para que la lista lateral lo marque (R1.4). */
  "app:console.location": { section: Section; path: string };
  "app:console.failed": { section: Section; code: number } | null;
  "app:handoff": { url: string };
  "app:workstation": WorkstationView;
  "app:signIn": SignInView;
  "app:update": UpdateView;
  /** La **única** fuente del número de decisiones que esperan (R5.4). */
  "app:waiting": WaitingView;
  /** «Sin red» dicho por su nombre, que no es «sin sesión» (R3.1). */
  "app:connectivity": ConnectivityView;
  /** La orden del menú «Mostrar u ocultar la lista lateral» (R1.7). */
  "app:shell.toggleSidebar": Record<string, never>;
};

/** Las preferencias de ventana que la cáscara guarda (lista cerrada). */
export type ShellPrefs = { theme: "system" | "light" | "dark"; sidebarWidth: number; silenceAviso: boolean };

/** El estado del puesto, tal como lo pinta el armazón (spec 010, R3.6). */
export type WorkstationView = {
  status:
    | "comprobando"
    | "sin_emparejar"
    | "emparejando"
    | "conectada"
    | "reconectando"
    | "sin_sesion"
    | "volver_a_emparejar"
    | "archivada_desde_consola"
    | "version_no_admitida";
  machine_name?: string;
  since?: string;
  cause?: "sin_red" | "sin_ejecutor" | "sesion_perdida";
  required_version?: string;
  missing_directories?: number;
  actions: Array<"emparejar" | "desemparejar" | "directorios" | "actualizar">;
};

/** La espera cuando algo ocurre en el navegador (R7.2). */
export type SignInView = { state: "idle" | "esperando" | "vuelto" | "cancelada" | "caducada" | "error"; since?: string };

/** El ciclo de la descarga. «No admitida» es del puesto, no de aquí (R6.4). */
export type UpdateView = { state: "idle" | "descargando" | "lista" | "esperando_trabajo"; version?: string };

/** Lo que falta para estar en marcha (R7.6). Derivado, no dato nuevo. */
export type SetupChecklist = {
  steps: Array<{
    key: "cuenta_lista" | "maquina_emparejada" | "ejecutor_presente" | "primer_teammate" | "primer_turno" | "avisos_concedidos";
    state: "hecho" | "pendiente" | "no_aplica";
    section?: Section;
    blocked_reason_key?: string;
  }>;
};

/** Cómo está la conexión (R3.1): «no pude preguntar» no es «no hay sesión». */
export type ConnectivityView = { state: "online" | "offline" | "unconfirmed"; since: string };

/** El derivado único de lo que espera una decisión (R5.4). */
export type WaitingView = { count: number; items: Array<{ action_id: string; teammate_id: string; level: Level; since: string }> };

export interface AuphereBridge {
  whoami(): Promise<Whoami>;
  rosterList(): Promise<Result<Teammate[]>>;
  rosterJobs(): Promise<Result<Jobs>>;
  rosterCreate(input: { name: string; job: string; model: string; permissions?: Partial<Teammate["permissions"]>; local_exec?: boolean }): Promise<Result<Teammate>>;
  rosterUpdate(input: { id: string; patch: Record<string, unknown> }): Promise<Result<Teammate>>;
  rosterArchive(input: { id: string }): Promise<Result<null>>;
  rosterChanges(input: { id: string }): Promise<Result<TeammateChange[]>>;
  threadOpen(input: { teammate_id: string }): Promise<Result<{ thread_id: string }>>;
  threadRuns(input: { thread_id: string }): Promise<Result<CompanionThreadRuns>>;
  runEvents(input: { run_id: string; since_seq?: number }): Promise<Result<CompanionEvents>>;
  threadSend(input: { thread_id: string; text: string; client_ref?: string }): Promise<Result<CompanionRunStarted>>;
  threadCancel(input: { run_id: string }): Promise<Result<null>>;
  streamOpen(input: { run_id: string; since_seq: number }): Promise<{ stream_id: string }>;
  streamClose(input: { stream_id: string }): Promise<null>;
  inboxDecide(input: { action_id: string; run_id: string; decision: string; note?: string }): Promise<Result<CompanionResumed>>;
  inboxList(): Promise<Result<InboxItem[]>>;
  tasksList(input?: { state?: string }): Promise<Result<Task[]>>;
  tasksCancel(input: { id: string }): Promise<Result<Task>>;
  notificationsPrefs(input?: { silence_aviso?: boolean }): Promise<{ silenceAviso: boolean }>;
  policyPrefs(): Promise<Result<LocalExecPolicy>>;
  policySetPref(input: { executable: string | null; mode: ExecMode }): Promise<Result<LocalExecPolicy>>;
  usage(): Promise<Result<Usage>>;
  envForThread(input: { thread_id: string }): Promise<Result<ThreadEnv>>;
  team(): Promise<Result<Team>>;
  openConsole(input: { path: string }): Promise<null>;

  /* ── El armazón — spec 010 ────────────────────────────────────────────── */
  /** Pide mostrar una sección. Secciones, no rutas: la lista es cerrada. */
  shellShowSection(input: { section: Section }): Promise<null>;
  /** Dónde cabe el panel, para que el principal coloque ahí la consola. */
  shellContentBounds(input: { x: number; y: number; width: number; height: number }): Promise<null>;
  /** Comodidades de ventana: tema, ancho de la lista lateral, ruido de avisos. */
  shellPrefs(input: { theme?: "system" | "light" | "dark"; sidebarWidth?: number; silenceAviso?: boolean }): Promise<ShellPrefs>;

  /* ── El puesto, absorbido — spec 010 (enmienda de la 002) ─────────────── */
  workstationState(): Promise<WorkstationView>;
  workstationPair(input: { code: string }): Promise<Result<{ machine_name: string }>>;
  workstationUnpair(): Promise<Result<null>>;
  workstationPickDirectory(input: { client_ref: string }): Promise<Result<{ path_shown: string }>>;

  /* ── Recorridos que salen y vuelven — spec 010 ────────────────────────── */
  signInStart(): Promise<SignInView>;
  signInCancel(): Promise<null>;
  setupStatus(): Promise<Result<SetupChecklist>>;
  updateInstall(): Promise<{ ok: boolean; error?: "busy" }>;
  /** Comprobar el canal ahora (R6.4, R6.5). */
  updateCheck(): Promise<null>;
  handoffDone(input: { kind: "sign_in" | "payment" }): Promise<null>;

  on<K extends keyof Push>(channel: K, callback: (payload: Push[K]) => void): () => void;
}

declare global {
  interface Window {
    auphere: AuphereBridge;
  }
}

export const bridge: AuphereBridge = window.auphere;
