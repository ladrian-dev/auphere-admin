import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { defaultConsolePolicy } from "@/components/agent-tools/settings-schema";
import { LocaleProvider } from "@/i18n/client";
import type { AgentDraft, AgentVersionEntry } from "@/lib/backend/agent-draft-types";

import { DraftEditsProvider } from "../draft-edits";
import { AgentPromptEditor } from "../prompt-editor";
import { AgentVersionHistory } from "../version-history";

/**
 * Spec 047, historia 2, escenario 3: el historial dice «v1 a v4 de ese
 * agente», cada una con su autor, su fecha, su nota y de cuál partió; el
 * borrador descartado se queda, dicho como tal. Y los cinco estados: sin
 * versiones, sin poder leerlas, y con lo que haya.
 */

const discardDraftAction = vi.fn();
const publishAgentAction = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/agent/actions", () => ({
  discardDraftAction: (...args: unknown[]) => discardDraftAction(...args),
}));
vi.mock("@/app/(console)/clients/actions", () => ({
  publishAgentAction: (...args: unknown[]) => publishAgentAction(...args),
  rollbackAgentAction: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));

const AGENT = "8f9e0d1c-2b3a-4c5d-8e6f-7a8b9c0d1e2f";

const draft: AgentDraft = {
  agent_id: AGENT,
  agent_name: "Recepción",
  revision: 7,
  exists: true,
  number: 4,
  version: 12,
  status: "staged",
  base_number: 2,
  active_number: 2,
  active_version: 6,
  author: "lucia@demo.test",
  created_at: "2026-10-26T09:00:00Z",
  updated_at: "2026-10-26T09:30:00Z",
  change_note: "Tono más cercano",
  system_prompt: "Cuatro.",
  tools: [],
  skills: [],
  settings: defaultConsolePolicy(),
  audience: { mode: "everyone", numbers: [], locked: false },
  payment_review: { reviewers: [] },
  screens: ["settings"],
  allowed: ["edit", "discard"],
};

const entry = (over: Partial<AgentVersionEntry>): AgentVersionEntry => ({
  number: 1,
  version: 1,
  status: "archived",
  author: "lucia@demo.test",
  created_at: "2026-10-20T09:00:00Z",
  published_at: "2026-10-20T10:00:00Z",
  published_by: "lucia@demo.test",
  change_note: null,
  base_number: null,
  ...over,
});

const FOUR: AgentVersionEntry[] = [
  entry({ number: 4, version: 12, status: "staged", published_at: null, published_by: null, change_note: "Tono más cercano", base_number: 2 }),
  entry({ number: 3, version: 9, published_at: null, published_by: null, author: "luis@demo.test", base_number: 2 }),
  entry({ number: 2, version: 6, status: "active", author: "Auphere", change_note: "Horario de verano", base_number: 1 }),
  entry({}),
];

function mount(entries: AgentVersionEntry[] | null, { withPrompt = false } = {}) {
  return render(
    <LocaleProvider locale="es">
      <DraftEditsProvider refId="demo" agentId={AGENT} initial={draft} canWrite>
        {withPrompt ? <AgentPromptEditor /> : null}
        <AgentVersionHistory entries={entries} prompts={{ 12: "Cuatro.", 6: "Dos." }} />
      </DraftEditsProvider>
    </LocaleProvider>,
  );
}

beforeEach(() => {
  discardDraftAction.mockReset();
  publishAgentAction.mockReset();
  refresh.mockReset();
});

describe("el historial del agente", () => {
  it("numera por agente, con autor, fecha, nota y versión de partida", () => {
    mount(FOUR);
    expect(screen.getByRole("heading", { name: "Versiones de Recepción" })).toBeInTheDocument();
    const rows = within(screen.getByRole("list", { name: "Versiones" })).getAllByRole("listitem");
    expect(rows.map((r) => within(r).getByText(/^v\d$/).textContent)).toEqual(["v4", "v3", "v2", "v1"]);
    expect(within(rows[0]!).getByText("Borrador")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("desde v2")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("Tono más cercano")).toBeInTheDocument();
    expect(within(rows[0]!).getByText(/lucia@demo\.test ·/)).toBeInTheDocument();
    // A draft somebody discarded stays, said as such — never as published.
    expect(within(rows[1]!).getByText("Descartada")).toBeInTheDocument();
    expect(within(rows[1]!).queryByText(/Publicada por/)).toBeNull();
    expect(within(rows[2]!).getByText("Activa")).toBeInTheDocument();
    expect(within(rows[2]!).getByText(/Publicada por lucia@demo\.test/)).toBeInTheDocument();
    expect(within(rows[3]!).getByText("Sin nota")).toBeInTheDocument();
    expect(within(rows[3]!).queryByText(/desde v/)).toBeNull();
  });

  it("sin versiones lo dice, y sin poder leerlas también, sin romper la página", () => {
    const { unmount } = mount([]);
    expect(screen.getByText("Todavía no hay versiones")).toBeInTheDocument();
    unmount();
    mount(null);
    expect(screen.getByRole("alert")).toHaveTextContent("No pudimos leer las versiones");
    fireEvent.click(screen.getByRole("button", { name: "Volver a intentarlo" }));
    expect(refresh).toHaveBeenCalled();
  });

  it("descartar el borrador manda la revisión que se leyó", async () => {
    discardDraftAction.mockResolvedValueOnce({ ok: true, data: { ...draft, exists: false, revision: 8, number: 2, status: "active" } });
    mount(FOUR);
    fireEvent.click(screen.getByRole("button", { name: /Opciones de la versión 4/ }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Descartar borrador" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Recepción sigue con la versión activa, que no cambia.");
    fireEvent.click(within(dialog).getByRole("button", { name: "Descartar" }));
    await waitFor(() => expect(discardDraftAction).toHaveBeenCalledWith({ ref: "demo", agent: AGENT, revision: 7 }));
  });

  it("no deja publicar el borrador con cambios sin guardar", async () => {
    mount(FOUR, { withPrompt: true });
    fireEvent.change(screen.getByRole("textbox", { name: "Instrucciones" }), { target: { value: "Cambio a medias." } });
    expect(await screen.findByText("Guarda los cambios antes de publicar: el borrador aún no los tiene.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Opciones de la versión 4/ }));
    const publish = await screen.findByRole("menuitem", { name: "Publicar" });
    expect(publish).toHaveAttribute("aria-disabled", "true");
  });
});
