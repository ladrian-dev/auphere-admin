/**
 * Spec 082 (Historia 2): el conocimiento del agente se ve al añadirlo.
 *
 * - 2.1 y 2.3: añadir, quitar o restaurar relee la lista y avisa al resto de la
 *   pantalla (`onChanged`), como ya pasaba al enseñar.
 * - 2.2: «Qué sabe» lee de la misma consulta y cuenta solo las fuentes vivas.
 * - 2.4: con una fuente en «Leyendo», la lista se relee cada 5 s mientras la
 *   pestaña está visible, y para a los 10 minutos.
 * - 2.5: una subida que no responde en 120 s, o una web en 60 s, dice que no
 *   respondió a tiempo y relee la lista.
 */
import { axeViolations } from "@nexus/ui/test/axe";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { AgentKnowledge } from "@/lib/backend/agent-knowledge-types";
import { testQueryClient } from "@/test/query";

import { DOC2, RECEPCION, REF, knowledge, ok, source } from "./channel-fixtures";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/app/(console)/clients/[ref]/agents/knowledge-actions", () => ({}));

const { AgentKnowledgePanel } = await import("../agent-knowledge");
const { useAgentKnowledge, KNOWLEDGE_POLL_MS, KNOWLEDGE_POLL_FOR_MS } = await import("../use-agent-knowledge");
const { QueryClientProvider } = await import("@tanstack/react-query");
type Actions = NonNullable<React.ComponentProps<typeof AgentKnowledgePanel>["actions"]>;

const CARTA = source({ id: DOC2, title: "Carta de otoño" });
const never = () => new Promise<never>(() => undefined);

/** «Qué sabe», as the builder counts it: the same query, live sources only. */
function Knows({ initial, reload }: { initial: AgentKnowledge | null; reload: Actions["reload"] }) {
  const known = useAgentKnowledge({ ref: REF, agent: RECEPCION }, initial, reload);
  return <p data-testid="knows">{known.live ?? "—"}</p>;
}

function panel(data: AgentKnowledge | null, over: Partial<Actions> = {}) {
  const actions: Actions = {
    reload: vi.fn(async () => ok(data ?? knowledge())),
    upload: vi.fn(async () => ok(CARTA)),
    addUrl: vi.fn(async () => ok(source({ id: DOC2, kind: "url", title: "Precios" }))),
    remove: vi.fn(async () => ok(null)),
    restore: vi.fn(async () => ok(source())),
    teach: vi.fn(async () => ok(source({ id: DOC2, kind: "note", title: "Cerramos en agosto" }))),
    forget: vi.fn(async () => ok(null)),
    ...over,
  };
  const onChanged = vi.fn();
  const client = testQueryClient();
  const view = render(
    <QueryClientProvider client={client}>
      <LocaleProvider locale="es">
        <Knows initial={data} reload={actions.reload} />
        <AgentKnowledgePanel refId={REF} agentId={RECEPCION} agentName="Recepción" knowledge={data} canWrite onChanged={onChanged} actions={actions} />
      </LocaleProvider>
    </QueryClientProvider>,
  );
  return { ...view, actions, onChanged };
}

const knows = () => screen.getByTestId("knows").textContent;

beforeEach(() => {
  toast.success.mockClear();
  toast.error.mockClear();
  Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
});
afterEach(() => vi.useRealTimers());

describe("Conocimiento del agente · al día (spec 082)", () => {
  it("añadir un archivo relee la lista, «Qué sabe» lo cuenta y avisa al resto de la pantalla (2.1, 2.3)", async () => {
    const user = userEvent.setup();
    const { actions, onChanged } = panel(knowledge(), { reload: vi.fn(async () => ok(knowledge({ items: [source(), CARTA] }))) });
    expect(knows()).toBe("1");
    await user.click(screen.getByRole("button", { name: "Subir un archivo" }));
    await user.upload(screen.getByLabelText(/Archivo \(PDF/), new File(["hola"], "carta.txt", { type: "text/plain" }));
    await user.click(screen.getByRole("button", { name: "Subir para este agente" }));
    const list = await screen.findByRole("list", { name: "Fuentes de este agente" });
    expect(await within(list).findByText("Carta de otoño")).toBeVisible();
    expect(actions.reload).toHaveBeenCalledWith({ ref: REF, agent: RECEPCION });
    expect(knows()).toBe("2");
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it("quitar y restaurar también avisan, y «Qué sabe» no cuenta la quitada (2.2, 2.3)", async () => {
    const user = userEvent.setup();
    const removed = source({ removed_at: new Date().toISOString(), restore_until: new Date(Date.now() + 600_000).toISOString() });
    const reload = vi
      .fn()
      .mockResolvedValueOnce(ok(knowledge({ items: [removed, CARTA] })))
      .mockResolvedValue(ok(knowledge({ items: [source(), CARTA] })));
    const { onChanged } = panel(knowledge({ items: [source(), CARTA] }), { reload });
    expect(knows()).toBe("2");
    await user.click(screen.getByRole("button", { name: "Quitar Tarifas mayoristas" }));
    const restorable = await screen.findByRole("list", { name: "Quitadas hace poco" });
    expect(knows()).toBe("1");
    expect(onChanged).toHaveBeenCalledTimes(1);
    await user.click(within(restorable).getByRole("button", { name: "Deshacer quitar Tarifas mayoristas" }));
    await waitFor(() => expect(knows()).toBe("2"));
    expect(onChanged).toHaveBeenCalledTimes(2);
  });

  it("con una fuente pendiente de leer relee cada 5 s mientras se ve, la fila cambia sola y para a los 10 minutos (2.4)", async () => {
    vi.useFakeTimers();
    const reading = knowledge({ items: [source({ status: "pending", indexed_at: null })] });
    const reload = vi.fn(async () => ok(reading));
    panel(reading, { reload });
    await act(async () => void (await vi.advanceTimersByTimeAsync(KNOWLEDGE_POLL_MS - 100)));
    expect(reload).not.toHaveBeenCalled();
    await act(async () => void (await vi.advanceTimersByTimeAsync(100)));
    expect(reload).toHaveBeenCalledTimes(1);
    await act(async () => void (await vi.advanceTimersByTimeAsync(KNOWLEDGE_POLL_MS)));
    expect(reload).toHaveBeenCalledTimes(2);
    // Hidden, it does not read.
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    await act(async () => void (await vi.advanceTimersByTimeAsync(KNOWLEDGE_POLL_MS * 3)));
    expect(reload).toHaveBeenCalledTimes(2);
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
    // Ten minutes after it first saw one reading, it stops.
    await act(async () => void (await vi.advanceTimersByTimeAsync(KNOWLEDGE_POLL_FOR_MS)));
    const asked = reload.mock.calls.length;
    expect(asked).toBeGreaterThan(2);
    await act(async () => void (await vi.advanceTimersByTimeAsync(KNOWLEDGE_POLL_MS * 6)));
    expect(reload).toHaveBeenCalledTimes(asked);
  });

  it("cuando la fuente termina de leerse, la fila cambia sola y deja de releer (2.4)", async () => {
    vi.useFakeTimers();
    const reading = knowledge({ items: [source({ status: "pending", indexed_at: null })] });
    const reload = vi.fn(async () => ok(knowledge()));
    panel(reading, { reload });
    expect(screen.getByText("Pendiente")).toBeInTheDocument();
    // The poll, and React Query's repaint right after it (a timer of its own).
    await act(async () => void (await vi.advanceTimersByTimeAsync(KNOWLEDGE_POLL_MS + 50)));
    expect(screen.getByText("Indexado")).toBeInTheDocument();
    await act(async () => void (await vi.advanceTimersByTimeAsync(KNOWLEDGE_POLL_MS * 4)));
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("una subida que no responde en 120 s dice que no respondió a tiempo y relee la lista (2.5)", async () => {
    const user = userEvent.setup();
    const { actions } = panel(knowledge(), { upload: vi.fn(never) });
    await user.click(screen.getByRole("button", { name: "Subir un archivo" }));
    await user.upload(screen.getByLabelText(/Archivo \(PDF/), new File(["hola"], "carta.txt", { type: "text/plain" }));
    vi.useFakeTimers();
    fireEvent.click(screen.getByRole("button", { name: "Subir para este agente" }));
    await act(async () => void (await vi.advanceTimersByTimeAsync(119_000)));
    expect(screen.queryByText(/No respondió a tiempo/)).toBeNull();
    expect(actions.reload).not.toHaveBeenCalled();
    await act(async () => void (await vi.advanceTimersByTimeAsync(1_000)));
    expect(screen.getByText(/No respondió a tiempo/)).toBeInTheDocument();
    expect(actions.reload).toHaveBeenCalledTimes(1);
    // The form is free again: the person may try once more.
    expect(screen.getByRole("button", { name: "Subir para este agente" })).toBeEnabled();
  });

  it("una web que no responde en 60 s, lo mismo (2.5)", async () => {
    const user = userEvent.setup();
    const { actions } = panel(knowledge(), { addUrl: vi.fn(never) });
    await user.click(screen.getByRole("button", { name: "Añadir una web" }));
    await user.type(screen.getByLabelText(/Dirección de la web/), "https://cultor.es/precios");
    vi.useFakeTimers();
    fireEvent.click(screen.getByRole("button", { name: "Añadir para este agente" }));
    await act(async () => void (await vi.advanceTimersByTimeAsync(59_000)));
    expect(screen.queryByText(/No respondió a tiempo/)).toBeNull();
    await act(async () => void (await vi.advanceTimersByTimeAsync(1_000)));
    expect(screen.getByText(/No respondió a tiempo/)).toBeInTheDocument();
    expect(actions.reload).toHaveBeenCalledTimes(1);
  });

  it("sin lectura del servidor: carga con su esqueleto y, si falla, lo dice y deja reintentar", async () => {
    const user = userEvent.setup();
    const reload = vi
      .fn()
      .mockResolvedValueOnce({ ok: false as const, status: 500, message: "" })
      .mockResolvedValue(ok(knowledge()));
    const { container } = panel(null, { reload });
    expect(screen.getByRole("status", { name: "Cargando lo que sabe el agente" })).toBeInTheDocument();
    // T041: los dos estados nuevos también pasan axe.
    expect(await axeViolations(container)).toEqual([]);
    expect(await screen.findByText(/No pudimos cargar el conocimiento/)).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByText("Tarifas mayoristas")).toBeVisible();
  });
});
