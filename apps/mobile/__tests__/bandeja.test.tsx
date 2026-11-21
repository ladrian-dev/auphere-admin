import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render as rtlRender, screen, waitFor } from "@testing-library/react-native";
import type { ReactElement } from "react";

import type { Conversation } from "@/api/endpoints";
import { badgeOf, eventText, previewOf, reasonText, waitingReasonText } from "@/features/inbox/model";
import { t as translate, type MessageKey } from "@/i18n/t";

/**
 * Spec 031 (T069, R5.1, R5.2, R14.5): the Bandeja's list. Spec 069 amends it
 * (R9.1, R9.2, R9.7, R10): the design's words for the filters and the rows, the
 * rest grouped by day under who waits, the list read with its channel through
 * `useInboxList`, a search that settles before it asks, and a footer that
 * names no channel. Its swipes and «Deshacer» are in `v13-bandeja-lista.test.tsx`.
 */
const t = (k: MessageKey, v?: Record<string, string | number>) => translate("es", k, v);

const conv = (o: Partial<Conversation> = {}): Conversation =>
  ({
    id: "c1",
    contact: { name: "Ana López", handle: "+34 600 000 000", initials: "AL", has_avatar: false },
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
}));
// Spec 069: the list goes with its channel (`v13-bandeja-hooks`); the search's resolved half is off unless searching.
jest.mock("@/api/v13-bandeja-hooks", () => ({
  useInboxList: (filter: string, q: string, agent: string | null, channel: string | null, enabled = true) => {
    if (enabled === false) return { data: undefined, isPending: true, hasNextPage: false, isFetchingNextPage: false, refetch: jest.fn(), fetchNextPage: jest.fn() };
    if (filter !== "resolved" || q === "") mockConversations(filter, q, agent, channel);
    return mockList.current;
  },
  avatarSource: (id: string, headers: Record<string, string>) => ({ uri: id, headers }),
}));
jest.mock("react-native-gesture-handler/ReanimatedSwipeable", () => {
  const RN = jest.requireActual<typeof import("react-native")>("react-native");
  return { __esModule: true, SwipeDirection: { LEFT: "left", RIGHT: "right" }, default: (p: { children: ReactElement }) => <RN.View>{p.children}</RN.View> };
});
jest.mock("@/ui/toast", () => ({ useToast: () => ({ show: jest.fn() }) }));
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

function page(items: Conversation[], has_any = items.length > 0, resolved = 0) {
  return { pages: [{ items, next_cursor: null, counts: { unread: 1, waiting: 2 }, has_any, channel_kinds: ["whatsapp"], resolved }] };
}
function list(o: Record<string, unknown>) {
  mockList.current = { isPending: false, isError: false, isRefetching: false, isFetchingNextPage: false, hasNextPage: false, refetch: jest.fn(), fetchNextPage: jest.fn(), dataUpdatedAt: 0, ...o };
}

const Bandeja = require("@/app/(app)/bandeja/index").default;
const render = (ui: ReactElement) => rtlRender(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);

describe("the list", () => {
  beforeEach(() => {
    mockConversations.mockClear();
    mockAgents = [{ id: "a1", name: "Recepción" }];
  });

  it("ideal: one spoken row per conversation, unread and its state in words", async () => {
    list({ data: page([conv()]) });
    await render(<Bandeja />);
    // Spec 069 (R9.1): the channel after the name, the state in the design's words.
    expect(screen.getByRole("button", { name: /^Ana López\. WhatsApp\. Sin leer\. Espera a una persona\. ¿Tenéis hueco\?/ })).toBeTruthy();
  });

  it("filters: all, unread, waiting and resolved — one chosen, with the counts the API gives", async () => {
    list({ data: page([conv()]) });
    await render(<Bandeja />);
    // Spec 056 calls «Todas» «Abiertas»; spec 069 (R9.2): «Esperan a una persona» and the counts as numbers after the label.
    for (const name of [t("inbox.filter.all"), "Sin leer, 1", "Esperan a una persona, 2", "Resueltas"]) expect(screen.getByRole("radio", { name })).toBeTruthy();
    expect(screen.getByRole("radio", { name: t("inbox.filter.all") }).props.accessibilityState).toEqual({ checked: true });
    await fireEvent.press(screen.getByRole("radio", { name: "Resueltas" }));
    expect(mockConversations).toHaveBeenLastCalledWith("resolved", "", null, null);
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

  it("searches by name or number from the native search bar, once the person stops typing (R10.1)", async () => {
    list({ data: page([conv()]) });
    await render(<Bandeja />);
    const search = mockOptions.current?.headerSearchBarOptions as { placeholder: string; onChangeText: (e: { nativeEvent: { text: string } }) => void };
    // Spec 069: the design's placeholder.
    expect(search.placeholder).toBe("Nombre, teléfono o mensaje");
    await act(async () => search.onChangeText({ nativeEvent: { text: "600" } }));
    await waitFor(() => expect(mockConversations).toHaveBeenLastCalledWith("all", "600", null, null));
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
    expect(screen.getByRole("button", { name: t("inbox.empty.clear") })).toBeTruthy();
  });

  /** Spec 056 (6.2, 6.3): «Abiertas» empty with resolved ones leads to them, not back to itself. */
  it("open and empty with resolved ones says how many and opens Resueltas", async () => {
    list({ data: page([], true, 2) });
    await render(<Bandeja />);
    expect(screen.getByText("No tienes conversaciones abiertas")).toBeTruthy();
    expect(screen.getByText("Tienes 2 resueltas.")).toBeTruthy();
    expect(screen.queryByText("No hay conversaciones con estos filtros.")).toBeNull();
    await fireEvent.press(screen.getByRole("button", { name: "Ver las resueltas" }));
    expect(mockConversations).toHaveBeenLastCalledWith("resolved", "", null, null);
  });

  it("one resolved reads in the singular; none at all is today's empty inbox, without a button", async () => {
    list({ data: page([], true, 1) });
    await render(<Bandeja />);
    expect(screen.getByText("Tienes 1 resuelta.")).toBeTruthy();
    list({ data: page([], false, 0) });
    await render(<Bandeja />);
    expect(screen.getByText("Aún no hay conversaciones")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Ver las resueltas" })).toBeNull();
  });
});

/** Spec 056 (7.1, 7.2): every reason through the table; a code never reaches the screen. */
describe("reasons in words", () => {
  it("a code of the table, its words; one it does not know, the generic sentence; the agent's own words as they are", () => {
    expect(reasonText("agent_unpublished", t)).toBe("Agente sin publicar");
    expect(reasonText("booking_unbacked", t)).toBe("El agente dio por hecha una cita que no existe");
    expect(reasonText("out_of_audience", t)).toBe("Fuera de su audiencia");
    expect(reasonText("brand_new_code", t)).toBe("El agente pidió ayuda");
    expect(reasonText("escalated", t)).toBe("El agente pidió ayuda");
    expect(reasonText("Pide que le devuelvan la seña", t)).toBe("Pide que le devuelvan la seña");
    expect(waitingReasonText("brand_new_code", t)).toBe("El agente pidió ayuda");
    expect(waitingReasonText(null, t)).toBeNull();
  });

  it("the thread and the activity: a code in words, the agent's words after the sentence", () => {
    const agent = { kind: "agent" as const, name: null, is_me: false };
    expect(eventText("escalated", agent, "agent_unpublished", t)).toBe("Agente sin publicar");
    expect(eventText("escalated", agent, "otro_codigo", t)).toBe("El agente pidió ayuda");
    expect(eventText("escalated", agent, "Pide un reembolso", t)).toBe("El agente pidió ayuda: Pide un reembolso");
  });

  it("a pinned row reads the code, once", async () => {
    const since = new Date(Date.now() - 60_000).toISOString();
    list({ data: page([conv({ id: "g1", waiting: { reason: "agent_unpublished", since }, waiting_reason: "agent_unpublished" })]) });
    await render(<Bandeja />);
    expect(screen.getAllByText("Agente sin publicar")).toHaveLength(1);
    expect(screen.queryByText("agent_unpublished")).toBeNull();
  });
});

describe("row words", () => {
  it("who wrote the last line", () => {
    expect(previewOf(conv({ last_message: { at: "", author: { kind: "member", name: "Yo", is_me: true }, preview: "Hola", has_media: false } }), t)).toBe("Tú: Hola");
    // Spec 069 (R21.2): the agent's line after its name, from the data.
    expect(previewOf(conv({ last_message: { at: "", author: { kind: "agent", name: null, is_me: false }, preview: "", has_media: true } }), t)).toBe("Recepción: Archivo");
    expect(previewOf(conv({ agent: null, last_message: { at: "", author: { kind: "agent", name: null, is_me: false }, preview: "", has_media: true } }), t)).toBe("Agente: Archivo");
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
  const other = conv({ id: "o1", state: "agent", contact: { name: "Benjamín Soto", handle: "+56 9 1111 2222", initials: "BS", has_avatar: false }, unread: false });

  it("with «Todas» and no search, they go first under «Esperan a una persona · N», with the reason and the wait", async () => {
    list({ data: page([other, waiting]) });
    await render(<Bandeja />);
    expect(screen.getByText("Esperan a una persona · 1")).toBeTruthy();
    // Spec 069 (R9.1): the rest by day, not «Las demás».
    expect(screen.getByText("Hoy")).toBeTruthy();
    expect(screen.getByText("Pide que le devuelvan la seña")).toBeTruthy();
    expect(screen.getByText("Espera hace 12 min")).toBeTruthy();
  });

  it("without the time from the API, the reason alone — never an invented wait (R10.2)", async () => {
    // 045 §2 always sends `since` with `waiting`; an older API sends no `waiting` at all: the plain preview, no time.
    list({ data: page([conv({ id: "w2", waiting: null, last_message: { at: new Date().toISOString(), author: { kind: "contact", name: "Ana", is_me: false }, preview: "Quiere hablar con alguien", has_media: false } })]) });
    await render(<Bandeja />);
    expect(screen.getByText("Quiere hablar con alguien")).toBeTruthy();
    expect(screen.queryByText(/hace \d/)).toBeNull();
  });

  it("says, at its foot, which conversations it shows — with the agent's name, and no channel (spec 069, R9.7)", async () => {
    list({ data: page([other]) });
    await render(<Bandeja />);
    expect(screen.getByText("Aquí solo están las conversaciones que atiende o atendió Recepción. El resto de tus chats no aparece.")).toBeTruthy();
    expect(screen.queryByText(/WhatsApp/)).toBeNull();
  });
});
