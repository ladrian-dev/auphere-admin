import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { BusinessRecord, Suggestion } from "@/lib/backend/client-records";

import { REF, fail, ok } from "./life-fixtures";
import { job, noWait } from "./quality-fixtures";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/app/(console)/clients/[ref]/business/client-builder-actions", () => ({}));
vi.mock("@/app/(console)/clients/[ref]/client-v2-actions", () => ({}));

const { ClientBuilderPanel } = await import("../client-builder-panel");
const { proposedAgentHref } = await import("../life-model");
type Actions = NonNullable<React.ComponentProps<typeof ClientBuilderPanel>["actions"]>;

/**
 * Spec 047 (historia 18, T098; requisito 18) — «Completar con el constructor»:
 * propone políticas y preguntas frecuentes marcadas «Sugerido · confirma», que
 * se aceptan, editan o descartan una a una, y agentes que no se crean solos.
 */

const suggestion = (over: Partial<Suggestion>): Suggestion => ({
  id: "99999999-9999-4999-8999-000000000001",
  pointer: "/policies/cancellation",
  section: "policies",
  proposed_value: "Se puede cancelar sin coste hasta 24 horas antes.",
  current_value: null,
  source: "builder",
  source_url: null,
  translated_from: null,
  created_at: "2026-10-27T10:00:00Z",
  ...over,
});
const POLICY = suggestion({});
const FAQ = suggestion({
  id: "99999999-9999-4999-8999-000000000002",
  pointer: "/faqs/-",
  section: "faqs",
  proposed_value: { q: "¿Aceptáis tarjeta?", a: "Sí, todas las tarjetas.", suggested: true },
});
const RECORD = { suggestions: [POLICY, FAQ, suggestion({ id: "99999999-9999-4999-8999-000000000003", source: "web" })] } as unknown as BusinessRecord;

function panelWith(props: Partial<React.ComponentProps<typeof ClientBuilderPanel>> = {}, actions: Partial<Actions> = {}) {
  const full: Actions = {
    start: vi.fn(async () => ok({ job_id: "66666666-6666-4666-8666-666666666666" })),
    poll: vi.fn(async () =>
      ok(
        job({
          kind: "client_builder",
          status: "done",
          result: {
            sections: { policies: [POLICY.id], faqs: [FAQ.id] },
            agents: [{ name: "Recepción", description: "Atiende las citas por WhatsApp y recuerda la política de cancelación." }],
            discarded: ["«¿Dónde estáis?»: ya está entre las preguntas frecuentes."],
          },
        }),
      ),
    ),
    load: vi.fn(async () => ok(RECORD)),
    decide: vi.fn(async () => ok({ decision: "accept" })),
    ...actions,
  };
  const view = render(
    <LocaleProvider locale="es">
      <ClientBuilderPanel refId={REF} canWrite suggestions={[]} actions={full} wait={noWait} {...props} />
    </LocaleProvider>,
  );
  return { ...view, actions: full };
}

const item = (title: string) => screen.getByRole("listitem", { name: title }) as HTMLElement;

beforeEach(() => toast.success.mockClear());

describe("«Completar con el constructor» (18.1–18.4)", () => {
  it("propone por secciones, «Sugerido · confirma», y agentes sin crearlos", async () => {
    const user = userEvent.setup();
    const { actions, container } = panelWith();
    await user.click(screen.getByRole("button", { name: "Completar con el constructor" }));
    expect(actions.start).toHaveBeenCalledWith({ ref: REF });
    expect(await screen.findByText("Listo: revisa lo que propone.")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Políticas" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Preguntas frecuentes" })).toBeVisible();
    expect(within(item("Cancelación")).getByText("Sugerido · confirma")).toBeVisible();
    expect(within(item("¿Aceptáis tarjeta?")).getByText("Sí, todas las tarjetas.")).toBeVisible();
    // Lo leído de la web no es del constructor: no sale aquí.
    expect(screen.getAllByRole("listitem", { name: /Cancelación/ })).toHaveLength(1);
    expect(screen.getByText(/ya está entre las preguntas frecuentes/)).toBeVisible();
    const create = screen.getByRole("link", { name: "Crear el agente Recepción" });
    expect(create).toHaveAttribute("href", proposedAgentHref(REF, { name: "Recepción", description: "Atiende las citas por WhatsApp y recuerda la política de cancelación." }));
    expect(create.getAttribute("href")).toMatch(/^\/clients\/barberia-cultor\/agents\/new\?name=Recepci%C3%B3n&description=/);
    expect(await axeViolations(container)).toEqual([]);
  });

  it("cada dato se acepta, se edita o se descarta (18.2)", async () => {
    const user = userEvent.setup();
    const { actions } = panelWith({ suggestions: [POLICY, FAQ] });
    await user.click(within(item("Cancelación")).getByRole("button", { name: "Aceptar Cancelación" }));
    expect(actions.decide).toHaveBeenCalledWith({ ref: REF, id: POLICY.id, decision: "accept" });
    await waitFor(() => expect(screen.queryByRole("listitem", { name: "Cancelación" })).toBeNull());

    const faq = item("¿Aceptáis tarjeta?");
    await user.click(within(faq).getByRole("button", { name: "Editar ¿Aceptáis tarjeta?" }));
    const answer = within(faq).getByRole("textbox", { name: /Respuesta/ });
    await user.clear(answer);
    await user.type(answer, "Sí, y también Bizum.");
    await user.click(within(faq).getByRole("button", { name: "Guardar en la ficha" }));
    expect(actions.decide).toHaveBeenLastCalledWith({ ref: REF, id: FAQ.id, decision: "edit", value: { q: "¿Aceptáis tarjeta?", a: "Sí, y también Bizum." } });
  });

  it("descartar, y lo que dice si otra persona ya lo decidió", async () => {
    const user = userEvent.setup();
    const decide = vi.fn<Actions["decide"]>().mockResolvedValueOnce(fail(409, "already_decided")).mockResolvedValueOnce(ok({ decision: "discard" }));
    panelWith({ suggestions: [POLICY] }, { decide });
    await user.click(screen.getByRole("button", { name: "Descartar Cancelación" }));
    expect(await screen.findByText("Ya lo decidió otra persona.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Descartar Cancelación" }));
    expect(decide).toHaveBeenLastCalledWith({ ref: REF, id: POLICY.id, decision: "discard" });
  });

  it("quien solo lee ve lo pendiente sin botones, y nada si no hay nada", () => {
    const { unmount } = panelWith({ canWrite: false, suggestions: [POLICY] });
    expect(screen.getByText("Sugerido · confirma")).toBeVisible();
    expect(screen.queryByRole("button")).toBeNull();
    unmount();
    const { container } = panelWith({ canWrite: false, suggestions: [] });
    expect(container.querySelector("[data-slot=client-builder]")).toBeNull();
  });

  it("si el constructor no responde, lo dice", async () => {
    const user = userEvent.setup();
    panelWith({}, { poll: vi.fn(async () => ok(job({ kind: "client_builder", status: "failed", error_code: "builder_unavailable" }))) });
    await user.click(screen.getByRole("button", { name: "Completar con el constructor" }));
    expect(await screen.findByText("El constructor no ha respondido. Inténtalo de nuevo.")).toBeVisible();
  });
});
