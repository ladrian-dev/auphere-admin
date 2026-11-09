import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { Proposal } from "@/lib/backend/builder-types";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const { ProposalList } = await import("../proposals");
type Props = React.ComponentProps<typeof ProposalList>;

/**
 * Spec 057 (T029; requisitos 3.3 y 3.7; `contracts/console-api.md` §8) — la
 * propuesta del texto de citas se ve por bloque, con lo de antes y lo de después
 * (`before` de cada operación). «Editar» la aplica y abre el primer bloque
 * cambiado; nada se aplica solo. Si la ficha dice que el equipo confirma las
 * citas, la propuesta lo señala con un enlace a Negocio, sin tocar la ficha.
 */

const REF = "spa-jemma";
const AGENT = "11111111-1111-4111-8111-111111111111";
const PROPOSAL = "55555555-5555-4555-8555-555555555555";

const AGENDA_TEXT: Proposal = {
  id: PROPOSAL,
  kind: "agent_spec_patch",
  author: "builder",
  summary: "Activaste la agenda: así cambian sus citas",
  diff: {
    ops: [
      {
        op: "replace",
        path: "/procedures/0/steps",
        value: "Busca huecos con la agenda y reserva.",
        before: "No ofrezcas huecos ni confirmes la reserva. Pasa la conversación al equipo.",
      },
      { op: "remove", path: "/rules/1", before: "Una solicitud de cita no es una reserva confirmada." },
      { op: "add", path: "/procedures/-", value: { id: "mover", title: "Mover una cita" }, before: null },
    ],
    ficha_links: [{ section: "policies.cancellation" }],
  },
  status: "open",
  created_at: "2026-11-09T10:00:00Z",
  expires_at: "2026-11-16T10:00:00Z",
};

function list(props: Partial<Props> = {}) {
  const decide = vi.fn<Props["decide"]>(async () => ({ ok: true as const, data: { id: PROPOSAL, status: "applied", draft_revision: 8 } }));
  const onApplied = vi.fn();
  const onEdit = vi.fn();
  const view = render(
    <LocaleProvider locale="es">
      <ProposalList
        refId={REF}
        agentId={AGENT}
        proposals={[AGENDA_TEXT]}
        canWrite
        decide={decide}
        onApplied={onApplied}
        onRetry={vi.fn()}
        onEdit={onEdit}
        {...props}
      />
    </LocaleProvider>,
  );
  return { ...view, decide, onApplied, onEdit };
}

const group = (title: string) => screen.getByRole("heading", { level: 3, name: title }).closest("[data-slot=proposal-block]") as HTMLElement;

beforeEach(() => toast.success.mockClear());

describe("la propuesta, por bloque (3.3)", () => {
  it("agrupa por bloque, con lo de antes y lo de después; pasa axe", async () => {
    const { container } = list();
    const procedures = group("Procedimientos");
    expect(within(procedures).getAllByText("Antes")).toHaveLength(2);
    expect(within(procedures).getByText("No ofrezcas huecos ni confirmes la reserva. Pasa la conversación al equipo.")).toBeVisible();
    expect(within(procedures).getByText("Busca huecos con la agenda y reserva.")).toBeVisible();
    // Lo que no existía: «Nada» antes.
    expect(within(procedures).getByText("Nada")).toBeVisible();
    const rules = group("Reglas");
    expect(within(rules).getByText("Una solicitud de cita no es una reserva confirmada.")).toBeVisible();
    expect(within(rules).getByText("Se quita")).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("una operación sin `before` (de antes de la 057) se sigue diciendo como siempre", () => {
    list({ proposals: [{ ...AGENDA_TEXT, diff: { ops: [{ op: "add", path: "/rules/-", value: "No des precios" }] } }] });
    expect(screen.getByText("Añade en Reglas")).toBeVisible();
    expect(screen.getByText("No des precios")).toBeVisible();
  });

  it("«Editar» la aplica y abre el primer bloque cambiado; «Aplicar» y «Rechazar» siguen", async () => {
    const user = userEvent.setup();
    const { decide, onApplied, onEdit } = list();
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Rechazar" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Aplicar y editar «Procedimientos»" }));
    expect(decide).toHaveBeenCalledWith({ ref: REF, agent: AGENT, proposal: PROPOSAL, decision: "apply" });
    await waitFor(() => expect(onEdit).toHaveBeenCalledWith("procedures"));
    expect(onApplied).toHaveBeenCalled();
  });

  it("si aplicarla falla, no abre ningún editor", async () => {
    const user = userEvent.setup();
    const decide = vi.fn<Props["decide"]>(async () => ({ ok: false as const, status: 409, message: "", code: "proposal_stale" }));
    const { onEdit } = list({ decide });
    await user.click(screen.getByRole("button", { name: "Aplicar y editar «Procedimientos»" }));
    expect(await screen.findByText(/Ya no aplica/)).toBeVisible();
    expect(onEdit).not.toHaveBeenCalled();
  });

  it("sin quien abra el editor (el copiloto), o para quien solo lee, no hay «Editar»", () => {
    const { unmount } = list({ onEdit: undefined });
    expect(screen.queryByRole("button", { name: /Aplicar y editar/ })).toBeNull();
    unmount();
    list({ canWrite: false });
    expect(screen.queryByRole("button", { name: /Aplicar y editar/ })).toBeNull();
  });
});

describe("la propuesta y la ficha (3.7)", () => {
  it("señala la sección de la ficha que dice que el equipo confirma, con su enlace a Negocio", () => {
    list();
    const note = screen.getByText(/La ficha del negocio dice que el equipo confirma las citas/).closest("[data-slot=proposal-ficha]") as HTMLElement;
    expect(note).toHaveTextContent("«Políticas»");
    expect(within(note).getByRole("link", { name: "Ir a Negocio" })).toHaveAttribute("href", `/clients/${REF}/business#business-policies`);
  });
});

/**
 * Revisión de las puertas de UI (spec 057, 3.3): la propuesta de la agenda
 * reescribe bloques enteros (`/procedures`, `/rules`, `/escalation`, `/skills`,
 * `/instructions`, `/services`). Cada lado se lee como el bloque —títulos y pasos,
 * reglas en lista, disparadores, habilidades con su alternativa, preguntas
 * frecuentes— entero y sin JSON.
 */
describe("la propuesta, por bloque entero (3.3)", () => {
  const LONG_STEPS =
    "Pregunta qué servicio quiere y con quién. Busca los huecos libres de los próximos siete días con la agenda, ofrece como mucho tres, y cuando elija uno, reserva y confirma la hora, el servicio y la política de cancelación del negocio en un solo mensaje.";
  const WHOLE: Proposal = {
    ...AGENDA_TEXT,
    diff: {
      ops: [
        {
          op: "replace",
          path: "/procedures",
          before: [{ id: "solicitud", title: "Recoger una solicitud de cita", when: "Cuando piden cita", steps: "No ofrezcas huecos ni confirmes la reserva." }],
          value: [{ id: "reservar", title: "Reservar una cita", when: "Cuando piden cita", steps: LONG_STEPS, tools: ["reservas.find_slots", "reservas.create"] }],
        },
        {
          op: "replace",
          path: "/rules",
          before: ["Una solicitud de cita no es una reserva confirmada.", "No des precios por teléfono."],
          value: ["No des precios por teléfono."],
        },
        {
          op: "replace",
          path: "/escalation",
          before: { triggers: ["asks_for_human", { custom: "Cuando solicitan crear, cambiar o cancelar una cita, porque la agenda no está activa" }], failed_attempts: 2 },
          value: { triggers: ["asks_for_human"], failed_attempts: 2 },
        },
        {
          op: "replace",
          path: "/skills",
          before: [{ key: "appointment_request_intake", enabled: true, integration: null, fallback: "Pasa la solicitud al equipo para que la confirme." }],
          value: [{ key: "appointment_request_intake", enabled: true, integration: null, fallback: "Reserva con la agenda." }],
        },
        {
          op: "replace",
          path: "/services",
          before: { mode: "all", faqs: [{ q: "¿Puedo reservar por aquí?", a: "Te paso con el equipo para que lo confirme." }] },
          value: { mode: "all", faqs: [{ q: "¿Puedo reservar por aquí?", a: "Sí, te busco hueco ahora mismo." }] },
        },
        {
          op: "replace",
          path: "/instructions",
          before: { sections: [{ title: "Citas", body: "El equipo confirma cada cita." }] },
          value: { sections: [{ title: "Citas", body: "Reserva tú con la agenda." }] },
        },
      ],
    },
  };

  it("cada lado se lee como el bloque, entero y sin JSON; pasa axe", async () => {
    const { container } = list({ proposals: [WHOLE] });
    const procedures = group("Procedimientos");
    expect(within(procedures).getByText("Recoger una solicitud de cita")).toBeVisible();
    expect(within(procedures).getByText("Reservar una cita")).toBeVisible();
    // Los pasos, enteros: nada de cortarlos a 200 caracteres.
    expect(within(procedures).getByText(LONG_STEPS)).toBeVisible();
    const rules = group("Reglas");
    const side = (el: HTMLElement, which: "before" | "after") => el.querySelector(`[data-side=${which}]`) as HTMLElement;
    expect(within(side(rules, "before")).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Una solicitud de cita no es una reserva confirmada.",
      "No des precios por teléfono.",
    ]);
    expect(within(side(rules, "after")).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["No des precios por teléfono."]);
    expect(within(group("Cuándo pasa a una persona")).getByText("Cuando solicitan crear, cambiar o cancelar una cita, porque la agenda no está activa")).toBeVisible();
    const skills = group("Qué puede hacer");
    expect(within(skills).getByText("Mientras tanto: Pasa la solicitud al equipo para que la confirme.")).toBeVisible();
    expect(within(skills).getByText("Mientras tanto: Reserva con la agenda.")).toBeVisible();
    const services = group("Qué sabe");
    expect(within(services).getByText("Te paso con el equipo para que lo confirme.")).toBeVisible();
    expect(within(services).getByText("Sí, te busco hueco ahora mismo.")).toBeVisible();
    expect(within(group("Instrucciones")).getByText("El equipo confirma cada cita.")).toBeVisible();
    expect(container.textContent).not.toMatch(/[{}[\]]"|"[:,]/);
    expect(await axeViolations(container)).toEqual([]);
  });

  it("una operación sobre un elemento suelto se lee como ese elemento", () => {
    list({
      proposals: [
        {
          ...AGENDA_TEXT,
          diff: {
            ops: [
              { op: "remove", path: "/escalation/triggers/1", before: { custom: "Porque la agenda no está activa" } },
              { op: "add", path: "/services/faqs/-", before: null, value: { q: "¿Reserváis hoy?", a: "Sí, mira los huecos." } },
            ],
          },
        },
      ],
    });
    expect(within(group("Cuándo pasa a una persona")).getByText("Porque la agenda no está activa")).toBeVisible();
    expect(within(group("Qué sabe")).getByText("¿Reserváis hoy?")).toBeVisible();
    expect(within(group("Qué sabe")).getByText("Sí, mira los huecos.")).toBeVisible();
  });
});
