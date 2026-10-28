import type { Call } from "../backend";
import { q } from "../backend";

import type {
  Activation,
  AffectedSkills,
  AgentConnector,
  ConnectBody,
  ConnectionPage,
  ConnectResult,
  ConnectorPermission,
  ConnectorSettings,
  ConnectConsent,
  Disconnected,
} from "./agent-connectors-types";

/**
 * Carril de los conectores de un agente (spec 047, T129; requisitos 35 y 36;
 * `contracts/console-api.md` §6): el catálogo del agente con su conexión y su
 * activación, conectar y activar en un paso, el permiso y los ajustes de cada
 * agente, quitarlo, y la página de cada conexión con «Reconectar» y
 * «Desconectar para todos». Se esparce en `backendFor`.
 *
 * Los errores llegan como `BackendError` con su código: `authorize_with_form`
 * (409, con `auth_kind` y `form`), `connection_not_authorized` (409),
 * `invalid_settings` (422, con `errors`), `settings_not_supported` (422),
 * `invalid_permission` (422), `unknown_integration` (404) y `confirm_required`
 * (409, con `affected`).
 */

export * from "./agent-connectors-types";

export function agentConnectorsApi(call: Call) {
  const enc = encodeURIComponent;
  const client = (ref: string) => `/console/clients/${enc(ref)}`;
  const agent = (ref: string, agentId: string) => `${client(ref)}/agents/${enc(agentId)}`;
  return {
    listAgentConnectors: (ref: string, agentId: string, filter: { q?: string; category?: string } = {}) =>
      call<AgentConnector[]>(`${agent(ref, agentId)}/integrations${q(filter)}`),
    connectConnector: (ref: string, body: ConnectBody) => call<ConnectResult>(`${client(ref)}/connections`, { method: "POST", body }),
    setActivation: (ref: string, agentId: string, slug: string, body: { permission: ConnectorPermission; settings: ConnectorSettings }) =>
      call<Activation>(`${agent(ref, agentId)}/activations/${enc(slug)}`, { method: "PUT", body }),
    removeActivation: (ref: string, agentId: string, slug: string) =>
      call<AffectedSkills>(`${agent(ref, agentId)}/activations/${enc(slug)}`, { method: "DELETE" }),
    getConnectionPage: (ref: string, connectionId: string) => call<ConnectionPage>(`${client(ref)}/connections/${enc(connectionId)}`),
    reconnectConnection: (ref: string, connectionId: string) =>
      call<ConnectConsent>(`${client(ref)}/connections/${enc(connectionId)}/reconnect`, { method: "POST" }),
    /** Sin `confirm`, `409 confirm_required` con lo afectado; con él, desconecta para todos. */
    disconnectConnection: (ref: string, connectionId: string, confirm: boolean) =>
      call<Disconnected>(`${client(ref)}/connections/${enc(connectionId)}/disconnect`, { method: "POST", body: { confirm } }),
  };
}
