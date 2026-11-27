import type { Call } from "../backend";
import { q } from "../backend";

import type {
  RunQueued,
  Schedule,
  SchedulePage,
  SchedulePatchBody,
  SchedulePreview,
  ScheduleBody,
  ScheduleRunPage,
  ScheduleState,
} from "./schedules-types";

/**
 * Carril de rutinas (spec 082, `contracts/console-api.md`): la lista con sus
 * filtros, el alta, las próximas ejecuciones antes de guardar, los cambios y
 * las cuatro transiciones.
 *
 * **No hay borrar**, y no es un olvido: una rutina se archiva, que es la regla
 * de la casa. La ruta del detalle responde 405 a quien lo intente.
 *
 * El cliente sale del `ref`: ningún cuerpo lleva `tenant_id`. Los errores
 * llegan como `BackendError` con su código, que es el contrato: `name_required`,
 * `instruction_required`, `weekdays_required`, `day_of_month_out_of_range`,
 * `run_date_required`, `run_date_in_the_past`, `limit_reached` (409) y
 * `bag_empty` (409) al ejecutar.
 */

export * from "./schedules-types";

export function schedulesApi(call: Call) {
  const enc = encodeURIComponent;
  const base = (ref: string) => `/console/clients/${enc(ref)}/schedules`;
  const one = (ref: string, id: string) => `${base(ref)}/${enc(id)}`;
  return {
    listSchedules: (ref: string, filters?: { agent?: string; state?: ScheduleState }) =>
      call<SchedulePage>(`${base(ref)}${q({ agent: filters?.agent, state: filters?.state })}`),
    getSchedule: (ref: string, id: string) => call<Schedule>(one(ref, id)),
    createSchedule: (ref: string, body: ScheduleBody) =>
      call<Schedule>(base(ref), { method: "POST", body }),
    patchSchedule: (ref: string, id: string, body: SchedulePatchBody) =>
      call<Schedule>(one(ref, id), { method: "PATCH", body }),
    previewSchedule: (
      ref: string,
      body: Pick<ScheduleBody, "cadence" | "local_time" | "weekdays" | "day_of_month" | "run_date">,
    ) => call<SchedulePreview>(`${base(ref)}/preview`, { method: "POST", body }),
    pauseSchedule: (ref: string, id: string) =>
      call<Schedule>(`${one(ref, id)}/pause`, { method: "POST" }),
    resumeSchedule: (ref: string, id: string) =>
      call<Schedule>(`${one(ref, id)}/resume`, { method: "POST" }),
    archiveSchedule: (ref: string, id: string) =>
      call<Schedule>(`${one(ref, id)}/archive`, { method: "POST" }),
    restoreSchedule: (ref: string, id: string) =>
      call<Schedule>(`${one(ref, id)}/restore`, { method: "POST" }),
    listRuns: (ref: string, id: string, page?: { limit?: number; cursor?: string }) =>
      call<ScheduleRunPage>(
        `${one(ref, id)}/runs${q({ limit: page?.limit?.toString(), cursor: page?.cursor })}`,
      ),
    runSchedule: (ref: string, id: string) =>
      call<RunQueued>(`${one(ref, id)}/run`, { method: "POST" }),
    trySchedule: (ref: string, agentId: string, instruction: string) =>
      call<RunQueued>(`/console/clients/${enc(ref)}/agents/${enc(agentId)}/schedules/try`, {
        method: "POST",
        body: { instruction },
      }),
  };
}
