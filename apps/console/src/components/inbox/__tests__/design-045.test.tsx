import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { ConversationRow } from "../conversation-row";
import { NOW, conversation, page } from "./fixtures";
import { InboxViewRef, renderInbox, resetActions } from "./view-harness";

vi.mock("@/app/(console)/inbox/actions", async () => (await import("./view-harness")).a);
vi.mock("../reload", () => ({ reloadPage: vi.fn() }));
InboxViewRef.current = (await import("../inbox-view")).InboxView;

const REASON = "Pide que le devuelvan la seña del pedido 4821. Los reembolsos los aprueba tu equipo y el agente no puede decidirlo solo.";
const twelveMinutesAgo = new Date(NOW.getTime() - 12 * 60_000).toISOString();
const AGENTS = [
  { id: "33333333-3333-4333-8333-333333333333", name: "Agente de soporte" },
  { id: "22222222-2222-4222-8222-222222222222", name: "Agente de ventas" },
];

function row(c = conversation()) {
  return render(
    <LocaleProvider locale="es">
      <ConversationRow conversation={c} selected={false} onOpen={vi.fn()} now={NOW} />
    </LocaleProvider>,
  );
}

/** Spec 045 (R3.1, R6.2): a waiting row says why and since when. */
describe("a conversation that waits for a person", () => {
  it("shows the agent's reason in two lines at most, the whole of it on hover and to a screen reader", () => {
    row(conversation({ state: "waiting", waiting: { reason: REASON, since: twelveMinutesAgo } }));
    const reason = screen.getByText(REASON);
    expect(reason).toHaveClass("line-clamp-2");
    expect(reason.getAttribute("title")).toBe(REASON);
    // The clamp is only visual: the row's name carries the whole reason.
    expect(screen.getByRole("button").textContent).toContain(REASON);
  });

  it("says how long it has waited", () => {
    row(conversation({ state: "waiting", waiting: { reason: REASON, since: twelveMinutesAgo } }));
    expect(screen.getByText("Espera hace 12 min")).toBeInTheDocument();
  });

  it("without a reason (an old escalation) the wait is still said, and nothing is invented", () => {
    row(conversation({ state: "waiting", waiting: { reason: null, since: twelveMinutesAgo } }));
    expect(screen.getByText("Espera hace 12 min")).toBeInTheDocument();
    expect(screen.getByText("Necesita humano")).toBeInTheDocument();
    expect(screen.getByRole("button").querySelector(".line-clamp-2")).toBeNull();
  });

  it("a conversation that does not wait has neither", () => {
    row(conversation({ state: "agent", waiting: null }));
    expect(screen.queryByText(/^Espera hace/)).toBeNull();
  });
});

/** Spec 045 (R6.2, R6.4): the Inbox's head names WhatsApp only, and the agents when there are several. */
describe("the Inbox's head", () => {
  beforeEach(resetActions);

  it("says who answers where, naming only WhatsApp", () => {
    const { unmount } = renderInbox();
    expect(screen.getByText("Tu agente responde en WhatsApp. Tú entras cuando hace falta.")).toBeInTheDocument();
    unmount();
    renderInbox({ agents: AGENTS });
    expect(screen.getByText("Tus agentes responden en WhatsApp. Tú entras cuando hace falta.")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/Instagram|Messenger/);
  });

  it("one agent: no «agentes activos» pill", () => {
    renderInbox();
    expect(screen.queryByRole("button", { name: /agentes activos/ })).toBeNull();
  });

  it("with several, the pill counts them and takes you to the agent filter", async () => {
    renderInbox({ agents: AGENTS, page: page([conversation()]) });
    const pill = screen.getByRole("button", { name: "2 agentes activos" });
    expect(pill.getAttribute("title")).toBe("Agente de soporte · Agente de ventas");
    await userEvent.click(pill);
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("combobox", { name: "Agente" })));
  });

  it("keeps the single filter of the 030: no channel tabs, no combinable chips", () => {
    renderInbox({ agents: AGENTS });
    const filters = screen.getByRole("group", { name: "Filtros" });
    expect(within(filters).getAllByRole("button").map((b) => b.textContent)).toEqual(["Todas", "Sin leer", "Necesita humano", "Resueltas"]);
    expect(screen.queryByRole("tab")).toBeNull();
  });
});
