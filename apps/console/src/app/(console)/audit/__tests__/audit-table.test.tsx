import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { AuditEntry } from "@/lib/backend";

vi.mock("next/navigation", () => ({ usePathname: () => "/audit", useSearchParams: () => new URLSearchParams("actor=old") }));

const { AuditTable } = await import("../audit-table");

/**
 * Spec 047 (T164, requisito 49.1): cada fila de Auditoría dice desde dónde se
 * hizo (la web y la app, no la consola), marca lo sensible y, si la API juntó
 * filas iguales, «{n} más como esta» las trae sin juntar (`group=false`).
 */
function entry(over: Partial<AuditEntry> = {}): AuditEntry {
  return {
    id: "00000000-0000-4000-8000-000000000001",
    at: "2026-10-27T15:04:00Z",
    actor: "ana@ladrian.studio",
    actor_kind: "person",
    action: "client.bag.assign",
    category: "money",
    severity: "info",
    target: "client:flor",
    external_client_ref: "flor-y-encanto",
    client_name: "Flor y Encanto",
    summary: "ana@ladrian.studio asignó 20,00 USD a Flor y Encanto",
    origin: "console",
    sensitive: false,
    more_like_this: 0,
    ...over,
  };
}

const table = (items: AuditEntry[]) =>
  render(
    <LocaleProvider locale="es">
      <AuditTable first={{ items, next_cursor: null }} query={{}} people={{ "ana@ladrian.studio": "Ana" }} categories={{ money: "Dinero" }} />
    </LocaleProvider>,
  );

describe("AuditTable · lo que gana con la spec 047", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("el origen solo cuando no es la consola, y lo sensible marcado", () => {
    table([
      entry(),
      entry({ id: "00000000-0000-4000-8000-000000000002", origin: "lite_web", action: "client.business.edit", category: "clients", summary: "ana cambió el horario" }),
      entry({ id: "00000000-0000-4000-8000-000000000003", origin: "app", action: "client.delete", sensitive: true, severity: "critical", summary: "ana borró un cliente" }),
    ]);
    const origins = document.querySelectorAll("[data-slot=audit-origin]");
    expect([...origins].map((o) => o.textContent)).toEqual(["Desde la web", "Desde la app"]);
    const sensitive = document.querySelectorAll("[data-slot=audit-sensitive]");
    expect(sensitive).toHaveLength(1);
    expect(sensitive[0]!.textContent).toBe("Sensible");
  });

  it("«{n} más como esta» trae las filas sin juntar, de esa persona, acción, cliente y día", async () => {
    const user = userEvent.setup();
    const later = entry({ more_like_this: 2 });
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          items: [
            later,
            entry({ id: "00000000-0000-4000-8000-0000000000a2", at: "2026-10-27T14:00:00Z", summary: "ana@ladrian.studio asignó 10,00 USD a Flor y Encanto" }),
            entry({ id: "00000000-0000-4000-8000-0000000000a3", at: "2026-10-27T13:00:00Z", summary: "ana@ladrian.studio asignó 5,00 USD a Flor y Encanto" }),
          ],
          next_cursor: null,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    table([later]);
    await user.click(screen.getByRole("button", { name: "2 más como esta" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const url = new URL(String((fetchMock.mock.calls[0] as unknown[])[0]), "http://x");
    expect(url.pathname).toBe("/api/audit/page");
    expect(Object.fromEntries(url.searchParams)).toMatchObject({
      group: "false",
      person: "ana@ladrian.studio",
      action: "client.bag.assign",
      client: "flor-y-encanto",
      after: "2026-10-27T00:00:00Z",
      before: "2026-10-27T23:59:59Z",
    });
    const more = await screen.findByText(/asignó 10,00 USD/);
    expect(within(more.closest("[role=status]") as HTMLElement).getByText(/asignó 5,00 USD/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Ocultar" })).toHaveAttribute("aria-expanded", "true");
  });

  it("«Solo esta persona» filtra por `person` y quita el `actor` de antes", async () => {
    const user = userEvent.setup();
    table([entry()]);
    await user.click(screen.getByRole("button", { name: "Opciones de este registro" }));
    const item = await screen.findByRole("menuitem", { name: "Ver solo esta persona" });
    const href = item.getAttribute("href") ?? "";
    expect(href).toContain("person=ana%40ladrian.studio");
    expect(href).not.toContain("actor=");
  });
});
