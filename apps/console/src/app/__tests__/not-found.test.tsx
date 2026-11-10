import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { type MessageKey, t as translate } from "@/i18n/messages";

/**
 * Spec 056 (requisito 14): una ruta que no existe.
 *
 * - Con sesión, la 404 sale dentro de la consola —su menú, el marco de cada
 *   persona— y lleva a su primer módulo.
 * - Sin sesión, ofrece «Entrar».
 * - El texto pasa por las traducciones y no dice si lo pedido existe.
 */
const state = vi.hoisted(() => ({
  resolution: { kind: "anonymous" } as unknown,
  principal: null as unknown,
  locale: "es" as "es" | "en",
  framed: null as unknown,
}));

vi.mock("@/lib/principal", async () => {
  const access = await vi.importActual<typeof import("@/lib/principal-access")>("@/lib/principal-access");
  return {
    resolvePrincipal: async () => state.resolution,
    requirePrincipal: async () => state.principal,
    firstModulePath: access.firstModulePath,
    firstPartnerModulePath: access.firstPartnerModulePath,
  };
});
vi.mock("@/i18n/server", () => ({
  getT: async () => ({ locale: state.locale, t: (key: MessageKey, vars?: Record<string, string | number>) => translate(state.locale, key, vars) }),
}));
vi.mock("@/components/shell/console-frame", () => ({
  ConsoleFrame: async ({ principal, children }: { principal: unknown; children: React.ReactNode }) => {
    state.framed = principal;
    return <div data-frame="">{children}</div>;
  },
}));

const RootNotFound = (await import("../not-found")).default;
const ConsoleNotFound = (await import("../(console)/not-found")).default;

const client = { kind: "client", role: "client", modules: ["inbox", "panel"], locale: "es", clientName: "Flor y Encanto" };
const partner = { kind: "partner", role: "owner", modules: ["clients", "usage"], locale: "en" };

async function paint(page: () => Promise<React.ReactElement>) {
  return render(await page());
}

describe("la 404", () => {
  beforeEach(() => {
    state.resolution = { kind: "anonymous" };
    state.principal = null;
    state.locale = "es";
    state.framed = null;
  });

  it("sin sesión ofrece «Entrar», sin decir si lo pedido existe", async () => {
    await paint(RootNotFound);
    expect(screen.getByRole("heading", { name: "Esta página no está" })).toBeInTheDocument();
    expect(screen.getByText("No existe o no es tuya.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Entrar" })).toHaveAttribute("href", "/login");
    expect(document.querySelector("[data-frame]")).toBeNull();
  });

  it("con sesión de cliente, dentro de su consola y hacia su primer módulo", async () => {
    state.resolution = { kind: "ok", principal: client };
    await paint(RootNotFound);
    expect(state.framed).toBe(client);
    expect(document.querySelector("[data-frame]")).not.toBeNull();
    expect(screen.getByRole("link", { name: "Ir al inicio" })).toHaveAttribute("href", "/inbox");
    expect(screen.queryByRole("link", { name: "Entrar" })).toBeNull();
  });

  it("con sesión de partner, en su idioma y hacia su primer módulo", async () => {
    state.resolution = { kind: "ok", principal: partner };
    state.locale = "en";
    await paint(RootNotFound);
    expect(screen.getByRole("heading", { name: "This page is not here" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to the start" })).toHaveAttribute("href", "/clients");
  });

  it("una sesión que no llega a la consola es como no tenerla", async () => {
    state.resolution = { kind: "no-membership", email: "x@y.test" };
    await paint(RootNotFound);
    expect(screen.getByRole("link", { name: "Entrar" })).toBeInTheDocument();
  });

  it("dentro de la consola (un `notFound()`), el menú ya está: solo el enlace", async () => {
    state.principal = client;
    await paint(ConsoleNotFound);
    expect(screen.getByRole("link", { name: "Ir al inicio" })).toHaveAttribute("href", "/inbox");
    expect(document.querySelector("[data-frame]")).toBeNull();
  });
});
