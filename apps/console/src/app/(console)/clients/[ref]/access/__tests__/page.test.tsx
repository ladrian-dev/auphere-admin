import type * as React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { can } from "@/lib/permissions";

/**
 * Spec 056 (requisitos 3.1, 3.2 y 3.10; D4): la página «Acceso» de un cliente.
 * Es de owner y admin (`client_access:manage`). Para los demás roles no existe,
 * tampoco por la dirección: el mismo `notFound()` que un cliente ajeno.
 */
const state = vi.hoisted(() => ({ role: "owner" as string, version: "v2" as string }));
const api = vi.hoisted(() => ({ clientAccess: vi.fn() }));

class FakeBackendError extends Error {
  status: number;
  detail = "";
  code: string | null = null;
  info = undefined;
  constructor(status: number) {
    super(`backend ${status}`);
    this.status = status;
  }
}

vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
  redirect: (to: string) => {
    throw new Error(`NEXT_REDIRECT ${to}`);
  },
}));
vi.mock("@/lib/principal", async () => {
  const permissions = await vi.importActual<typeof import("@/lib/permissions")>("@/lib/permissions");
  return {
    requirePartnerPrincipal: async () => ({ kind: "partner", role: state.role, locale: "es", modules: ["clients"] }),
    can: permissions.can,
  };
});
vi.mock("@/lib/backend", () => ({ backendFor: () => api, BackendError: FakeBackendError }));
vi.mock("../../data", () => ({ getConsoleVersionCached: async () => state.version }));
vi.mock("@/i18n/server", () => ({ getT: async () => ({ locale: "es", t: (k: string) => k }) }));
vi.mock("@/components/clients/access/client-access-view", () => ({ ClientAccessView: () => null }));

const ClientAccessPage = (await import("../page")).default;

const ACCESS = { eligible: true, ineligible_reason: null, whatsapp_connected: true, enabled: true, modules: ["panel"], members: [], reservas: null };

async function open(ref = "flor") {
  return (await ClientAccessPage({ params: Promise.resolve({ ref }) })) as React.ReactElement<{ refId: string; initial: unknown }>;
}

beforeEach(() => {
  state.role = "owner";
  state.version = "v2";
  api.clientAccess.mockReset();
  api.clientAccess.mockResolvedValue(ACCESS);
});

describe("la página Acceso de un cliente", () => {
  it.each(["owner", "admin"])("%s la abre con el acceso leído", async (role) => {
    state.role = role;
    const el = await open();
    expect(el.props.refId).toBe("flor");
    expect(el.props.initial).toEqual(ACCESS);
    expect(api.clientAccess).toHaveBeenCalledWith("flor");
  });

  it.each(["builder", "analyst"])("para %s no existe: notFound, sin leer nada", async (role) => {
    // El permiso es el de la API: si cambia allí, esta lista cambia con él.
    expect(can(role as "builder", "client_access:manage")).toBe(false);
    state.role = role;
    await expect(open()).rejects.toThrow("NEXT_NOT_FOUND");
    expect(api.clientAccess).not.toHaveBeenCalled();
  });

  it("billing no ve clientes: va al inicio, como en el resto de la ficha", async () => {
    expect(can("billing", "client_access:manage")).toBe(false);
    state.role = "billing";
    await expect(open()).rejects.toThrow("NEXT_REDIRECT /");
    expect(api.clientAccess).not.toHaveBeenCalled();
  });

  it("un cliente ajeno o que no existe es el mismo notFound (3.10)", async () => {
    api.clientAccess.mockRejectedValueOnce(new FakeBackendError(404));
    await expect(open("de-otro")).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it("si la lectura falla, la página se pinta con las tarjetas en error", async () => {
    api.clientAccess.mockRejectedValueOnce(new FakeBackendError(503));
    const el = await open();
    expect(el.props.initial).toBeNull();
  });

  it("con la consola de antes vuelve al cliente", async () => {
    state.version = "v1";
    await expect(open()).rejects.toThrow("NEXT_REDIRECT /clients/flor");
  });
});
