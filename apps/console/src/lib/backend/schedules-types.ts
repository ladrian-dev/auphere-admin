/**
 * Rutinas de agente (spec 082, `contracts/console-api.md`).
 *
 * Una rutina es una instrucción que el agente de un cliente ejecuta a su hora,
 * y cuya respuesta lee el partner aquí. El estado que llega es **el efectivo**:
 * ya viene cruzado con el del agente, así que la pantalla lo pinta tal cual y
 * no tiene que deducir nada.
 *
 * Los días de la semana llegan con **lunes 0 y domingo 6**, la convención de
 * Python. En JavaScript el domingo es 0, así que la pantalla traduce al pintar
 * y al enviar: el desfase de un día no se nota hasta que alguien recibe el
 * informe el día que no era.
 */

export type Cadence = "daily" | "weekly" | "monthly" | "once";
export type ScheduleState = "active" | "paused" | "archived";

export type ScheduleWhen = {
  cadence: Cadence;
  local_time: string;
  weekdays: number[] | null;
  day_of_month: number | null;
  run_date: string | null;
};

export type ScheduleAgent = {
  id: string;
  name: string;
  state: string;
};

export type Schedule = {
  id: string;
  name: string;
  instruction: string;
  agent: ScheduleAgent;
  when: ScheduleWhen;
  next_run_at: string | null;
  state: ScheduleState;
  pause_reason: string | null;
  email: boolean;
  created_by: string;
  created_at: string;
  /** Sin dinero todavía: la partida llega con su propia tarea. */
  month: { runs: number };
};

export type ScheduleCounts = {
  all: number;
  active: number;
  paused: number;
  archived: number;
};

export type SchedulePage = {
  timezone: string;
  counts: ScheduleCounts;
  /** `null` hasta que exista la partida de Consumo: un cero sería mentira. */
  spend: null;
  schedules: Schedule[];
};

export type ScheduleBody = {
  agent_id: string;
  name: string;
  instruction: string;
  cadence: Cadence;
  local_time: string;
  weekdays?: number[] | null;
  day_of_month?: number | null;
  run_date?: string | null;
  email?: boolean;
};

export type SchedulePatchBody = Partial<Omit<ScheduleBody, "agent_id">>;

export type SchedulePreview = {
  next: string[];
  timezone: string;
};

/** Lo que salió de la bolsa del cliente: un precio, nunca un coste (C9). */
export type ScheduleMoney = { amount_micros: number; currency: string };

export type ScheduleRun = {
  id: string;
  scheduled_for: string;
  trigger: "schedule" | "manual";
  status: "running" | "done" | "partial" | "failed";
  attempts: number;
  duration_ms: number | null;
  /** `null` mientras no se haya cobrado: un cero diría que fue gratis. */
  spend: ScheduleMoney | null;
  answer: string | null;
  tools_used: string[];
  withheld: { tool: string; reason: string }[] | null;
  error_code: string | null;
  /** La de ese momento: editar la rutina no reescribe lo ya contestado. */
  instruction: string;
};

export type ScheduleRunPage = {
  runs: ScheduleRun[];
  next_cursor: string | null;
};

export type RunQueued = {
  run_id: string | null;
  job_id: string;
  schedule_id: string | null;
};
