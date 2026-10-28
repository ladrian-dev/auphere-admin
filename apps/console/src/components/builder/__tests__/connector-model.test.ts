import { describe, expect, it } from "vitest";

import { t as translate } from "@/i18n/messages";
import type { AgentSpec } from "@/lib/backend/builder-types";

import {
  agentConnectorsHref,
  apiSettingProblems,
  authKindLabel,
  categoriesOf,
  connectionHref,
  filterConnectors,
  rowActions,
  rowState,
  settingFields,
  settingLabel,
  settingProblems,
  settingValues,
  settingsFromValues,
  settingsSummary,
  skillsUsing,
} from "../connector-model";
import { COBRO_SCHEMA, CONN_WOO, REF, AGENT, catalog, connector } from "./connector-fixtures";

const t = (key: Parameters<typeof translate>[1], vars?: Record<string, string | number>) => translate("es", key, vars);

/**
 * Spec 047 (historia 21; T129) — lo que la sección Conectores y la página de
 * cada conexión deciden sin pintar: el estado de cada fila, sus acciones, el
 * filtro del catálogo y los ajustes declarados en el catálogo (36.2).
 */
describe("los conectores · el estado y las acciones de cada fila", () => {
  it("sin conectar, conectado con o sin uso, y con la conexión rota", () => {
    const [woo, gcal, cobro, hubspot] = catalog();
    expect(rowState(woo!)).toBe("on");
    expect(rowState(gcal!)).toBe("not_connected");
    expect(rowState(cobro!)).toBe("off");
    expect(rowState(hubspot!)).toBe("other");
    expect(rowState(connector({ connection: { id: CONN_WOO, status: "disconnected", last_checked_at: null } }))).toBe("not_connected");
  });

  it("cada fila trae lo suyo, la principal primero, y quien solo lee solo ve la página", () => {
    const [woo, gcal, cobro, hubspot] = catalog();
    expect(rowActions(woo!, true)).toEqual(["page", "settings", "remove"]);
    expect(rowActions(gcal!, true)).toEqual(["connect"]);
    expect(rowActions(cobro!, true)).toEqual(["page"]);
    expect(rowActions(hubspot!, true)).toEqual(["reconnect", "page"]);
    expect(rowActions(connector({ connection: { id: CONN_WOO, status: "pending", last_checked_at: null } }), true)).toEqual(["connect", "page"]);
    expect(rowActions(connector({ connection: { id: CONN_WOO, status: "paused", last_checked_at: null } }), true)).toEqual(["page"]);
    expect(rowActions(woo!, false)).toEqual(["page"]);
    expect(rowActions(gcal!, false)).toEqual([]);
  });

  it("filtra por nombre y por categoría sin cambiar el orden de la API, y nombra lo que no conoce como «El resto»", () => {
    const list = [...catalog(), connector({ slug: "rara", name: "Rara", category: "weird" })];
    expect(categoriesOf(list)).toEqual(["ecommerce", "calendar", "billing", "crm", "other"]);
    expect(filterConnectors(list, { q: "goo", category: null }).map((c) => c.slug)).toEqual(["googlecalendar"]);
    expect(filterConnectors(list, { q: "", category: "other" }).map((c) => c.slug)).toEqual(["rara"]);
    expect(filterConnectors(list, { q: "  ", category: null })).toHaveLength(5);
    expect(authKindLabel(t, "oauth_composio")).toBe("Se autoriza con la cuenta del servicio");
    expect(authKindLabel(t, "algo_nuevo")).toBe("Se autoriza desde el servicio");
  });

  it("las direcciones: la página de la conexión sabe volver al agente", () => {
    expect(connectionHref(REF, CONN_WOO, AGENT)).toBe(`/clients/${REF}/integrations/${CONN_WOO}?agent=${AGENT}`);
    expect(connectionHref(REF, CONN_WOO)).toBe(`/clients/${REF}/integrations/${CONN_WOO}`);
    expect(agentConnectorsHref(REF, AGENT)).toBe(`/clients/${REF}/agents/${AGENT}?tab=integrations`);
  });

  it("antes de quitarlo, las habilidades del borrador que lo declaran", () => {
    const spec = { skills: [{ key: "reservas.create", enabled: true, integration: "woocommerce" }, { key: "faq", enabled: true }] } as unknown as AgentSpec;
    expect(skillsUsing(spec, "woocommerce").map((s) => s.key)).toEqual(["reservas.create"]);
    expect(skillsUsing(null, "woocommerce")).toEqual([]);
  });
});

describe("los conectores · los ajustes declarados (36.2)", () => {
  const fields = settingFields(COBRO_SCHEMA);

  it("aplana el esquema con sus grupos y nombra cada campo con palabras", () => {
    expect(fields.map((f) => [f.path, f.kind, f.group])).toEqual([
      ["business_uuid", "text", null],
      ["reminders.enabled", "boolean", "reminders"],
      ["reminders.hour_local", "integer", "reminders"],
    ]);
    expect(settingLabel(t, "amigable_cobro", "reminders.hour_local")).toBe("Hora del envío, en la hora del negocio");
    expect(settingLabel(t, "nuevo", "calendar_id")).toBe("Calendar id");
    expect(settingLabel(t, "nuevo", "calendar_id", "Calendario")).toBe("Calendario");
  });

  it("lee lo guardado, lo valida y lo vuelve a escribir con sus grupos, sin mandar lo vacío", () => {
    const values = settingValues(fields, { business_uuid: "abc", reminders: { enabled: true, hour_local: 9 } });
    expect(values).toEqual({ business_uuid: "abc", "reminders.enabled": true, "reminders.hour_local": "9" });
    expect(settingProblems(fields, { ...values, "reminders.hour_local": "25" })).toEqual({ "reminders.hour_local": "integer" });
    expect(settingProblems(fields, { ...values, "reminders.hour_local": "9,5" })).toEqual({ "reminders.hour_local": "integer" });
    expect(settingsFromValues(fields, { ...values, business_uuid: " " })).toEqual({ reminders: { enabled: true, hour_local: 9 } });
    const url = settingFields({ type: "object", properties: { store_url: { type: "string", format: "uri", pattern: "^https://" } } });
    expect(settingProblems(url, { store_url: "http://tienda" })).toEqual({ store_url: "https" });
  });

  it("lo que la API marca vuelve a su campo, y el resumen se lee de un vistazo", () => {
    expect(apiSettingProblems({ errors: [{ field: "reminders.hour_local", message: "25 is greater than 23" }, { field: null }] })).toEqual({
      "reminders.hour_local": "invalid",
    });
    expect(apiSettingProblems(undefined)).toEqual({});
    expect(settingsSummary(t, "amigable_cobro", fields, { business_uuid: "abc", reminders: { enabled: false } })).toEqual([
      "Identificador del negocio: abc",
      "Enviar recordatorios: No",
    ]);
  });
});
