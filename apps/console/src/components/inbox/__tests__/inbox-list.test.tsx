import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { InboxPage } from "@/lib/backend/inbox";

import { ConversationList } from "../conversation-list";
import { ME, NOW, conversation, page } from "./fixtures";

function view(p: InboxPage | null, o: Partial<Parameters<typeof ConversationList>[0]> = {}) {
  const props = {
    page: p,
    loading: false,
    failed: false,
    filter: "all" as const,
    query: "",
    agent: null as string | null,
    agents: [] as { id: string; name: string }[],
    counts: p?.counts ?? { unread: 0, waiting: 0 },
    selectedId: null,
    now: NOW,
    loadingMore: false,
    onFilter: vi.fn(),
    onQuery: vi.fn(),
    onAgent: vi.fn(),
    onOpen: vi.fn(),
    onMore: vi.fn(),
    onRetry: vi.fn(),
    onClear: vi.fn(),
    ...o,
  };
  render(
    <LocaleProvider locale="es">
      <ConversationList {...props} />
    </LocaleProvider>,
  );
  return props;
}

/** Spec 030 (R7, T053): the list, in each of its five states. */
describe("ConversationList", () => {
  it("loading: rows the size of real ones, announced", () => {
    view(null, { loading: true });
    expect(screen.getByRole("status", { name: "Cargando conversaciones" })).toBeInTheDocument();
  });

  it("an inbox that never had a conversation is not «no results»", () => {
    view(page([], { has_any: false }));
    expect(screen.getByText("Aún no hay conversaciones")).toBeInTheDocument();
    expect(screen.queryByText("No hay conversaciones con estos filtros.")).toBeNull();
  });

  it("filters that match nothing say so and offer the way back", async () => {
    const props = view(page([], { has_any: true }), { filter: "unread" });
    expect(screen.getByText("No hay conversaciones con estos filtros.")).toBeInTheDocument();
    expect(screen.queryByText("Aún no hay conversaciones")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Ver todas las conversaciones" }));
    expect(props.onClear).toHaveBeenCalled();
  });

  it("a failed read is an error, not an empty inbox — and not a dead end", async () => {
    const props = view(null, { failed: true });
    expect(screen.getByRole("alert")).toHaveTextContent("No pudimos cargar la bandeja");
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(props.onRetry).toHaveBeenCalled();
  });

  it("ideal: who, when, what, unread and state — and a row opens its conversation", async () => {
    const props = view(
      page(
        [
          conversation({ id: "a", unread: true }),
          conversation({
            id: "b",
            contact: { name: "Bruno Díaz", handle: "+54", initials: "BD" },
            state: "waiting",
            last_message: { at: "2026-10-07T18:00:00Z", author: { kind: "agent", name: null, is_me: false }, preview: "Te paso con una persona", has_media: false },
          }),
          conversation({
            id: "c",
            contact: { name: "Carla Gil", handle: "+54", initials: "CG" },
            state: "person",
            assignee: ME,
            last_message: { at: "2026-10-08T10:00:00Z", author: ME, preview: "Ya te lo reservo", has_media: false },
          }),
        ],
        { counts: { unread: 1, waiting: 1 } },
      ),
      { selectedId: "c" },
    );
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(within(rows[0]!).getByText("Sin leer")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("Agente: Te paso con una persona")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("Ayer")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("Necesita humano")).toBeInTheDocument();
    expect(within(rows[2]!).getByText("Tú: Ya te lo reservo")).toBeInTheDocument();
    expect(within(rows[2]!).getByText("Tú respondes")).toBeInTheDocument();
    expect(within(rows[2]!).getByRole("button")).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("button", { name: "Necesita humano · 1" })).toBeInTheDocument();

    await userEvent.click(within(rows[0]!).getByRole("button"));
    expect(props.onOpen).toHaveBeenCalledWith("a");
  });

  it("long names and previews are cut inside the row, never wrapped", () => {
    const long = "Donaudampfschifffahrtsgesellschaftskapitänswitwe Müller-Lüdenscheidt";
    view(page([conversation({ contact: { name: long, handle: "+49", initials: "DM" }, last_message: { at: "2026-10-08T11:00:00Z", author: { kind: "contact", name: null, is_me: false }, preview: long.repeat(3), has_media: false } })]));
    const name = screen.getByText(long);
    expect(name.className).toContain("truncate");
    expect(name.className).toContain("min-w-0");
  });

  it("filters are toggles and the search reports what was typed", async () => {
    const props = view(page([conversation()]));
    await userEvent.click(screen.getByRole("button", { name: "Sin leer" }));
    expect(props.onFilter).toHaveBeenCalledWith("unread");
    expect(screen.getByRole("button", { name: "Todas" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.type(screen.getByRole("searchbox", { name: "Buscar por nombre, teléfono o mensaje" }), "a");
    expect(props.onQuery).toHaveBeenCalledWith("a");
  });

  it("offers the next page when there is one", async () => {
    const props = view(page([conversation()], { next_cursor: "abc" }));
    await userEvent.click(screen.getByRole("button", { name: "Cargar más" }));
    expect(props.onMore).toHaveBeenCalled();
  });
});
