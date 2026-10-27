import { describe, expect, it } from "vitest";

import { crumbsFor } from "../crumbs-v2";

/**
 * Spec 047 (R47.1, R47.12; `01` §1.4): las migas de cada pantalla. El último
 * elemento no es un enlace (`href: null`). Los nombres de un cliente, de un
 * agente o de un canal los anuncia su página (`<CrumbName>`); mientras no
 * llegan, las migas usan la referencia del cliente o una palabra genérica,
 * nunca un identificador.
 */
const NAMES = { flor: "Flor y Encanto", "a-1": "Recepción", "ch-9": "+34 611 20 48 93" };

describe("crumbsFor", () => {
  it("las pantallas de cuenta y de operación son una sola miga", () => {
    expect(crumbsFor("/", {})).toEqual([{ href: null, label: { key: "nav.home" } }]);
    expect(crumbsFor("/clients", {})).toEqual([{ href: null, label: { key: "nav.clients" } }]);
    expect(crumbsFor("/usage", {})).toEqual([{ href: null, label: { key: "nav.usage" } }]);
    expect(crumbsFor("/keys", {})).toEqual([{ href: null, label: { key: "nav.keys" } }]);
    expect(crumbsFor("/notifications", {})).toEqual([{ href: null, label: { key: "notif.title" } }]);
  });

  it("Alertas de consumo cuelga de Consumo", () => {
    expect(crumbsFor("/usage/alerts", {})).toEqual([
      { href: "/usage", label: { key: "nav.usage" } },
      { href: null, label: { key: "shell.crumbs.usageAlerts" } },
    ]);
  });

  it("un cliente: Clientes › {cliente}, también en sus pestañas", () => {
    const expected = [
      { href: "/clients", label: { key: "nav.clients" } },
      { href: null, label: { text: "Flor y Encanto" } },
    ];
    expect(crumbsFor("/clients/flor", NAMES)).toEqual(expected);
    expect(crumbsFor("/clients/flor/business", NAMES)).toEqual(expected);
    expect(crumbsFor("/clients/flor/agents", NAMES)).toEqual(expected);
  });

  it("un agente: Clientes › {cliente} › {agente}, y el cliente lleva a su pestaña Agentes", () => {
    expect(crumbsFor("/clients/flor/agents/a-1", NAMES)).toEqual([
      { href: "/clients", label: { key: "nav.clients" } },
      { href: "/clients/flor/agents", label: { text: "Flor y Encanto" } },
      { href: null, label: { text: "Recepción" } },
    ]);
  });

  it("la página de un canal cuelga de su agente", () => {
    expect(crumbsFor("/clients/flor/agents/a-1/channels/ch-9", NAMES)).toEqual([
      { href: "/clients", label: { key: "nav.clients" } },
      { href: "/clients/flor/agents", label: { text: "Flor y Encanto" } },
      { href: "/clients/flor/agents/a-1", label: { text: "Recepción" } },
      { href: null, label: { key: "shell.crumbs.channel", vars: { name: "+34 611 20 48 93" } } },
    ]);
  });

  it("sin nombre todavía: la referencia del cliente y una palabra para el agente, nunca un uuid", () => {
    const crumbs = crumbsFor("/clients/caf%C3%A9-origen/agents/0b7c2e4e-1111-4c1c-9d1f-3f0f0f0f0f0f", {});
    expect(crumbs[1]).toEqual({ href: "/clients/caf%C3%A9-origen/agents", label: { text: "café-origen" } });
    expect(crumbs[2]).toEqual({ href: null, label: { key: "shell.crumbs.agent" } });
  });

  it("el alta de un cliente de la consola de hoy cuelga de Clientes", () => {
    expect(crumbsFor("/clients/new", {})).toEqual([
      { href: "/clients", label: { key: "nav.clients" } },
      { href: null, label: { key: "shell.crumbs.newClient" } },
    ]);
  });

  it("una ruta desconocida no inventa migas", () => {
    expect(crumbsFor("/algo/raro", {})).toEqual([]);
  });
});
