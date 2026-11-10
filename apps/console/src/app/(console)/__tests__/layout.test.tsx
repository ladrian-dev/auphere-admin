import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { type MessageKey, t as translate } from "@/i18n/messages";

/**
 * Spec 047 (R55.2, T004): la consola nueva se activa partner a partner. El
 * marco lo elige `layout.tsx` con `console_version` de `GET /console/me`:
 * `v2` pinta el marco nuevo; `v1`, la ausencia del campo o cualquier fallo
 * al leerlo pintan la consola de hoy. Un partner sin activar nunca ve la nueva
 * por un error, y una persona de cliente sigue en su consola (spec 030).
 */
const state = vi.hoisted(() => ({
  principal: null as unknown,
  me: vi.fn(),
  cookie: null as string | null,
  v2Props: null as Record<string, unknown> | null,
}));

vi.mock("@/lib/principal", () => ({
  requirePrincipal: async () => state.principal,
  firstModulePath: () => "/",
}));
vi.mock("next/headers", () => ({
  headers: async () => new Headers({ "x-pathname": "/" }),
  cookies: async () => ({ get: (name: string) => (name === "nexus-console.nav" && state.cookie ? { name, value: state.cookie } : undefined) }),
}));
vi.mock("next/navigation", () => ({ redirect: vi.fn() }));
vi.mock("@/i18n/server", () => ({
  getT: async () => ({ locale: "es", t: (key: MessageKey, vars?: Record<string, string | number>) => translate("es", key, vars) }),
}));
vi.mock("@/lib/backend", () => ({ backendFor: () => ({ me: state.me }) }));
vi.mock("@/components/shell/console-shell-v1", () => ({
  ConsoleShellV1: ({ children }: { children: React.ReactNode }) => <div data-shell="v1">{children}</div>,
}));
vi.mock("@/components/shell/console-shell-v2", () => ({
  ConsoleShellV2: (props: Record<string, unknown> & { children: React.ReactNode }) => {
    state.v2Props = props;
    return <div data-shell="v2">{props.children}</div>;
  },
}));
vi.mock("@/components/companion/companion-launcher", () => ({ CompanionLauncher: () => <span data-companion="" /> }));

const ConsoleLayout = (await import("../layout")).default;

const partner = (modules: string[] = ["panel", "clients", "usage"]) => ({
  kind: "partner",
  role: "owner",
  modules,
  locale: "es",
  userId: "u-1",
  name: "Luis Matos",
  email: "luis@ladrian.studio",
  partnerName: "Ladrian Studio",
  partnerSlug: "ladrian",
});

async function paint() {
  return render(await ConsoleLayout({ children: <p>contenido</p> }));
}
const shell = () => document.querySelector("[data-shell]")?.getAttribute("data-shell");

describe("(console)/layout — qué marco ve cada partner", () => {
  beforeEach(() => {
    state.principal = partner();
    state.me.mockReset();
    state.cookie = null;
    state.v2Props = null;
  });

  it("un partner activado ve el marco nuevo", async () => {
    state.me.mockResolvedValue({ console_version: "v2" });
    await paint();
    expect(shell()).toBe("v2");
    expect(screen.getByText("contenido")).toBeInTheDocument();
    expect(state.me).toHaveBeenCalledTimes(1);
  });

  it("un partner sin activar ve la consola de hoy", async () => {
    state.me.mockResolvedValue({ console_version: "v1" });
    await paint();
    expect(shell()).toBe("v1");
  });

  it("sin el campo (una API de antes) es la consola de hoy", async () => {
    state.me.mockResolvedValue({ partner_id: "p-1" });
    await paint();
    expect(shell()).toBe("v1");
  });

  it("si `/console/me` falla, la consola de hoy: nunca la nueva por un error", async () => {
    state.me.mockRejectedValue(new Error("502"));
    await paint();
    expect(shell()).toBe("v1");
  });

  it("una persona de cliente sigue en su consola y no se pregunta la versión", async () => {
    state.principal = { kind: "client", role: "client", modules: ["panel"], locale: "es", clientName: "Flor y Encanto", name: "Valeria", email: "v@x.test" };
    await paint();
    expect(shell()).toBe("v1");
    expect(state.me).not.toHaveBeenCalled();
  });

  it("el marco nuevo recuerda el menú plegado y recibe al Companion si el partner lo tiene", async () => {
    state.me.mockResolvedValue({ console_version: "v2" });
    state.cookie = "collapsed";
    state.principal = partner(["panel", "clients", "companion"]);
    await paint();
    expect(state.v2Props).toMatchObject({
      defaultCollapsed: true,
      who: { role: "owner", modules: ["panel", "clients", "companion"] },
      user: { name: "Luis Matos", email: "luis@ladrian.studio" },
      partnerName: "Ladrian Studio",
    });
    expect(state.v2Props?.companion).toBeTruthy();
  });
});
