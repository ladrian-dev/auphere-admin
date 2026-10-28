import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { ClientAgent } from "@/lib/backend";
import type { AgentConversationPage, AgentPerformance, Improvement, Improvements } from "@/lib/backend/agent-improve-types";
import type { BuilderDraft } from "@/lib/backend/builder-types";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/app/(console)/clients/[ref]/agents/improve-actions", () => ({}));
vi.mock("@/app/(console)/clients/[ref]/agents/builder-actions", () => ({}));

const { AgentPerformancePanel } = await import("../agent-performance");
const { AgentImprovementsPanel } = await import("../agent-improvements");
const { ReceptionBadge, ReceptionSection } = await import("../reception-section");
type PerfActions = NonNullable<React.ComponentProps<typeof AgentPerformancePanel>["actions"]>;
type ImpActions = NonNullable<React.ComponentProps<typeof AgentImprovementsPanel>["actions"]>;

/**
 * Spec 047 — la pantalla del agente del partner gana Rendimiento y Mejoras
 * (T174; requisitos 51 y 52.2) y Recepción (T178; requisito 53). Nada de esto
 * enseña un mensaje: las conversaciones llegan con sus metadatos y una
 * corrección con la lección y la paráfrasis.
 */

const REF = "barberia-cultor";
const AGENT = "00000000-0000-4000-8000-0000000000a1";
const VENTAS = "00000000-0000-4000-8000-0000000000a3";
const CITAS = "00000000-0000-4000-8000-0000000000a4";
const ok = <T,>(data: T) => ({ ok: true as const, data });
const usd = (amount_micros: number) => ({ amount_micros, currency: "USD" as const });

function perf(days = 30): AgentPerformance {
  const series = Array.from({ length: days }, (_, i) => ({
    day: new Date(Date.UTC(2026, 8, 29 + i)).toISOString().slice(0, 10),
    conversations: i % 3,
    resolved_without_person: i % 2,
    handed_to_person: i % 3 === 2 ? 1 : 0,
    spent: usd(12_000),
  }));
  return {
    days,
    since: "2026-09-29T00:00:00Z",
    until: "2026-10-29T00:00:00Z",
    conversations: 42,
    resolved_without_person: 35,
    handed_to_person: 7,
    resolved_pct: 83.3,
    spent: usd(4_200_000),
    spend_per_conversation: usd(100_000),
    series,
  };
}

const page: AgentConversationPage = {
  items: [
    {
      id: "00000000-0000-4000-8000-00000000c001",
      started_at: "2026-10-27T09:00:00Z",
      last_activity_at: "2026-10-27T09:12:00Z",
      channel_type: "whatsapp",
      duration_seconds: 720,
      messages_count: 9,
      outcome: "handed_to_person",
      in_progress: false,
      handoff_reason: "reception_loop",
      spent: usd(150_000),
    },
  ],
  next_cursor: "c2",
};

describe("Rendimiento (T174)", { timeout: 30_000 }, () => {
  // `hidden`: esta persona no puede leer conversaciones (un `undefined` a secas tomaría el valor por defecto).
  function view(over: Partial<PerfActions> = {}, list: AgentConversationPage | null | "hidden" = page) {
    const conversations = list === "hidden" ? undefined : list;
    const actions: PerfActions = {
      load: vi.fn(async (b) => ok(perf(b.days))),
      more: vi.fn(async () => ok({ items: [{ ...page.items[0]!, id: "00000000-0000-4000-8000-00000000c002", handoff_reason: null, outcome: "resolved_without_person" as const }], next_cursor: null })),
      ...over,
    };
    const r = render(
      <LocaleProvider locale="es">
        <AgentPerformancePanel refId={REF} agentId={AGENT} performance={perf()} conversations={conversations} actions={actions} />
      </LocaleProvider>,
    );
    return { ...r, actions };
  }

  it("enseña los 30 días con sus cifras, la gráfica y las conversaciones solo con metadatos, y pasa axe", async () => {
    const { container } = view();
    const figures = container.querySelector("[data-slot=performance-figures]") as HTMLElement;
    expect(within(figures).getByText("42")).toBeInTheDocument();
    expect(within(figures).getByText("35")).toBeInTheDocument();
    expect(within(figures).getByText("83 % del total")).toBeInTheDocument();
    expect(within(figures).getByText("7")).toBeInTheDocument();
    expect(within(figures).getByText(/42,00/)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "30 días" })).toHaveAttribute("aria-selected", "true");
    const table = screen.getByRole("table", { name: "Conversaciones" });
    expect(within(table).getByText("WhatsApp")).toBeInTheDocument();
    expect(within(table).getByText("12 min")).toBeInTheDocument();
    expect(within(table).getByText("Derivaciones en bucle")).toBeInTheDocument();
    expect(within(table).getByText("Pasó a una persona")).toBeInTheDocument();
    expect(screen.getByText(/Nunca los mensajes ni quién era el cliente/)).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("la píldora cambia el periodo, también con las flechas", async () => {
    const user = userEvent.setup();
    const { actions } = view();
    await user.click(screen.getByRole("tab", { name: "7 días" }));
    await waitFor(() => expect(actions.load).toHaveBeenCalledWith({ ref: REF, agent: AGENT, days: 7 }));
    expect(await screen.findByText("Últimos 7 días")).toBeInTheDocument();
    screen.getByRole("tab", { name: "7 días" }).focus();
    await user.keyboard("{ArrowRight}");
    await waitFor(() => expect(actions.load).toHaveBeenCalledWith({ ref: REF, agent: AGENT, days: 30 }));
    expect(screen.getByRole("tab", { name: "30 días" })).toHaveFocus();
  });

  it("«Ver más» sigue el cursor; sin permiso, la lista no se pinta; si las cifras fallan, se reintenta", async () => {
    const user = userEvent.setup();
    const { actions, unmount } = view();
    await user.click(screen.getByRole("button", { name: "Ver más" }));
    await waitFor(() => expect(actions.more).toHaveBeenCalledWith({ ref: REF, agent: AGENT, cursor: "c2" }));
    expect(await screen.findByText("Sin persona")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ver más" })).toBeNull();
    unmount();

    view({}, "hidden");
    expect(screen.queryByRole("table", { name: "Conversaciones" })).toBeNull();
  });

  it("si el periodo no llega, lo dice y deja reintentar", async () => {
    const user = userEvent.setup();
    const load = vi.fn().mockResolvedValueOnce({ ok: false, status: 500, message: "x" }).mockResolvedValueOnce(ok(perf(90)));
    view({ load });
    await user.click(screen.getByRole("tab", { name: "90 días" }));
    expect(await screen.findByText("No pudimos leer el rendimiento")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByText("Últimos 90 días")).toBeInTheDocument();
  });
});

function suggestion(over: Partial<Improvement> = {}): Improvement {
  return {
    id: "00000000-0000-4000-8000-0000000000d1",
    kind: "suggestion",
    week: "2026-10-19",
    topic: "12 clientes preguntaron por el aparcamiento y el agente no supo",
    summary: "Añadir dónde aparcar.",
    lesson: null,
    origin: null,
    conversations_count: 12,
    contacts_count: 9,
    proposal_id: "p1",
    diff: { ops: [{ op: "add", path: "/rules/-", value: "El aparcamiento está en la calle de atrás" }] },
    test: { name: "Pregunta por el aparcamiento", persona: "", first_message: "¿Dónde aparco?", plan: "", criteria: [], critical: false },
    created_at: "2026-10-26T10:00:00Z",
    ...over,
  };
}

const correction = suggestion({
  id: "00000000-0000-4000-8000-0000000000d2",
  kind: "correction",
  week: null,
  topic: "¿Dais citas el día de fiesta?",
  summary: "No des citas los festivos",
  lesson: "No des citas los festivos",
  origin: "app",
  conversations_count: 1,
  contacts_count: 1,
});

describe("Mejoras (T174)", { timeout: 30_000 }, () => {
  function view(data: Improvements | null, over: Partial<ImpActions> = {}) {
    const actions: ImpActions = {
      reload: vi.fn(async () => ok({ items: [suggestion()], allowed: ["accept", "discard"] as ("accept" | "discard")[] })),
      accept: vi.fn(async () => ok({ id: "x", status: "accepted" as const, draft_revision: 9, test_id: "t9" })),
      discard: vi.fn(async () => ok({ id: "x", status: "discarded" as const, suppress_until: "2026-11-27T00:00:00Z" })),
      ...over,
    };
    const onAccepted = vi.fn();
    const r = render(
      <LocaleProvider locale="es">
        <AgentImprovementsPanel refId={REF} agentId={AGENT} improvements={data} onAccepted={onAccepted} actions={actions} />
      </LocaleProvider>,
    );
    return { ...r, actions, onAccepted };
  }

  it("las sugerencias dicen a cuántos afectan y las correcciones la lección, nunca el mensaje; pasan axe", async () => {
    const { container } = view({ items: [suggestion(), correction], allowed: ["accept", "discard"] });
    const list = screen.getByRole("list", { name: "Mejoras por decidir" });
    expect(within(list).getByText("12 conversaciones de 9 clientes")).toBeInTheDocument();
    expect(within(list).getByText("Sugerencia de la semana")).toBeInTheDocument();
    expect(within(list).getByText("Corrección del negocio")).toBeInTheDocument();
    expect(within(list).getByText("Desde la app")).toBeInTheDocument();
    expect(within(list).getByText("No des citas los festivos")).toBeInTheDocument();
    // Cuatro botones en la lista: cada fila los pliega en «⋯».
    expect(within(list).getAllByRole("button", { name: /^Acciones de / })).toHaveLength(2);
    expect(await axeViolations(container)).toEqual([]);
  });

  it("aceptar dice en qué quedó el borrador y avisa a la pantalla", async () => {
    const user = userEvent.setup();
    const { actions, onAccepted } = view({ items: [suggestion()], allowed: ["accept", "discard"] });
    await user.click(screen.getByText("Ver propuesta"));
    expect(screen.getByText("Prueba nueva: Pregunta por el aparcamiento")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Aceptar" }));
    await waitFor(() => expect(actions.accept).toHaveBeenCalledWith({ ref: REF, agent: AGENT, id: suggestion().id }));
    expect(await screen.findByText(/El cambio y su prueba están en el borrador \(revisión 9\)/)).toBeInTheDocument();
    expect(onAccepted).toHaveBeenCalledWith(expect.objectContaining({ draft_revision: 9 }));
    expect(screen.getByText("Nada que mejorar por ahora")).toBeInTheDocument();
  });

  it("descartar pide el motivo (al menos 3 caracteres) y no vuelve en 30 días", async () => {
    const user = userEvent.setup();
    const { actions } = view({ items: [suggestion()], allowed: ["accept", "discard"] });
    await user.click(screen.getByRole("button", { name: "Descartar" }));
    const dialog = await screen.findByRole("dialog", { name: "¿Por qué la descartas?" });
    expect(within(dialog).getByText("No volveremos a proponerla en 30 días.")).toBeInTheDocument();
    await user.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "no");
    await user.click(within(dialog).getByRole("button", { name: "Descartar" }));
    expect(within(dialog).getByText("Escribe el motivo, al menos 3 caracteres.")).toBeInTheDocument();
    expect(actions.discard).not.toHaveBeenCalled();
    await user.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), " aplica: no tenemos parking");
    await user.click(within(dialog).getByRole("button", { name: "Descartar" }));
    await waitFor(() => expect(actions.discard).toHaveBeenCalledWith({ ref: REF, agent: AGENT, id: suggestion().id, reason: "no aplica: no tenemos parking" }));
    expect(toast.success).toHaveBeenCalledWith("Descartada. No volverá en 30 días.");
  });

  it("los «no» de la API en palabras; quien solo lee no tiene botones; vacío y error", async () => {
    const user = userEvent.setup();
    const { unmount } = view({ items: [suggestion()], allowed: ["accept", "discard"] }, { accept: vi.fn(async () => ({ ok: false as const, status: 409, message: "x", code: "improvement_outdated" })) });
    await user.click(screen.getByRole("button", { name: "Aceptar" }));
    expect(await screen.findByText("El borrador cambió y la propuesta ya no encaja.")).toBeInTheDocument();
    unmount();

    const reader = view({ items: [suggestion()], allowed: [] });
    expect(screen.queryByRole("button", { name: /Aceptar|Descartar|Acciones de/ })).toBeNull();
    reader.unmount();

    const broken = view(null);
    expect(screen.getByText("No pudimos leer las mejoras")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    await waitFor(() => expect(broken.actions.reload).toHaveBeenCalledWith({ ref: REF, agent: AGENT }));
  });
});

describe("Recepción (T178)", { timeout: 30_000 }, () => {
  const agents: ClientAgent[] = [
    { id: AGENT, name: "Recepción", status: "active", is_principal: true, channels: [], active_version: 2, draft_version: null },
    { id: VENTAS, name: "Ventas mayoristas", status: "active", is_principal: false, channels: [], active_version: 1, draft_version: null, visible_state: { code: "serving", tone: "positive", reason: null } },
    { id: CITAS, name: "Citas", status: "active", is_principal: false, channels: [], active_version: 1, draft_version: null, visible_state: { code: "paused", tone: "warn", reason: "manual" } },
    { id: "00000000-0000-4000-8000-0000000000a9", name: "Vieja", status: "archived", is_principal: false, channels: [], active_version: null, draft_version: null },
  ];

  type Save = React.ComponentProps<typeof ReceptionSection>["onSave"];
  function view(reception = { enabled: false }, onSave: Save = vi.fn(async () => ok({} as BuilderDraft)), canWrite = true) {
    const onReload = vi.fn();
    const r = render(
      <LocaleProvider locale="es">
        <ReceptionSection agentId={AGENT} reception={reception} agents={agents} canWrite={canWrite} onSave={onSave} onReload={onReload} />
      </LocaleProvider>,
    );
    return { ...r, onSave, onReload };
  }

  it("marcar como Recepción, elegir destinos de este cliente y decir cuándo; guarda el AgentSpec", async () => {
    const user = userEvent.setup();
    const { onSave, container } = view();
    expect(screen.getByText("No deriva")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Editar Recepción" }));
    await user.click(screen.getByRole("checkbox", { name: /Este agente es Recepción/ }));
    // Solo los demás agentes vivos de este cliente: ni él mismo ni el archivado.
    expect(screen.getByRole("checkbox", { name: "Derivar a Ventas mayoristas" })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: /Derivar a Recepción|Derivar a Vieja/ })).toBeNull();
    expect(screen.getByText(/En pausa ahora/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Guardar en el borrador" }));
    expect(screen.getByText("Elige al menos un agente al que derivar.")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "Derivar a Ventas mayoristas" }));
    await user.click(screen.getByRole("button", { name: "Guardar en el borrador" }));
    expect(screen.getByText("Di cuándo derivarle.")).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: /Cuándo derivar a Ventas mayoristas/ }), "Quiere comprar  al por mayor");
    expect(await axeViolations(container)).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Guardar en el borrador" }));
    await waitFor(() => expect(vi.mocked(onSave)).toHaveBeenCalledWith({ enabled: true, targets: [{ agent_id: VENTAS, when: "Quiere comprar al por mayor" }] }));
  });

  it("lee lo guardado con sus destinos; un 412 avisa y vuelve a leer; sin permiso, sin «Editar»", async () => {
    const user = userEvent.setup();
    const conflict: Save = vi.fn(async () => ({ ok: false as const, status: 412, message: "x", code: "revision_conflict" }));
    const { onReload, unmount } = view({ enabled: true, targets: [{ agent_id: VENTAS, when: "Quiere comprar al por mayor" }] } as never, conflict);
    expect(screen.getByText("Es Recepción")).toBeInTheDocument();
    const list = screen.getByRole("list", { name: "A quién deriva" });
    expect(within(list).getByText("Ventas mayoristas")).toBeInTheDocument();
    expect(within(list).getByText("Cuándo: Quiere comprar al por mayor")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Editar Recepción" }));
    await user.click(screen.getByRole("button", { name: "Guardar en el borrador" }));
    expect(await screen.findByText(/Alguien guardó este agente mientras editabas/)).toBeInTheDocument();
    expect(onReload).toHaveBeenCalled();
    unmount();

    view({ enabled: false }, undefined, false);
    expect(screen.queryByRole("button", { name: "Editar Recepción" })).toBeNull();
  });
});

describe("La marca «Recepción» de la cabecera", () => {
  function badge(published: boolean | undefined, drafted: boolean) {
    const { container, unmount } = render(
      <LocaleProvider locale="es">
        <ReceptionBadge published={published} drafted={drafted} />
      </LocaleProvider>,
    );
    const text = container.querySelector("[data-slot=agent-reception]")?.textContent ?? null;
    unmount();
    return text;
  }

  it("dice lo publicado y avisa de lo que cambia el borrador", () => {
    expect(badge(true, true)).toBe("Recepción");
    expect(badge(true, false)).toBe("Deja de ser Recepción al publicar");
    expect(badge(false, true)).toBe("Recepción al publicar");
    expect(badge(false, false)).toBeNull();
    // Sin el dato de la API, manda el borrador (lo de antes).
    expect(badge(undefined, true)).toBe("Recepción");
  });

  it("marca los destinos que también son Recepción", async () => {
    const user = userEvent.setup();
    render(
      <LocaleProvider locale="es">
        <ReceptionSection
          agentId={AGENT}
          reception={{ enabled: true, targets: [] }}
          agents={[
            { id: AGENT, name: "Recepción", status: "active", is_principal: true, channels: [], active_version: 2, draft_version: null },
            { id: VENTAS, name: "Ventas", status: "active", is_principal: false, channels: [], active_version: 1, draft_version: null, is_reception: true },
          ]}
          canWrite
          onSave={vi.fn()}
          onReload={vi.fn()}
        />
      </LocaleProvider>,
    );
    await user.click(screen.getByRole("button", { name: "Editar Recepción" }));
    expect(screen.getAllByText("También es Recepción")).toHaveLength(1);
  });
});
