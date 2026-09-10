/**
 * El puente tipado sobre `window.auphere` — lo que el preload expone
 * (`app-ipc.ts`). El renderer no sabe de red: pregunta y recibe.
 */
import type {
  CompanionBudget,
  CompanionEvents,
  CompanionResumed,
  CompanionRunStarted,
  CompanionThreadRuns,
  Result,
  WireEvent,
} from "@nexus/companion-ui";

export type MyState = "en_marcha" | "esperandote" | "en_pausa_por_tope" | "en_espera";
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

export type Jobs = { jobs: string[]; models: Array<{ id: string; note: string; cost_label: string }> };

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
};

export interface AuphereBridge {
  whoami(): Promise<Whoami>;
  rosterList(): Promise<Result<Teammate[]>>;
  rosterJobs(): Promise<Result<Jobs>>;
  rosterCreate(input: { name: string; job: string; model: string; permissions?: Partial<Teammate["permissions"]>; local_exec?: boolean }): Promise<Result<Teammate>>;
  rosterUpdate(input: { id: string; patch: Record<string, unknown> }): Promise<Result<Teammate>>;
  rosterArchive(input: { id: string }): Promise<Result<null>>;
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
  usage(): Promise<Result<{ budget: CompanionBudget; by_teammate: unknown[] }>>;
  openConsole(input: { path: string }): Promise<null>;
  on<K extends keyof Push>(channel: K, callback: (payload: Push[K]) => void): () => void;
}

declare global {
  interface Window {
    auphere: AuphereBridge;
  }
}

export const bridge: AuphereBridge = window.auphere;
