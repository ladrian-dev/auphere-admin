/**
 * Lane ``models`` (spec 016, US4): the closed catalogue the partner may pick
 * from, with its relative cost in credits, and the client's ``respond``
 * binding. ``partner_id``/``tenant_id`` never travel.
 */
import type { Call } from "../backend";

export type ModelWeights = { input: number; cache_read: number; output: number };

export type ConsoleModel = {
  model_id: string;
  display_name: string;
  /** Output weight normalised to the cheapest of the list: «×N créditos». */
  relative_cost: number;
  weights: ModelWeights;
};

export type ClientModel = {
  client_ref: string;
  role: string;
  model_id: string | null;
  display_name: string | null;
  is_bound: boolean;
  /** ``false`` when the plan no longer includes the bound model (R5.3). */
  allowed: boolean;
  /** What answers without a binding (or with one the plan no longer allows). */
  fallback_model_id: string;
  fallback_display_name: string;
};

export function modelsApi(call: Call) {
  const enc = encodeURIComponent;
  return {
    listModels: () => call<ConsoleModel[]>("/console/models"),
    getClientModel: (ref: string) => call<ClientModel>(`/console/clients/${enc(ref)}/model`),
    setClientModel: (ref: string, model_id: string) =>
      call<ClientModel>(`/console/clients/${enc(ref)}/model`, { method: "PUT", body: { model_id } }),
  };
}
