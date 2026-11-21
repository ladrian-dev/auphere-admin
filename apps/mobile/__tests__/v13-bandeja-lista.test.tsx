import { QueryClient, QueryClientProvider, type InfiniteData } from "@tanstack/react-query";
import { act, fireEvent, render as rtlRender, screen, waitFor, within } from "@testing-library/react-native";
import type { ReactElement } from "react";

import type { Conversation, ConversationPage } from "@/api/endpoints";
import { keys } from "@/api/query";
import { patchLists } from "@/features/inbox/list/row-actions";
import { dayGroupOf, inboxEntries, rowTime } from "@/features/inbox/model";
import { t as translate, type MessageKey } from "@/i18n/t";

/**
 * Spec 069, Requisitos 9 y 10 (T031, T032), Historias 3 y 4: the Bandeja by
 * day with who waits first, compact rows with their channel, the channel
 * selector, the search that spans the resolved, the swipes with «Deshacer»
 * and their accessibility actions, and what arrives (micro 3).
 */
const t = (k: MessageKey, v?: Record<string, string | number>) => translate("es", k, v);
const NOW = new Date();
const ago = (days: number, h = 0) => new Date(NOW.getTime() - days * 86_400_000 - h * 3_600_000).toISOString();

const conv = (id: string, o: Partial<Conversation> = {}): Conversation =>
  ({
    id,
    contact: { name: `Persona ${id}`, handle: "+34 600 000 000", initials: "PE", has_avatar: false },
    channel: { kind: "whatsapp" },
    agent: { id: "a1", name: "Recepción" },
    handled_by_agent: { id: "a1", name: "Recepción" },
    state: "agent",
    assignee: null,
    last_message: { at: NOW.toISOString(), author: { kind: "contact", name: null, is_me: false }, preview: "Hola", has_media: false },
    unread: false,
    tags: [],
    ...o,
  }) as Conversation;

type Page = { items: Conversation[]; next_cursor: null; counts: { unread: number; waiting: number }; has_any: boolean; channel_kinds: string[]; resolved: number };
const page = (items: Conversation[], kinds = ["whatsapp"]): { pages: Page[] } => ({
  pages: [{ items, next_cursor: null, counts: { unread: 1, waiting: 1 }, has_any: true, channel_kinds: kinds, resolved: 0 }],
});
const state = (o: Record<string, unknown> = {}) => ({ isPending: false, isError: false, isRefetchError: false, isFetchingNextPage: false, hasNextPage: false, refetch: jest.fn(), fetchNextPage: jest.fn(), dataUpdatedAt: 0, ...o });

const mockLists: { open: Record<string, unknown>; resolved: Record<string, unknown> } = { open: state(), resolved: state() };
const mockCalls = jest.fn();
jest.mock("@/api/v13-bandeja-hooks", () => ({
  useInboxList: (filter: string, q: string, agent: string | null, channel: string | null, enabled = true) => {
    mockCalls(filter, q, agent, channel, enabled);
    if (!enabled) return { data: undefined, isPending: true, hasNextPage: false, isFetchingNextPage: false, refetch: jest.fn(), fetchNextPage: jest.fn() };
    return filter === "resolved" && q !== "" ? mockLists.resolved : mockLists.open;
  },
  avatarSource: (id: string, headers: Record<string, string>) => ({ uri: id, headers }),
}));
jest.mock("@/api/v13-bandeja", () => ({ credentialHeaders: async () => ({ Authorization: "Bearer tok" }) }));
let mockAgents = [{ id: "a1", name: "Recepción" }];
jest.mock("@/api/hooks", () => ({
  useMe: () => ({ data: { agents: mockAgents, nav: ["panel", "inbox"] } }),
  useCounts: () => ({ data: { unread: 1, waiting: 1 }, refetch: jest.fn() }),
}));
jest.mock("@/api/sse", () => ({ useLiveStatus: () => "live" }));
const mockActions = jest.fn();
jest.mock("@/ui/actions", () => ({ useActions: () => mockActions }));
let mockOnline = true;
jest.mock("@/ui/online", () => ({ useOnline: () => mockOnline }));
const mockShow = jest.fn();
jest.mock("@/ui/toast", () => ({ useToast: () => ({ show: mockShow }) }));
const mockEndpoints = { resolve: jest.fn(), reopen: jest.fn(), markRead: jest.fn(), markUnread: jest.fn() };
// A getter: `row-actions` is imported above, before this file's constants exist.
jest.mock("@/api/endpoints", () => ({
  get endpoints() {
    return mockEndpoints;
  },
}));
const mockSwipes = new Map<string, { enabled: boolean; onSwipeableOpen: (d: string) => void }>();
jest.mock("react-native-gesture-handler/ReanimatedSwipeable", () => {
  const RN = jest.requireActual<typeof import("react-native")>("react-native");
  function Swipeable(p: { testID: string; enabled: boolean; onSwipeableOpen: (d: string) => void; children: ReactElement }) {
    mockSwipes.set(p.testID, p);
    return <RN.View testID={p.testID}>{p.children}</RN.View>;
  }
  return { __esModule: true, SwipeDirection: { LEFT: "left", RIGHT: "right" }, default: Swipeable };
});
const mockOptions: { current: Record<string, unknown> | null } = { current: null };
jest.mock("expo-router", () => {
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
jest.mock("expo-image", () => ({ Image: () => null }));

const Bandeja = require("@/app/(app)/bandeja/index").default;
let client: QueryClient;
const render = (ui: ReactElement) => rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);

beforeEach(() => {
  client = new QueryClient();
  mockLists.open = state();
  mockLists.resolved = state();
  mockCalls.mockClear();
  mockActions.mockClear();
  mockShow.mockClear();
  mockSwipes.clear();
  mockOnline = true;
  mockAgents = [{ id: "a1", name: "Recepción" }];
  for (const f of Object.values(mockEndpoints)) f.mockReset().mockResolvedValue({});
});

describe("by day, who waits first (R9.1, R9.3)", () => {
  it("Hoy, Ayer, Esta semana and Anteriores, in that order, each with how many", async () => {
    // The design's «today», Wednesday 18 November 2026 at 10:54, so «Esta semana» has room whatever day the suite runs.
    jest.useFakeTimers({ now: new Date(2026, 10, 18, 10, 54), advanceTimers: true });
    const at = (d: number, h: number) => new Date(2026, 10, d, h, 0).toISOString();
    const line = (when: string, preview: string) => ({ last_message: { at: when, author: { kind: "contact" as const, name: null, is_me: false }, preview, has_media: false } });
    mockLists.open = state({
      data: page([conv("t1", line(at(18, 9), "Hoy")), conv("y1", line(at(17, 9), "Ayer")), conv("w1", line(at(16, 9), "Semana")), conv("o1", line(at(12, 9), "Antes"))]),
    });
    await render(<Bandeja />);
    const headers = screen.getAllByRole("header").map((h) => h.props.accessibilityLabel);
    expect(headers).toEqual(["Hoy, 1", "Ayer, 1", "Esta semana, 1", "Anteriores, 1"]);
    jest.useRealTimers();
  });

  it("with more pages to come, the group says no number (R21)", async () => {
    mockLists.open = state({ data: page([conv("t1")]), hasNextPage: true });
    await render(<Bandeja />);
    expect(screen.getByRole("header", { name: "Hoy" })).toBeTruthy();
  });

  it("someone waiting since yesterday goes above today's", async () => {
    const waiting = conv("wait", {
      state: "waiting",
      last_message: { at: ago(1), author: { kind: "contact", name: null, is_me: false }, preview: "¿Me atiende alguien?", has_media: false },
    });
    mockLists.open = state({ data: page([conv("t1"), waiting]) });
    await render(<Bandeja />);
    const rows = screen.getAllByRole("button").filter((b) => /^Persona /.test(b.props.accessibilityLabel ?? ""));
    expect(rows[0]!.props.accessibilityLabel).toMatch(/^Persona wait\./);
    expect(screen.getByText("Esperan a una persona · 1")).toBeTruthy();
  });

  it("the day groups and the row's time, as pure decisions", () => {
    const now = new Date(2026, 10, 18, 10, 54);
    expect(dayGroupOf(new Date(2026, 10, 18, 8, 0).toISOString(), now)).toBe("today");
    expect(dayGroupOf(new Date(2026, 10, 17, 23, 0).toISOString(), now)).toBe("yesterday");
    // «Esta semana» is the calendar week (Monday on), as the design reads it: Wednesday 18 → Monday 16 is this week, Thursday 12 is not.
    expect(dayGroupOf(new Date(2026, 10, 16, 9, 0).toISOString(), now)).toBe("week");
    expect(dayGroupOf(new Date(2026, 10, 12, 9, 0).toISOString(), now)).toBe("older");
    expect(rowTime(new Date(2026, 10, 17, 9, 0).toISOString(), now, "es", t)).toBe("Ayer");
    expect(rowTime(new Date(2026, 10, 16, 9, 0).toISOString(), now, "es", t)).toBe("lun");
    expect(rowTime(new Date(2026, 10, 12, 9, 0).toISOString(), now, "es", t)).toBe("12 nov");
    const entries = inboxEntries([conv("a"), conv("b", { state: "waiting" })], now, { pinWaiting: true });
    expect(entries.map((e) => e.key)).toEqual(["h-waiting", "b", "h-older", "a"].map((k) => (k === "h-older" ? `h-${dayGroupOf(NOW.toISOString(), now)}` : k)));
  });
});

describe("compact rows (R9.1, R21.2)", () => {
  it("the channel's mark on the avatar, the unread dot, and the line with who wrote it — the agent by its name", async () => {
    mockLists.open = state({
      data: page([
        conv("ig", {
          channel: { kind: "instagram" },
          unread: true,
          last_message: { at: NOW.toISOString(), author: { kind: "agent", name: null, is_me: false }, preview: "Te esperamos", has_media: false },
        }),
        conv("me", { state: "person", assignee: { kind: "member", name: null, is_me: true }, last_message: { at: NOW.toISOString(), author: { kind: "member", name: null, is_me: true }, preview: "Hecho", has_media: false } }),
      ]),
    });
    await render(<Bandeja />);
    const ig = screen.getByTestId("conversation-ig");
    expect(within(ig).getByTestId("avatar-channel-instagram", { includeHiddenElements: true })).toBeTruthy();
    expect(within(ig).getByTestId("unread-dot")).toBeTruthy();
    expect(within(ig).getByText("Recepción: Te esperamos")).toBeTruthy();
    expect(ig.props.accessibilityLabel).toMatch(/^Persona ig\. Instagram\. Sin leer\./);
    const mine = screen.getByTestId("conversation-me");
    expect(within(mine).getByText("Tú")).toBeTruthy();
    expect(within(mine).getByText("Tú: Hecho")).toBeTruthy();
  });

  it("a preview that ends in a full stop is not read with two", async () => {
    mockLists.open = state({
      data: page([conv("dot", { last_message: { at: NOW.toISOString(), author: { kind: "contact", name: null, is_me: false }, preview: "Vale, mañana te digo.", has_media: false } })]),
    });
    await render(<Bandeja />);
    const label: string = screen.getByTestId("conversation-dot").props.accessibilityLabel;
    expect(label).toContain("Vale, mañana te digo.");
    expect(label).not.toMatch(/\.\./);
  });

  it("the agent answering says nothing on the row; who waits says «Espera»", async () => {
    mockLists.open = state({ data: page([conv("a1"), conv("w1", { state: "waiting" })]) });
    await render(<Bandeja />);
    expect(within(screen.getByTestId("conversation-a1")).queryByText("La atiende Recepción")).toBeNull();
    expect(within(screen.getByTestId("conversation-w1")).getByText("Espera")).toBeTruthy();
  });
});

describe("the channel (R9.2, R10.2, R10.3)", () => {
  it("one channel: no selector", async () => {
    mockLists.open = state({ data: page([conv("c1")], ["whatsapp"]) });
    await render(<Bandeja />);
    expect(screen.queryByRole("button", { name: /^Canal:/ })).toBeNull();
  });

  it("several: «Todos los canales», and choosing one reads that channel only", async () => {
    mockLists.open = state({ data: page([conv("c1")], ["instagram", "whatsapp"]) });
    await render(<Bandeja />);
    await fireEvent.press(screen.getByRole("button", { name: "Canal: Todos los canales" }));
    const [title, options] = mockActions.mock.calls[0] as [string, { label: string; onPress: () => void }[]];
    expect(title).toBe("Canal");
    expect(options.map((o) => o.label)).toEqual(["Todos los canales", "Instagram", "WhatsApp"]);
    await act(async () => options[1]!.onPress());
    expect(mockCalls).toHaveBeenLastCalledWith("resolved", "", null, "instagram", false);
    expect(mockCalls.mock.calls.some((c) => c[0] === "all" && c[3] === "instagram")).toBe(true);
    expect(screen.getByRole("button", { name: "Canal: Instagram" })).toBeTruthy();
  });
});

describe("search (R10)", () => {
  const typeIn = async (text: string) => {
    const search = mockOptions.current?.headerSearchBarOptions as { onChangeText: (e: { nativeEvent: { text: string } }) => void };
    await act(async () => search.onChangeText({ nativeEvent: { text } }));
  };

  it("spans the resolved too, in their own group, without pressing anything", async () => {
    mockLists.open = state({ data: page([conv("open1")]) });
    mockLists.resolved = state({ data: page([conv("done1", { state: "resolved" })]) });
    await render(<Bandeja />);
    await typeIn("seña");
    await waitFor(() => expect(mockCalls).toHaveBeenCalledWith("resolved", "seña", null, null, true));
    expect(mockCalls).toHaveBeenCalledWith("all", "seña", null, null, true);
    expect(screen.getByRole("header", { name: "Resueltas, 1" })).toBeTruthy();
    expect(screen.getByTestId("conversation-done1")).toBeTruthy();
    // The state chips step aside while searching.
    expect(screen.queryByRole("radio", { name: "Sin leer, 1" })).toBeNull();
  });

  it("nothing found: says what was searched, and offers to drop the channel", async () => {
    mockLists.open = state({ data: page([], ["instagram", "whatsapp"]) });
    mockLists.resolved = state({ data: page([]) });
    await render(<Bandeja />);
    await fireEvent.press(screen.getByRole("button", { name: "Canal: Todos los canales" }));
    const options = mockActions.mock.calls[0]![1] as { onPress: () => void }[];
    await act(async () => options[2]!.onPress());
    await typeIn("urgencia");
    await waitFor(() => expect(screen.getByText("Nada coincide con «urgencia»")).toBeTruthy());
    expect(screen.getByText(/Buscaste solo en WhatsApp\./)).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Quitar el filtro de canal" }));
    expect(mockCalls).toHaveBeenLastCalledWith("resolved", "urgencia", null, null, true);
  });
});

describe("swipes, «Deshacer» and the same actions for VoiceOver and TalkBack (R9.4, R3.4, Historia 4)", () => {
  it("left resolves, with «Deshacer» that reopens", async () => {
    mockLists.open = state({ data: page([conv("c1")]) });
    await render(<Bandeja />);
    await act(async () => mockSwipes.get("swipe-c1")!.onSwipeableOpen("left"));
    expect(mockEndpoints.resolve).toHaveBeenCalledWith("c1");
    const toast = mockShow.mock.calls.at(-1)![0] as { text: string; tone: string; action: { label: string; onPress: () => void } };
    expect(toast).toMatchObject({ text: "Resuelta", tone: "ok", action: { label: "Deshacer" } });
    await act(async () => toast.action.onPress());
    expect(mockEndpoints.reopen).toHaveBeenCalledWith("c1");
  });

  it("right marks it read or unread", async () => {
    mockLists.open = state({ data: page([conv("u1", { unread: true }), conv("r1")]) });
    await render(<Bandeja />);
    await act(async () => mockSwipes.get("swipe-u1")!.onSwipeableOpen("right"));
    expect(mockEndpoints.markRead).toHaveBeenCalledWith("u1");
    expect(mockShow.mock.calls.at(-1)![0]).toMatchObject({ text: "Marcada como leída" });
    await act(async () => mockSwipes.get("swipe-r1")!.onSwipeableOpen("right"));
    expect(mockEndpoints.markUnread).toHaveBeenCalledWith("r1");
    expect(mockShow.mock.calls.at(-1)![0]).toMatchObject({ text: "Marcada como no leída" });
  });

  it("a resolved one reopens, and the notice says who answers now", async () => {
    mockLists.open = state({ data: page([conv("d1", { state: "resolved" })]) });
    await render(<Bandeja />);
    await act(async () => mockSwipes.get("swipe-d1")!.onSwipeableOpen("left"));
    expect(mockEndpoints.reopen).toHaveBeenCalledWith("d1");
    expect(mockShow.mock.calls.at(-1)![0]).toMatchObject({ text: "Reabierta · la atiende Recepción" });
  });

  it("the row offers the same actions to the screen reader", async () => {
    mockLists.open = state({ data: page([conv("c1")]) });
    await render(<Bandeja />);
    const row = screen.getByTestId("conversation-c1");
    expect(row.props.accessibilityActions).toEqual([
      { name: "resolve", label: "Resolver" },
      { name: "unread", label: "Marcar como no leída" },
    ]);
    await fireEvent(row, "accessibilityAction", { nativeEvent: { actionName: "resolve" } });
    expect(mockEndpoints.resolve).toHaveBeenCalledWith("c1");
  });

  it("a failure says so and puts the row back", async () => {
    mockEndpoints.resolve.mockRejectedValue(new Error("no"));
    mockLists.open = state({ data: page([conv("c1")]) });
    await render(<Bandeja />);
    await act(async () => mockSwipes.get("swipe-c1")!.onSwipeableOpen("left"));
    expect(mockShow.mock.calls.at(-1)![0]).toMatchObject({ text: t("inbox.error.action"), tone: "warn" });
  });

  it("offline, nothing that writes: no swipe and no actions", async () => {
    mockOnline = false;
    mockLists.open = state({ data: page([conv("c1")]) });
    await render(<Bandeja />);
    expect(mockSwipes.get("swipe-c1")!.enabled).toBe(false);
    expect(screen.getByTestId("conversation-c1").props.accessibilityActions).toBeUndefined();
  });

  it("every loaded list changes at once: resolved leaves «Abiertas» and the read one loses its dot", () => {
    const qc = new QueryClient();
    const data = (items: Conversation[]): InfiniteData<ConversationPage> => ({ pages: [{ ...page(items).pages[0]!, items } as unknown as ConversationPage], pageParams: [null] });
    qc.setQueryData([...keys.conversations("all", "", null), null], data([conv("c1"), conv("c2", { unread: true })]));
    patchLists(qc, "c1", "resolve");
    patchLists(qc, "c2", "read");
    const all = qc.getQueryData<InfiniteData<ConversationPage>>([...keys.conversations("all", "", null), null])!;
    expect(all.pages[0]!.items.map((c) => [c.id, c.unread])).toEqual([["c2", false]]);
  });
});

describe("what arrives (R9.5, micro 3)", () => {
  it("a new conversation drops into its group; the first load and the others do not move", async () => {
    mockLists.open = state({ data: page([conv("c1")]) });
    const view = await render(<Bandeja />);
    expect(screen.queryByTestId("arrived-c1")).toBeNull();
    mockLists.open = state({ data: page([conv("n1"), conv("c1")]) });
    await view.rerender(
      <QueryClientProvider client={client}>
        <Bandeja />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("arrived-n1")).toBeTruthy();
    expect(screen.queryByTestId("arrived-c1")).toBeNull();
  });
});

describe("each filter's own empty (R3.1)", () => {
  it.each([
    ["Esperan a una persona, 1", "Nadie espera a una persona", "Cuando Recepción te necesite, la conversación aparece aquí y te llega un aviso."],
    ["Sin leer, 1", "Todo leído", "Los mensajes nuevos aparecerán aquí en cuanto lleguen."],
    ["Resueltas", "Nada resuelto todavía", "Marca una conversación como resuelta, o deslízala a la izquierda, y descansará aquí."],
  ])("%s empty: %s", async (chip, title, body) => {
    mockLists.open = state({ data: page([]) });
    await render(<Bandeja />);
    await fireEvent.press(screen.getByRole("radio", { name: chip }));
    expect(screen.getByText(title)).toBeTruthy();
    expect(screen.getByText(body)).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Ver las abiertas" }));
    expect(screen.getByRole("radio", { name: "Abiertas" }).props.accessibilityState).toEqual({ checked: true });
  });

  it("loading: a skeleton of the rows' size, named", async () => {
    mockLists.open = state({ isPending: true, data: undefined });
    await render(<Bandeja />);
    expect(screen.getByRole("progressbar", { name: "Cargando conversaciones" })).toBeTruthy();
  });
});
