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
export type Jobs = { jobs: string[]; models: Array<{ id: string; note: string; cost_label: string }> };

type Push = {
  "app:event": { stream_id: string; event: WireEvent };
  "app:stream.end": { stream_id: string; ok: boolean };
  "app:inbox.changed": { action_id: string; decision: string };
  "app:task.state": { task_id: string; state: string; cause: string };
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
