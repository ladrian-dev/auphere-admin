import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { conversation, detail, page } from "./fixtures";
import { InboxViewRef, a, renderInbox, resetActions } from "./view-harness";

vi.mock("@/app/(console)/inbox/actions", async () => (await import("./view-harness")).a);
vi.mock("../reload", () => ({ reloadPage: vi.fn() }));
InboxViewRef.current = (await import("../inbox-view")).InboxView;

const SALES = "22222222-2222-4222-8222-222222222222";
const MAIN = "33333333-3333-4333-8333-333333333333";
const AGENTS = [
  { id: MAIN, name: "Agente principal" },
  { id: SALES, name: "Ventas" },
];
const ID = "11111111-1111-4111-8111-111111111111";

/**
 * Spec 030, iteration 3 (R4.2, T096): a client with more than one agent sees
 * whose number each conversation came in on and can narrow the list to one
 * agent. With one agent none of it is there — a one-item choice says nothing.
 */
describe("Inbox with several agents", () => {
  beforeEach(resetActions);

  it("one agent: no agent selector and no agent tag", () => {
    renderInbox();
    expect(screen.queryByRole("combobox", { name: "Agente" })).toBeNull();
    expect(screen.queryByText(/^Agente:/)).toBeNull();
  });

  it("each row carries its agent's name", () => {
    renderInbox({
      agents: AGENTS,
      page: page([conversation({ agent: { id: SALES, name: "Ventas" } })]),
    });
    const row = screen.getByRole("button", { name: /Ana Torres/ });
    expect(within(row).getByText("Ventas")).toBeInTheDocument();
    expect(within(row).getByText("Agente:")).toHaveClass("sr-only");
  });

  it("choosing an agent re-reads the list for it and keeps it in the URL", async () => {
    renderInbox({ agents: AGENTS });
    const select = screen.getByRole("combobox", { name: "Agente" });
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Todos los agentes",
      "Agente principal",
      "Ventas",
    ]);

    await userEvent.selectOptions(select, SALES);
    await waitFor(() =>
      expect(a.listConversationsAction).toHaveBeenLastCalledWith({ filter: "all", q: undefined, agent: SALES }),
    );
    expect(window.location.search).toBe(`?agent=${SALES}`);

    await userEvent.selectOptions(select, "");
    await waitFor(() =>
      expect(a.listConversationsAction).toHaveBeenLastCalledWith({ filter: "all", q: undefined, agent: undefined }),
    );
    expect(window.location.search).toBe("");
  });

  it("«see all» from an empty filtered list also drops the agent", async () => {
    a.listConversationsAction.mockResolvedValue({ ok: true, data: page([], { has_any: true }) });
    renderInbox({ agents: AGENTS, agent: SALES, page: page([], { has_any: true }) });
    await userEvent.click(screen.getByRole("button", { name: "Ver todas las conversaciones" }));
    await waitFor(() =>
      expect(a.listConversationsAction).toHaveBeenLastCalledWith({ filter: "all", q: undefined, agent: undefined }),
    );
  });

  it("the header names the agent answering, when there is more than one", () => {
    renderInbox({
      agents: AGENTS,
      selectedId: ID,
      open: { detail: detail({ agent: { id: SALES, name: "Ventas" } }), thread: { items: [], next_before: null } },
    });
    expect(screen.getByText("Atiende: Ventas")).toBeInTheDocument();
  });
});
