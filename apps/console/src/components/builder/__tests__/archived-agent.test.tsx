import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";

import { COBROS, REF, header, ok } from "./life-fixtures";

const nav = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname: () => "/", useRouter: () => nav }));
const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/app/(console)/clients/[ref]/agents/life-actions", () => ({}));

const { ArchivedAgent } = await import("../archived-agent");

/** Spec 047 (T124; requisito 28.2) — un agente archivado: solo lectura y «Restaurar», que lo devuelve en pausa. */
describe("un agente archivado", () => {
  const archived = header({ lifecycle: "archived", visible_state: { code: "archived", tone: "muted", reason: null }, allowed: ["restore"] });

  it("se ve en solo lectura y se restaura", async () => {
    const user = userEvent.setup();
    const restore = vi.fn(async () => ok(header({ lifecycle: "paused" })));
    const { container } = render(
      <LocaleProvider locale="es">
        <ArchivedAgent refId={REF} header={archived} actions={{ restore }} />
      </LocaleProvider>,
    );
    expect(screen.getByRole("heading", { name: "Cobros" })).toBeVisible();
    expect(screen.getByText("Archivado")).toBeVisible();
    expect(screen.getByText(/Restaurarlo lo devuelve en pausa/)).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Restaurar" }));
    expect(restore).toHaveBeenCalledWith({ ref: REF, agent: COBROS });
    await waitFor(() => expect(nav.refresh).toHaveBeenCalled());
    expect(toast.success).toHaveBeenCalledWith("Cobros vuelve, en pausa. Reanúdalo cuando quieras que responda.");
  });

  it("sin permiso, no hay «Restaurar» y lo dice", () => {
    render(
      <LocaleProvider locale="es">
        <ArchivedAgent refId={REF} header={{ ...archived, allowed: [] }} actions={{ restore: vi.fn() }} />
      </LocaleProvider>,
    );
    expect(screen.queryByRole("button", { name: "Restaurar" })).toBeNull();
    expect(screen.getByText(/Solo alguien que pueda editar agentes/)).toBeVisible();
  });
});
