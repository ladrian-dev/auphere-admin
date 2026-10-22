import { act, fireEvent, render, screen } from "@testing-library/react-native";

import type { Conversation } from "@/api/endpoints";
import { badgeOf, previewOf } from "@/features/inbox/model";
import { t as translate, type MessageKey } from "@/i18n/t";

/**
 * Spec 031 (T069, R5.1, R5.2, R14.5): the Bandeja's list. Swipe actions are
 * out of v1 — every action lives in the conversation's menu — so there is no
 * gesture without its button, and no «Deshacer» to offer.
 */
const t = (k: MessageKey, v?: Record<string, string | number>) => translate("es", k, v);

const conv = (o: Partial<Conversation> = {}): Conversation =>
  ({
    id: "c1",
    contact: { name: "Ana López", handle: "+34 600 000 000", initials: "AL" },
    channel: { kind: "whatsapp" },
    agent: { id: "a1", name: "Recepción" },
    state: "waiting",
    assignee: null,
    last_message: { at: new Date().toISOString(), author: { kind: "contact", name: "Ana", is_me: false }, preview: "¿Tenéis hueco?", has_media: false },
    unread: true,
    tags: [],
    ...o,
  }) as Conversation;

const mockList = { current: {} as Record<string, unknown> };
const mockConversations = jest.fn();
let mockAgents = [{ id: "a1", name: "Recepción" }];
const mockOptions: { current: Record<string, unknown> | null } = { current: null };

jest.mock("@/api/hooks", () => ({
  useMe: () => ({ data: { agents: mockAgents, nav: ["panel", "inbox"] } }),
  useCounts: () => ({ data: { unread: 1, waiting: 2 }, refetch: jest.fn() }),
  useConversations: (...a: unknown[]) => {
    mockConversations(...a);
    return mockList.current;
  },
}));
jest.mock("@/api/sse", () => ({ useLiveStatus: () => "live" }));
jest.mock("@/ui/actions", () => ({ useActions: () => jest.fn() }));
jest.mock("@/ui/online", () => ({ useOnline: () => true }));
jest.mock("expo-router", () => {
  // The settings bar button (spec 042, SettingsToolbar) renders nothing here.
  function Toolbar() {
    return null;
  }
  Toolbar.Button = function ToolbarButton() {
    return null;
  };
  return {
    router: { push: jest.fn() },
    Stack: { Screen: ({ options }: { options: Record<string, unknown> }) => ((mockOptions.current = options), null), Toolbar },
  };
});

function page(items: Conversation[], has_any = items.length > 0) {
  return { pages: [{ items, next_cursor: null, counts: { unread: 1, waiting: 2 }, has_any, channel_kinds: ["whatsapp"] }] };
}
function list(o: Record<string, unknown>) {
  mockList.current = { isPending: false, isError: false, isRefetching: false, isFetchingNextPage: false, hasNextPage: false, refetch: jest.fn(), fetchNextPage: jest.fn(), dataUpdatedAt: 0, ...o };
}

const Bandeja = require("@/app/(app)/bandeja/index").default;

describe("the list", () => {
  beforeEach(() => {
    mockConversations.mockClear();
    mockAgents = [{ id: "a1", name: "Recepción" }];
  });

  it("ideal: one spoken row per conversation, unread and its state in words", async () => {
    list({ data: page([conv()]) });
    await render(<Bandeja />);
    expect(screen.getByRole("button", { name: /^Ana López\. Sin leer\. Necesita humano\. ¿Tenéis hueco\?/ })).toBeTruthy();
  });

  it("filters: all, unread, waiting (with its count) and resolved — one chosen", async () => {
    list({ data: page([conv()]) });
    await render(<Bandeja />);
    for (const name of ["Todas", "Sin leer", "Necesita humano · 2", "Resueltas"]) expect(screen.getByRole("radio", { name })).toBeTruthy();
    expect(screen.getByRole("radio", { name: "Todas" }).props.accessibilityState).toEqual({ checked: true });
    await fireEvent.press(screen.getByRole("radio", { name: "Resueltas" }));
    expect(mockConversations).toHaveBeenLastCalledWith("resolved", "", null);
  });

  it("the agent filter only with more than one agent", async () => {
    list({ data: page([conv()]) });
    await render(<Bandeja />);
    expect(screen.queryByRole("button", { name: "Todos los agentes" })).toBeNull();
    mockAgents = [
      { id: "a1", name: "Recepción" },
      { id: "a2", name: "Ventas" },
    ];
    await render(<Bandeja />);
    expect(screen.getByRole("button", { name: "Todos los agentes" })).toBeTruthy();
  });

  it("searches by name or number from the native search bar", async () => {
    list({ data: page([conv()]) });
    await render(<Bandeja />);
    const search = mockOptions.current?.headerSearchBarOptions as { placeholder: string; onChangeText: (e: { nativeEvent: { text: string } }) => void };
    expect(search.placeholder).toBe("Buscar por nombre, teléfono o mensaje");
    await act(async () => search.onChangeText({ nativeEvent: { text: "600" } }));
    expect(mockConversations).toHaveBeenLastCalledWith("all", "600", null);
  });

  it("the search bar's icon, text and hint come from the theme, so they read in dark mode on Android (spec 042, H23)", async () => {
    const { tokens } = require("@/theme/tokens.gen") as typeof import("@/theme/tokens.gen");
    list({ data: page([conv()]) });
    await render(<Bandeja />);
    const search = mockOptions.current?.headerSearchBarOptions as Record<string, unknown>;
    expect(search.headerIconColor).toBe(tokens.light.primaryText);
    expect(search.textColor).toBe(tokens.light.foreground);
    expect(search.hintTextColor).toBe(tokens.light.mutedForeground);
  });

  it("loading: a named skeleton", async () => {
    list({ isPending: true, data: undefined });
    await render(<Bandeja />);
    expect(screen.getByRole("progressbar", { name: "Cargando conversaciones" })).toBeTruthy();
  });

  it("error: an alert with retry, not an empty inbox", async () => {
    list({ isError: true, data: undefined });
    await render(<Bandeja />);
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.queryByText("Aún no hay conversaciones")).toBeNull();
  });

  it("empty inbox and empty filter say different things", async () => {
    list({ data: page([], false) });
    await render(<Bandeja />);
    expect(screen.getByText("Aún no hay conversaciones")).toBeTruthy();
    list({ data: page([], true) });
    await render(<Bandeja />);
    expect(screen.getByText("No hay conversaciones con estos filtros.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Ver todas las conversaciones" })).toBeTruthy();
  });
});

describe("row words", () => {
  it("who wrote the last line", () => {
    expect(previewOf(conv({ last_message: { at: "", author: { kind: "member", name: "Yo", is_me: true }, preview: "Hola", has_media: false } }), t)).toBe("Tú: Hola");
    expect(previewOf(conv({ last_message: { at: "", author: { kind: "agent", name: null, is_me: false }, preview: "", has_media: true } }), t)).toBe("Agente: Archivo");
  });

  it("the state badge", () => {
    expect(badgeOf(conv(), t)?.label).toBe("Necesita humano");
    expect(badgeOf(conv({ state: "person", assignee: { kind: "member", name: "Luis", is_me: false } }), t)?.label).toBe("Luis responde");
    expect(badgeOf(conv({ state: "person", assignee: { kind: "member", name: null, is_me: true } }), t)?.label).toBe("Tú respondes");
    expect(badgeOf(conv({ state: "agent" }), t)).toBeNull();
  });
});

/**
 * Spec 044, Historia 6, Requisito 10: the ones waiting for a person, pinned on
 * top with the agent's reason and how long they have waited; the rule of
 * what the Bandeja shows, said at its foot.
 */
describe("the waiting ones, pinned (spec 044, R10)", () => {
  const since = new Date(Date.now() - 12 * 60_000).toISOString();
  const waiting = conv({ id: "w1", waiting: { reason: "Pide que le devuelvan la seña", since } });
  const other = conv({ id: "o1", state: "agent", contact: { name: "Benjamín Soto", handle: "+56 9 1111 2222", initials: "BS" }, unread: false });

  it("with «Todas» and no search, they go first under «Esperan a una persona · N», with the reason and the wait", async () => {
    list({ data: page([other, waiting]) });
    await render(<Bandeja />);
    expect(screen.getByText("Esperan a una persona · 1")).toBeTruthy();
    expect(screen.getByText("Las demás")).toBeTruthy();
    expect(screen.getByText("Pide que le devuelvan la seña")).toBeTruthy();
    expect(screen.getByText("Necesita humano · hace 12 min")).toBeTruthy();
  });

  it("without the time from the API, the reason alone — never an invented wait (R10.2)", async () => {
    // 045 §2 always sends `since` with `waiting`; an older API sends no `waiting` at all: the plain preview, no time.
    list({ data: page([conv({ id: "w2", waiting: null, last_message: { at: new Date().toISOString(), author: { kind: "contact", name: "Ana", is_me: false }, preview: "Quiere hablar con alguien", has_media: false } })]) });
    await render(<Bandeja />);
    expect(screen.getByText("Quiere hablar con alguien")).toBeTruthy();
    expect(screen.queryByText(/hace \d/)).toBeNull();
  });

  it("says, at its foot, which conversations it shows", async () => {
    list({ data: page([other]) });
    await render(<Bandeja />);
    expect(screen.getByText("Aquí solo están las conversaciones que atiende o atendió tu agente. El resto de chats de tu WhatsApp no aparece.")).toBeTruthy();
  });
});
