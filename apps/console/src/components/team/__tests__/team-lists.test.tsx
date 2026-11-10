import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/app/(console)/team/actions", () => ({
  changeRoleAction: vi.fn(),
  changeStatusAction: vi.fn(),
  removeMemberAction: vi.fn(),
  revokeInvitationAction: vi.fn(),
}));

import { LocaleProvider } from "@/i18n/client";
import type { Member, Team } from "@/lib/backend";

import { TeamLists } from "../team-lists";

/**
 * Spec 047 — Equipo como el prototipo «Consola de partners v2»: miembros e
 * invitaciones en tarjetas con su recuento, el propietario primero, cada fila
 * con el rol antes que el estado y la fecha, y las invitaciones con su baldosa.
 */
const member = (over: Partial<Member> = {}): Member => ({
  id: "m1",
  email: "andres@ladrian.studio",
  display_name: "Andrés Ruiz",
  role: "admin",
  status: "active",
  accepted_at: "2026-05-01T00:00:00Z",
  created_at: "2026-05-01T00:00:00Z",
  is_you: false,
  ...over,
});
const team: Team = {
  members: [
    member(),
    member({ id: "m2", email: "javier@ladrian.studio", display_name: "Javier Soto", role: "analyst", status: "suspended" }),
    member({ id: "m0", email: "luis@ladrian.studio", display_name: "Luis Matos", role: "owner", is_you: true }),
  ],
  invitations: [{ id: "i1", email: "contabilidad@ladrian.studio", role: "billing", status: "pending", expires_at: "2026-11-16T00:00:00Z", created_at: "2026-10-26T00:00:00Z" }],
};
const wrap = (t: Team) =>
  render(
    <LocaleProvider locale="es">
      <main>
        <h1>Equipo</h1>
        <TeamLists team={t} manage />
      </main>
    </LocaleProvider>,
  );

describe("Equipo · como el prototipo", () => {
  it("miembros en una tarjeta con su recuento y el propietario primero", async () => {
    const { container } = wrap(team);
    const members = screen.getByRole("region", { name: "Miembros" });
    expect(within(members).getByText("3")).toBeInTheDocument();
    const rows = within(members).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Luis Matos");
    expect(rows[0]).toHaveTextContent("(tú)");
    // El rol antes que el estado.
    const text = rows[1]!.textContent ?? "";
    expect(text.indexOf("Administrador")).toBeLessThan(text.indexOf("Activo"));
    expect(within(rows[2]!).getByText("Suspendido")).toBeInTheDocument();
    // En tu fila no hay «⋯».
    expect(within(rows[0]!).queryByRole("button")).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("invitaciones en su tarjeta, con baldosa, rol y caducidad, y «Revocar»", () => {
    wrap(team);
    const invitations = screen.getByRole("region", { name: "Invitaciones pendientes" });
    expect(within(invitations).getByText("1")).toBeInTheDocument();
    expect(within(invitations).getByText("contabilidad@ladrian.studio")).toBeInTheDocument();
    expect(within(invitations).getByText(/Facturación · Caduca/)).toBeInTheDocument();
    expect(within(invitations).getByRole("button", { name: "Revocar" })).toBeInTheDocument();
  });

  it("sin invitaciones, la tarjeta lo dice", () => {
    wrap({ ...team, invitations: [] });
    const invitations = screen.getByRole("region", { name: "Invitaciones pendientes" });
    expect(within(invitations).getByText("No hay invitaciones pendientes.")).toBeInTheDocument();
  });
});
