import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AgentSettingsForm } from "@/components/agent-tools/agent-settings-form";
import { defaultConsolePolicy } from "@/components/agent-tools/settings-schema";
import { LocaleProvider } from "@/i18n/client";
import type { AgentDraft, DraftChange } from "@/lib/backend/agent-draft-types";

import { DraftEditsProvider } from "../draft-edits";
import { AgentPromptEditor } from "../prompt-editor";
import { DraftSaveBar } from "../save-bar";

/**
 * Spec 047, historia 2 (T041): una sola barra de guardado en el agente y el
 * aviso de conflicto con los dos cambios.
 *
 * - Las instrucciones y los ajustes ya no tienen botón cada uno: la barra
 *   aparece cuando hay algo pendiente y guarda todo en UNA escritura, con la
 *   revisión que leyó la pantalla.
 * - Si otra persona guardó entre medias, la API responde 412: no se guardó
 *   nada de esta persona y la pantalla conserva lo que escribió, enseña lo que
 *   cambió la otra al lado de lo suyo, y deja elegir.
 */

const saveDraftAction = vi.fn();
const saveAgentSettingsAction = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/agent/actions", () => ({
  saveDraftAction: (...args: unknown[]) => saveDraftAction(...args),
  saveAgentSettingsAction: (...args: unknown[]) => saveAgentSettingsAction(...args),
}));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));

const AGENT = "8f9e0d1c-2b3a-4c5d-8e6f-7a8b9c0d1e2f";

function draft(over: Partial<AgentDraft> = {}): AgentDraft {
  return {
    agent_id: AGENT,
    agent_name: "Recepción",
    revision: 3,
    exists: true,
    number: 4,
    version: 9,
    status: "staged",
    base_number: 3,
    active_number: 3,
    active_version: 7,
    author: "lucia@demo.test",
    created_at: "2026-10-26T09:00:00Z",
    updated_at: "2026-10-26T09:30:00Z",
    change_note: null,
    system_prompt: "Atiende con calma.",
    tools: [],
    skills: [],
    settings: defaultConsolePolicy(),
    audience: { mode: "everyone", numbers: [], locked: false },
    payment_review: { reviewers: [] },
    screens: ["prompt"],
    allowed: ["edit", "discard"],
    ...over,
  };
}

function mount(initial: AgentDraft = draft(), { withSettings = false, canWrite = true } = {}) {
  return render(
    <LocaleProvider locale="es">
      <DraftEditsProvider refId="demo" agentId={AGENT} initial={initial} canWrite={canWrite}>
        <AgentPromptEditor />
        {withSettings ? (
          <AgentSettingsForm
            refId="demo"
            data={{
              version: initial.version,
              version_status: "staged",
              active_version: initial.active_version,
              has_draft: true,
              settings: initial.settings,
              audience: initial.audience,
              payment_review: initial.payment_review,
            }}
            canWrite={canWrite}
            actor="console:lucia@demo.test"
          />
        ) : null}
        <DraftSaveBar />
      </DraftEditsProvider>
    </LocaleProvider>,
  );
}

const prompt = () => screen.getByRole("textbox", { name: "Instrucciones" });
const bar = () => screen.queryByRole("region", { name: "Cambios sin guardar" });
const saveButton = () => screen.getByRole("button", { name: "Guardar" });

function conflict(changes: DraftChange[], current: Partial<AgentDraft> = {}) {
  return {
    ok: false,
    status: 412,
    message: "",
    code: "revision_conflict",
    info: { current: draft({ revision: 5, ...current }), changes },
  };
}

const byLuis: DraftChange = {
  revision: 4,
  kind: "edit",
  by: "luis@demo.test",
  at: "2026-10-26T10:00:00Z",
  fields: ["settings.tone", "system_prompt"],
};

beforeEach(() => {
  saveDraftAction.mockReset();
  saveAgentSettingsAction.mockReset();
  refresh.mockReset();
});

describe("la barra de guardado del agente", () => {
  it("no está mientras no hay nada que guardar, y aparece diciendo dónde hay cambios", () => {
    mount();
    expect(bar()).toBeNull();
    expect(screen.getByText("Borrador v4 de Recepción, desde v3")).toBeInTheDocument();
    fireEvent.change(prompt(), { target: { value: "Atiende rápido." } });
    expect(within(bar()!).getAllByText("Cambios sin guardar en Instrucciones").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "Guardar" })).toHaveLength(1);
  });

  it("guarda en una escritura con la revisión que leyó, y se va", async () => {
    saveDraftAction.mockResolvedValueOnce({ ok: true, data: draft({ revision: 4, system_prompt: "Atiende rápido." }) });
    mount();
    fireEvent.change(prompt(), { target: { value: "Atiende rápido." } });
    fireEvent.change(screen.getByLabelText("Nota del cambio (opcional)"), { target: { value: "Más corto" } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(bar()).toBeNull());
    expect(saveDraftAction).toHaveBeenCalledTimes(1);
    expect(saveDraftAction).toHaveBeenCalledWith({
      ref: "demo",
      agent: AGENT,
      revision: 3,
      patch: { system_prompt: "Atiende rápido.", note: "Más corto" },
    });
    expect(prompt()).toHaveValue("Atiende rápido.");
    expect(refresh).toHaveBeenCalled();
  });

  it("las instrucciones y los ajustes van juntos: un solo botón, una sola escritura", async () => {
    saveDraftAction.mockResolvedValueOnce({ ok: true, data: draft({ revision: 4 }) });
    mount(draft(), { withSettings: true });
    // The settings form has no button of its own inside the bar.
    expect(screen.queryByRole("button", { name: "Guardar borrador" })).toBeNull();
    fireEvent.change(prompt(), { target: { value: "Vende pan." } });
    fireEvent.change(screen.getByRole("textbox", { name: "Objetivo" }), { target: { value: "vender pan" } });
    await waitFor(() =>
      expect(within(bar()!).getAllByText("Cambios sin guardar en Instrucciones y Ajustes").length).toBeGreaterThan(0),
    );
    fireEvent.click(saveButton());
    await waitFor(() => expect(saveDraftAction).toHaveBeenCalledTimes(1));
    const { patch, revision } = saveDraftAction.mock.calls[0]![0] as { patch: Record<string, unknown>; revision: number };
    expect(revision).toBe(3);
    expect(patch.system_prompt).toBe("Vende pan.");
    expect((patch.settings as { objective: string }).objective).toBe("vender pan");
    expect(patch.audience).toEqual({ mode: "everyone", numbers: [] });
    expect(saveAgentSettingsAction).not.toHaveBeenCalled();
  });

  it("una instrucción vacía no viaja", async () => {
    mount();
    fireEvent.change(prompt(), { target: { value: "   " } });
    fireEvent.click(saveButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("Escribe las instrucciones antes de guardar.");
    expect(saveDraftAction).not.toHaveBeenCalled();
  });

  it("quien solo lee no tiene barra", () => {
    mount(draft(), { canWrite: false });
    expect(prompt()).toHaveAttribute("readonly");
    expect(screen.getByText("Puedes leer el borrador, pero tu rol no puede cambiarlo.")).toBeInTheDocument();
    expect(bar()).toBeNull();
  });
});

describe("el aviso de conflicto", () => {
  it("enseña los dos cambios, avisa de lo que tocaron los dos y no pierde lo escrito", async () => {
    saveDraftAction.mockResolvedValueOnce(conflict([byLuis], { system_prompt: "El de Luis." }));
    mount();
    fireEvent.change(prompt(), { target: { value: "El mío." } });
    fireEvent.click(saveButton());

    const heading = await screen.findByRole("heading", { name: "Hay cambios más nuevos de luis@demo.test" });
    await waitFor(() => expect(heading).toHaveFocus());
    const notice = heading.closest("section")!;
    const theirs = within(notice).getByRole("heading", { name: /Sus cambios/ }).parentElement!;
    expect(within(theirs).getByText("Tono")).toBeInTheDocument();
    expect(within(theirs).getByText("Instrucciones")).toBeInTheDocument();
    const mine = within(notice).getByRole("heading", { name: "Tus cambios, sin guardar" }).parentElement!;
    expect(within(mine).getByText("Instrucciones")).toBeInTheDocument();
    expect(within(notice).getByText(/Los dos habéis cambiado Instrucciones/)).toBeInTheDocument();
    // Both versions of the instructions, side by side.
    expect(within(notice).getByText("El de Luis.")).toBeInTheDocument();
    expect(within(notice).getAllByText("El mío.").length).toBeGreaterThan(0);
    // What this person wrote is still on screen, and the bar waits for a decision.
    expect(prompt()).toHaveValue("El mío.");
    expect(saveButton()).toBeDisabled();
  });

  it("«Guardar los míos encima» vuelve a escribir con la revisión nueva", async () => {
    saveDraftAction
      .mockResolvedValueOnce(conflict([byLuis], { system_prompt: "El de Luis." }))
      .mockResolvedValueOnce({ ok: true, data: draft({ revision: 6, system_prompt: "El mío." }) });
    mount();
    fireEvent.change(prompt(), { target: { value: "El mío." } });
    fireEvent.click(saveButton());
    fireEvent.click(await screen.findByRole("button", { name: "Guardar los míos encima" }));
    await waitFor(() => expect(saveDraftAction).toHaveBeenCalledTimes(2));
    expect(saveDraftAction.mock.calls[1]![0]).toEqual({
      ref: "demo",
      agent: AGENT,
      revision: 5,
      patch: { system_prompt: "El mío." },
    });
    await waitFor(() => expect(bar()).toBeNull());
    expect(prompt()).toHaveValue("El mío.");
  });

  it("«Quedarme con los suyos» enseña su borrador y deja lo mío sin guardar", async () => {
    saveDraftAction.mockResolvedValueOnce(conflict([byLuis], { system_prompt: "El de Luis." }));
    mount();
    fireEvent.change(prompt(), { target: { value: "El mío." } });
    fireEvent.click(saveButton());
    fireEvent.click(await screen.findByRole("button", { name: "Quedarme con los suyos" }));
    await waitFor(() => expect(prompt()).toHaveValue("El de Luis."));
    expect(bar()).toBeNull();
    expect(saveDraftAction).toHaveBeenCalledTimes(1);
  });

  it("si lo que pasó fue publicar, lo dice", async () => {
    saveDraftAction.mockResolvedValueOnce(
      conflict([{ ...byLuis, kind: "publish", fields: [] }], { exists: false, status: "active" }),
    );
    mount();
    fireEvent.change(prompt(), { target: { value: "El mío." } });
    fireEvent.click(saveButton());
    expect(await screen.findByRole("heading", { name: "luis@demo.test publicó el borrador mientras editabas" })).toBeInTheDocument();
    expect(screen.getByText("Sin cambios de campos")).toBeInTheDocument();
  });
});
