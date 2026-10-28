import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";

import { AGENT, REF, REVIEW, fail, ok } from "./quality-fixtures";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/app/(console)/clients/[ref]/agents/quality-actions", () => ({ reviewAction: vi.fn() }));
vi.mock("@/app/(console)/clients/[ref]/agents/builder-actions", () => ({ decideProposalAction: vi.fn() }));

const { ReviewPanel } = await import("../review-panel");
type Actions = NonNullable<React.ComponentProps<typeof ReviewPanel>["actions"]>;

/**
 * Spec 047 (historia 8, T089; requisito 22) — la revisión: cada comprobación
 * con su resultado de verdad (sin «✓» fijos), cada hallazgo con «Bloquea» o
 * «Avisa» y su arreglo: un enlace, abrir el bloque o aplicar la propuesta.
 */

function screenWith(props: Partial<React.ComponentProps<typeof ReviewPanel>> = {}, actions: Partial<Actions> = {}) {
  const full: Actions = {
    load: vi.fn(async () => ok(REVIEW)),
    decide: vi.fn(async () => ok({ id: "p", status: "applied", draft_revision: 5 })),
    ...actions,
  };
  const onEdit = vi.fn();
  const onApplied = vi.fn();
  const view = render(
    <LocaleProvider locale="es">
      <ReviewPanel refId={REF} agentId={AGENT} canWrite onEdit={onEdit} onApplied={onApplied} actions={full} {...props} />
    </LocaleProvider>,
  );
  return { ...view, actions: full, onEdit, onApplied };
}

const finding = (text: string) => screen.getByText(text).closest("[data-slot=review-finding]") as HTMLElement;

beforeEach(() => toast.success.mockClear());

describe("la revisión (22.2, 22.3)", () => {
  it("cada comprobación dice su resultado real y cada hallazgo su gravedad, y pasa axe", async () => {
    const { container } = screenWith();
    const checks = await screen.findByRole("list", { name: "Comprobaciones" });
    const items = within(checks).getAllByRole("listitem");
    expect(items).toHaveLength(8);
    expect(within(checks).getByText(/Horario del negocio/)).toBeVisible();
    expect(items.filter((li) => li.dataset.ok === "true")).toHaveLength(4);
    expect(within(items[0]!).getByText("1 hallazgo")).toBeVisible();
    expect(within(items[2]!).getByText("Sin problemas")).toBeVisible();
    expect(within(finding("Contradice la ficha: horario del domingo.")).getByText("Avisa")).toBeVisible();
    expect(within(finding("Cita una herramienta que no existe: reservas.borrar.")).getByText("Bloquea")).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("cada arreglo lleva a su sitio, abre el bloque o aplica la propuesta", async () => {
    const user = userEvent.setup();
    const { actions, onEdit, onApplied } = screenWith();
    await screen.findByRole("list", { name: "Hallazgos" });
    expect(within(finding("La habilidad Reservas necesita AgendaPro y no está conectada.")).getByRole("link", { name: "Ir a Conectores" })).toHaveAttribute(
      "href",
      `/clients/${REF}/integrations`,
    );
    expect(within(finding("El servicio Tinte no tiene precio.")).getByRole("link", { name: "Ir a Servicios" })).toHaveAttribute(
      "href",
      `/clients/${REF}/business#business-services`,
    );
    await user.click(within(finding("Contradice la ficha: horario del domingo.")).getByRole("button", { name: "Arreglar en el borrador" }));
    expect(onEdit).toHaveBeenCalledWith("/instructions/sections/0/body");
    await user.click(screen.getByRole("button", { name: "Aplicar el arreglo" }));
    expect(actions.decide).toHaveBeenCalledWith({ ref: REF, agent: AGENT, proposal: "88888888-8888-4888-8888-888888888888", decision: "apply" });
    await waitFor(() => expect(onApplied).toHaveBeenCalled());
  });

  it("quien solo lee ve los hallazgos y sus enlaces, sin aplicar ni editar", async () => {
    screenWith({ canWrite: false });
    await screen.findByRole("list", { name: "Hallazgos" });
    expect(screen.getByRole("link", { name: "Ir a Conectores" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Aplicar el arreglo" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Arreglar en el borrador" })).toBeNull();
  });

  it("se vuelve a leer cuando cambia el borrador, y dice si falló", async () => {
    const load = vi.fn<Actions["load"]>().mockResolvedValueOnce(ok(REVIEW)).mockResolvedValueOnce(fail(500));
    const { rerender } = screenWith({}, { load });
    await screen.findByRole("list", { name: "Hallazgos" });
    rerender(
      <LocaleProvider locale="es">
        <ReviewPanel refId={REF} agentId={AGENT} canWrite refreshKey={1} actions={{ load, decide: vi.fn() }} />
      </LocaleProvider>,
    );
    expect(await screen.findByText("No se pudo revisar.")).toBeVisible();
    expect(load).toHaveBeenCalledTimes(2);
  });
});
