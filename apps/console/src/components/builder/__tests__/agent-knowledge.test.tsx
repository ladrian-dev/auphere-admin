import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { AgentKnowledge } from "@/lib/backend/agent-knowledge-types";

import { DOC, DOC2, RECEPCION, REF, fail, knowledge, ok, source } from "./channel-fixtures";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/app/(console)/clients/[ref]/agents/knowledge-actions", () => ({}));

const { AgentKnowledgePanel } = await import("../agent-knowledge");
type Actions = NonNullable<React.ComponentProps<typeof AgentKnowledgePanel>["actions"]>;

/**
 * Spec 047 (historia 22, T134; requisitos 37.3 y 12.1) — la sección
 * Conocimiento del agente: sus fuentes con su estado, cuántas sabe del negocio
 * (con el camino a Negocio), añadir solo para él, quitar con «Deshacer» durante
 * 10 minutos y «Enseñar» que siempre pide el alcance. Quien solo lee no ve
 * botones.
 */

function panel(data: AgentKnowledge | null = knowledge(), over: Partial<Actions> = {}, canWrite = true) {
  const actions: Actions = {
    reload: vi.fn(async () => ok(data ?? knowledge())),
    upload: vi.fn(async () => ok(source({ id: DOC2, title: "Carta de otoño" }))),
    addUrl: vi.fn(async () => ok(source({ id: DOC2, kind: "url", title: "Precios" }))),
    remove: vi.fn(async () => ok(null)),
    restore: vi.fn(async () => ok(source())),
    teach: vi.fn(async ({ scope }) => ok(source({ id: DOC2, kind: "note", title: "Cerramos en agosto", agent_id: scope === "agent" ? RECEPCION : null }))),
    forget: vi.fn(async () => ok(null)),
    ...over,
  };
  const onTaught = vi.fn();
  const view = render(
    <LocaleProvider locale="es">
      <AgentKnowledgePanel refId={REF} agentId={RECEPCION} agentName="Recepción" knowledge={data} canWrite={canWrite} onTaught={onTaught} actions={actions} />
    </LocaleProvider>,
  );
  return { ...view, actions, onTaught };
}

beforeEach(() => {
  toast.success.mockClear();
  toast.error.mockClear();
});

describe("la sección Conocimiento del agente", () => {
  it("enseña sus fuentes y cuántas sabe del negocio, con el camino a Negocio", async () => {
    const { container } = panel();
    const list = screen.getByRole("list", { name: "Fuentes de este agente" });
    const row = within(list).getByRole("listitem");
    expect(within(row).getByText("Tarifas mayoristas")).toBeVisible();
    expect(within(row).getByText("Archivo")).toBeVisible();
    expect(within(row).getByText("Indexado")).toBeVisible();
    expect(screen.getByText(/Además sabe 3 fuentes del negocio/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Verlas en Negocio" })).toHaveAttribute("href", `/clients/${REF}/knowledge`);
    expect(await axeViolations(container)).toEqual([]);
  });

  it("quien solo lee lo ve todo, sin botones (§V)", () => {
    panel(knowledge(), {}, false);
    expect(screen.getByText("Tarifas mayoristas")).toBeVisible();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("si no se pudo leer, lo dice y deja reintentar", async () => {
    const user = userEvent.setup();
    const { actions } = panel(null, { reload: vi.fn(async () => ok(knowledge())) });
    expect(screen.getByText(/No pudimos cargar el conocimiento/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(actions.reload).toHaveBeenCalledWith({ ref: REF, agent: RECEPCION });
    expect(await screen.findByText("Tarifas mayoristas")).toBeVisible();
  });

  it("quitar deja la fuente con «Deshacer» durante 10 minutos (12.2)", async () => {
    const user = userEvent.setup();
    const removed = source({ removed_at: new Date().toISOString(), restore_until: new Date(Date.now() + 600_000).toISOString() });
    const reload = vi.fn().mockResolvedValueOnce(ok(knowledge({ items: [removed] }))).mockResolvedValue(ok(knowledge()));
    const { actions } = panel(knowledge(), { reload });
    await user.click(screen.getByRole("button", { name: "Quitar Tarifas mayoristas" }));
    expect(actions.remove).toHaveBeenCalledWith({ ref: REF, agent: RECEPCION, doc: DOC });
    expect(toast.success).toHaveBeenCalledWith(expect.stringMatching(/Puedes deshacerlo durante 10 minutos/), expect.objectContaining({ action: expect.anything() }));
    const restorable = await screen.findByRole("list", { name: "Quitadas hace poco" });
    expect(within(restorable).getByText(/se puede deshacer hasta las/)).toBeVisible();
    await user.click(within(restorable).getByRole("button", { name: "Deshacer quitar Tarifas mayoristas" }));
    expect(actions.restore).toHaveBeenCalledWith({ ref: REF, agent: RECEPCION, doc: DOC });
    await waitFor(() => expect(screen.queryByRole("list", { name: "Quitadas hace poco" })).toBeNull());
  });

  it("pasado el plazo, deshacer lo dice", async () => {
    const user = userEvent.setup();
    const removed = source({ removed_at: new Date().toISOString(), restore_until: new Date(Date.now() + 600_000).toISOString() });
    panel(knowledge({ items: [removed] }), { restore: vi.fn(async () => fail(409, "undo_window_closed")) });
    await user.click(screen.getByRole("button", { name: "Deshacer quitar Tarifas mayoristas" }));
    expect(toast.error).toHaveBeenCalledWith("Han pasado más de 10 minutos: ya no se puede deshacer.");
  });

  it("con más de dos fuentes, la acción de cada una va en su ⋯", () => {
    panel(knowledge({ items: [source(), source({ id: DOC2, title: "Carta" }), source({ id: "x", title: "Horario de verano" })] }));
    expect(screen.queryByRole("button", { name: "Quitar Carta" })).toBeNull();
    expect(screen.getByRole("button", { name: "Acciones de Carta" })).toBeVisible();
  });

  it("añade una web solo para este agente", async () => {
    const user = userEvent.setup();
    const { actions } = panel();
    await user.click(screen.getByRole("button", { name: "Añadir una web" }));
    const field = screen.getByRole("textbox", { name: /Dirección de la web/ });
    await user.type(field, "cultor.es");
    await user.click(screen.getByRole("button", { name: "Añadir para este agente" }));
    expect(screen.getByText("Escribe una dirección que empiece por http:// o https://.")).toBeVisible();
    expect(actions.addUrl).not.toHaveBeenCalled();
    await user.clear(field);
    await user.type(field, "https://cultor.es/precios");
    await user.click(screen.getByRole("button", { name: "Añadir para este agente" }));
    expect(actions.addUrl).toHaveBeenCalledWith({ ref: REF, agent: RECEPCION, url: "https://cultor.es/precios" });
    expect(toast.success).toHaveBeenCalledWith("«Precios» ya es una fuente de este agente.");
  });

  it("sube un archivo solo para este agente", async () => {
    const user = userEvent.setup();
    const { actions } = panel();
    await user.click(screen.getByRole("button", { name: "Subir un archivo" }));
    await user.upload(screen.getByLabelText(/Archivo \(PDF/), new File(["hola"], "carta.txt", { type: "text/plain" }));
    await user.click(screen.getByRole("button", { name: "Subir para este agente" }));
    const form = (actions.upload as ReturnType<typeof vi.fn>).mock.calls[0]![0] as FormData;
    expect(form.get("ref")).toBe(REF);
    expect(form.get("agent")).toBe(RECEPCION);
    expect((form.get("file") as File).name).toBe("carta.txt");
  });
});

describe("«Enseñar» (37.3)", () => {
  it("no se manda sin elegir el alcance, y dice qué pruebas se vuelven a pasar", async () => {
    const user = userEvent.setup();
    const { actions, onTaught, baseElement } = panel();
    await user.click(screen.getByRole("button", { name: "Enseñar" }));
    const dialog = await screen.findByRole("dialog", { name: "Enseñar algo a Recepción" });
    await user.type(within(dialog).getByRole("textbox", { name: /Lo que debe saber/ }), "Cerramos en agosto");
    expect(within(dialog).getByRole("radio", { name: /Solo este agente/ })).not.toBeChecked();
    expect(within(dialog).getByRole("radio", { name: /Todo el negocio \(todos los agentes\)/ })).not.toBeChecked();
    await user.click(within(dialog).getByRole("button", { name: "Enseñar" }));
    expect(within(dialog).getByText("Elige quién debe saberlo.")).toBeVisible();
    expect(actions.teach).not.toHaveBeenCalled();
    expect(await axeViolations(baseElement)).toEqual([]);

    await user.click(within(dialog).getByRole("radio", { name: /Solo este agente/ }));
    expect(within(dialog).getByText("Después se vuelven a pasar las pruebas de este agente.")).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "Enseñar" }));
    expect(actions.teach).toHaveBeenCalledWith({ ref: REF, agent: RECEPCION, text: "Cerramos en agosto", scope: "agent" });
    expect(toast.success).toHaveBeenCalledWith("Aprendido. Solo lo sabe Recepción.", expect.objectContaining({ action: expect.anything() }));
    expect(onTaught).toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("al negocio: lo dice aquí, con su «Deshacer», que lo quita de la capa del negocio", async () => {
    const user = userEvent.setup();
    const { actions } = panel();
    await user.click(screen.getByRole("button", { name: "Enseñar" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByRole("textbox", { name: /Lo que debe saber/ }), "Cerramos en agosto");
    await user.click(within(dialog).getByRole("radio", { name: /Todo el negocio/ }));
    expect(within(dialog).getByText(/las pruebas de todos los agentes del cliente/)).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "Enseñar" }));
    expect(actions.teach).toHaveBeenCalledWith(expect.objectContaining({ scope: "business" }));
    const notice = await screen.findByText(/Todos los agentes saben ya «Cerramos en agosto»/);
    expect(notice).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Deshacer" }));
    expect(actions.forget).toHaveBeenCalledWith({ ref: REF, agent: RECEPCION, doc: DOC2, scope: "business" });
    await waitFor(() => expect(screen.queryByText(/Todos los agentes saben ya/)).toBeNull());
  });

  it("un error de la API se queda en el diálogo", async () => {
    const user = userEvent.setup();
    panel(knowledge(), { teach: vi.fn(async () => fail(422, "teach_too_long")) });
    await user.click(screen.getByRole("button", { name: "Enseñar" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByRole("textbox", { name: /Lo que debe saber/ }), "Algo");
    await user.click(within(dialog).getByRole("radio", { name: /Solo este agente/ }));
    await user.click(within(dialog).getByRole("button", { name: "Enseñar" }));
    expect(await within(dialog).findByText("Como mucho 5.000 caracteres.")).toBeVisible();
  });
});
