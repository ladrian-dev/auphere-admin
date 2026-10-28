import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { t as translate, type MessageKey } from "@/i18n/messages";
import { can } from "@/lib/permissions";

import { ROLE_CAPABILITIES, ROLE_ORDER, RolesTable } from "../roles-table";

const t = (key: MessageKey, vars?: Record<string, string | number>) => translate("es", key, vars);

/**
 * Spec 047 (T165; requisito 49.2): «Qué puede hacer cada rol» en Equipo. Sale del
 * mismo mapa de permisos que la consola y la API, así que no puede prometer lo que
 * un rol no puede hacer (49.6).
 */
describe("«Qué puede hacer cada rol»", () => {
  it("una columna por rol y una fila por cosa, con «Sí» o «No» también para lectores de pantalla", async () => {
    const { container } = render(
      <main>
        <RolesTable t={t} />
      </main>,
    );
    const table = screen.getByRole("table", { name: "Qué puede hacer cada rol" });
    const headers = within(table).getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["Qué se puede hacer", "Propietario", "Administrador", "Constructor", "Analista", "Facturación"]);
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(ROLE_CAPABILITIES.length);
    rows.forEach((row, i) => {
      const cap = ROLE_CAPABILITIES[i]!;
      const cells = within(row).getAllByRole("cell").map((c) => c.textContent);
      expect(cells).toEqual(ROLE_ORDER.map((role) => (can(role, cap.permission) ? "Sí" : "No")));
    });
    // El analista solo lee; facturación no toca nada operativo.
    const write = rows[ROLE_CAPABILITIES.findIndex((c) => c.key === "team.roles.cap.clientsWrite")]!;
    expect(within(write).getAllByRole("cell").map((c) => c.textContent)).toEqual(["Sí", "Sí", "Sí", "No", "No"]);
    expect(screen.getByText("Todo salvo facturación.")).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });
});
