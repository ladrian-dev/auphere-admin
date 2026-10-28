/**
 * Tipos puros de los conectores de un agente — spec 047, T129 (requisitos 35 y
 * 36; `contracts/console-api.md` §6). Reflejan `api/console/agent_integrations.py`:
 * la conexión es del cliente (una por servicio, con su cuenta) y la activación,
 * del agente (con su permiso y sus ajustes). Sin imports con efectos: valen para
 * componentes de cliente y para los tests. El cliente de la API es
 * `./agent-connectors.ts`.
 *
 * En la API se llaman `integrations` y `connections` (las rutas no cambian); en
 * pantalla son «Conectores» (`words.test.ts`).
 */

/** «Solo leer», «Preguntar antes de escribir» y «Leer y escribir» (35.5). */
export type ConnectorPermission = "read" | "ask_before_write" | "read_write";
export const CONNECTOR_PERMISSIONS: readonly ConnectorPermission[] = ["read", "ask_before_write", "read_write"];

/** Un esquema JSON de ajustes, tal como lo declara el catálogo (36.2). */
export type SettingsSchema = {
  type?: string;
  title?: string;
  description?: string;
  properties?: Record<string, SettingsSchema>;
  required?: string[];
  additionalProperties?: boolean;
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  format?: string;
  enum?: unknown[];
  default?: unknown;
};

export type ConnectorSettings = Record<string, unknown>;

/** La conexión del cliente con ese servicio: su id, su estado y cuándo se comprobó. */
export type ConnectionState = { id: string; status: string; last_checked_at: string | null };

export type Activation = { permission: ConnectorPermission; settings: ConnectorSettings };

/** Una fila del catálogo del agente (`GET …/agents/{id}/integrations`, 35.2). */
export type AgentConnector = {
  slug: string;
  name: string;
  category: string;
  /** La URL del logotipo en el catálogo; la consola lo sirve desde su origen. */
  logo: string | null;
  /** Cómo se autoriza: `oauth_composio`, `api_key`, `browser_credentials`… */
  auth_kind: string;
  /** La piden las habilidades del agente: va primero. */
  needed: boolean;
  connection: ConnectionState | null;
  activation: Activation | null;
  settings_schema: SettingsSchema | null;
};

/** `POST /connections`: autorizar y activar en un paso (35.3, 35.4). */
export type ConnectBody = { integration: string; agent_id?: string; permission?: ConnectorPermission };
/** Ya autorizada: se activó sin pedirla otra vez. */
export type ConnectDone = { status: "connected" | "activated"; connection_id: string };
/** Hay que autorizar en la ventana del proveedor (OAuth). */
export type ConnectConsent = { slug: string; signed_consent_url: string; expires_at: string };
export type ConnectResult = ConnectDone | ConnectConsent;

/** Un campo del formulario de credenciales del catálogo (`409 authorize_with_form`). */
export type ConnectFormField = { field: string; label?: string; placeholder?: string; secret?: boolean; required?: boolean };

/** `DELETE …/activations/{integration}`: lo que se queda sin el conector (35.7). */
export type AffectedSkills = { skills: string[]; procedures: string[] };

/** Un agente que usa la conexión, con su permiso y sus ajustes (36.1). */
export type ConnectionUser = { agent_id: string; name: string; permission: ConnectorPermission; settings: ConnectorSettings };

/** La página de un conector conectado (`GET /connections/{id}`, 36.1). */
export type ConnectionPage = {
  id: string;
  integration: string;
  name: string;
  logo: string | null;
  status: string;
  /** «Hay que volver a autorizar» (36.3). */
  needs_reauth: boolean;
  account: string | null;
  connected_at: string | null;
  last_checked_at: string | null;
  agents: ConnectionUser[];
  settings_schema: SettingsSchema | null;
};

/** «Desconectar para todos» (36.4): cada agente afectado y lo que pierde. */
export type DisconnectImpact = { agent_id: string; name: string; skills: string[]; procedures: string[] };
export type Disconnected = { status: "disconnected"; affected: DisconnectImpact[] };
