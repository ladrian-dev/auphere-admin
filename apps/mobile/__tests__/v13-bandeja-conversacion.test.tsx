import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react-native";
import type { ReactNode } from "react";
import { Alert, Linking, Platform } from "react-native";

import type { ThreadItem } from "@/api/endpoints";
import { keys } from "@/api/query";
import { t as translate, type MessageKey } from "@/i18n/t";

/**
 * Spec 069, Requisito 11 (T033) and Historia 2: the conversation's header,
 * «Tomar el control» with its choreography and «Devolver», the menu with
 * «Vaciar chat» and «Eliminar chat», the comment's post, and sending.
 */
const t = (k: MessageKey, v?: Record<string, string | number>) => translate("es", k, v);

const mockShow = jest.fn();
jest.mock("@/ui/toast", () => ({ useToast: () => ({ show: mockShow }) }));
const mockBack = jest.fn();
jest.mock("expo-router", () => {
  const RN = jest.requireActual<typeof import("react-native")>("react-native");
  function Toolbar(p: { children?: React.ReactNode; placement?: string }) {
    return <RN.View testID={`toolbar-${p.placement}`}>{p.children}</RN.View>;
  }
  Toolbar.Menu = function ToolbarMenu(p: { children?: React.ReactNode }) {
    return <RN.View>{p.children}</RN.View>;
  };
  Toolbar.MenuAction = function ToolbarMenuAction(p: { children?: string; onPress?: () => void; disabled?: boolean; destructive?: boolean }) {
    return (
      <RN.Pressable testID="toolbar-menu-action" accessibilityRole="menuitem" accessibilityLabel={p.children} accessibilityState={{ disabled: !!p.disabled }} accessibilityHint={p.destructive ? "destructive" : undefined} onPress={p.onPress}>
        <RN.Text>{p.children}</RN.Text>
      </RN.Pressable>
    );
  };
  return { Stack: { Toolbar, Screen: () => null }, router: { push: jest.fn(), back: (...a: unknown[]) => mockBack(...a) } };
});
const mockApi = { clear: jest.fn(), archive: jest.fn(), post: jest.fn() };
jest.mock("@/api/v13-bandeja", () => ({
  get bandejaApi() {
    return mockApi;
  },
  avatarUrl: (id: string) => `http://api/console/lite/inbox/conversations/${id}/avatar`,
  credentialHeaders: async () => null,
}));
const mockEndpoints = { markRead: jest.fn(), reopen: jest.fn() };
jest.mock("@/api/endpoints", () => ({
  get endpoints() {
    return mockEndpoints;
  },
}));
jest.mock("@/features/inbox/thread/media", () => ({ mediaUrl: (id: string) => id, mediaHeaders: async () => null }));
jest.mock("expo-image", () => ({ Image: () => null }));

const { useChatActions } = require("@/features/inbox/thread/chat-actions") as typeof import("@/features/inbox/thread/chat-actions");
const { ConversationToolbar, ConversationTitle, conversationMenu } = require("@/features/inbox/thread/toolbar") as typeof import("@/features/inbox/thread/toolbar");
const { TAKE_OVER, TAKE_OVER_SETTLED_MS, takeOverMotion } = require("@/features/inbox/thread/choreography") as typeof import("@/features/inbox/thread/choreography");
const { ThreadFoot } = require("@/features/inbox/thread/foot") as typeof import("@/features/inbox/thread/foot");
const { Composer } = require("@/features/inbox/thread/composer") as typeof import("@/features/inbox/thread/composer");
const { CommentPost } = require("@/features/inbox/thread/comment-post") as typeof import("@/features/inbox/thread/comment-post");
const { MessageBubble } = require("@/features/inbox/thread/bubble") as typeof import("@/features/inbox/thread/bubble");

const noop = () => undefined;
let qc: QueryClient;
const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;

beforeEach(() => {
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  mockShow.mockClear();
  mockBack.mockClear();
  for (const f of [...Object.values(mockApi), ...Object.values(mockEndpoints)]) f.mockReset();
});

const fakeAct = () => ({
  takeOver: jest.fn(async () => true),
  giveBack: jest.fn(async () => true),
  markUnread: jest.fn(async () => true),
  resolve: jest.fn(async () => true),
});
const chat = async (a = fakeAct(), agent: string | null = "Recepción") => {
  const { result } = await renderHook(() => useChatActions("c1", t, a as never, agent), { wrapper });
  return { result, a };
};

describe("«Tomar el control» (R2.3, 044 R16.7 amended)", () => {
  it("says that you answer now, with «Devolver» — which uses the version the takeover answered", async () => {
    const { result, a } = await chat();
    await act(async () => result.current.takeOver(3));
    expect(a.takeOver).toHaveBeenCalledWith(3);
    const toast = mockShow.mock.calls.at(-1)![0] as { text: string; action: { label: string; onPress: () => void } };
    expect(toast.text).toBe("Ahora respondes tú. Recepción deja de responder aquí.");
    expect(toast.action.label).toBe("Devolver");
    qc.setQueryData(keys.conversation("c1"), { control_version: 4 });
    await act(async () => toast.action.onPress());
    expect(a.giveBack).toHaveBeenCalledWith(4);
  });

  it("if it did not go through, no notice", async () => {
    const a = fakeAct();
    a.takeOver.mockResolvedValue(false);
    const { result } = await chat(a);
    await act(async () => result.current.takeOver(3));
    expect(mockShow).not.toHaveBeenCalled();
  });

  it("the choreography: the strip folds in 120 ms, 40 ms, the box rises in 240 ms — at once with reduced motion", () => {
    expect(TAKE_OVER).toEqual({ fold: 120, pause: 40, rise: 240 });
    expect(TAKE_OVER_SETTLED_MS).toBe(400);
    const m = takeOverMotion(false) as unknown as { fold: { name: string; ms: number }; rise: { name: string; ms: number } };
    expect([m.fold.name, m.fold.ms, m.rise.name, m.rise.ms]).toEqual(["FadeOutDown", 120, "FadeInDown", 240]);
    const r = takeOverMotion(true) as unknown as { fold: { name: string }; rise: { name: string } };
    expect([r.fold.name, r.rise.name]).toEqual(["FadeOut", "FadeIn"]);
  });

  it("waiting, the action names who waits: «Atender a Lucía»", async () => {
    await render(
      <ThreadFoot
        mode={{ kind: "waiting", reason: "Pide la seña" }}
        busy={false}
        online
        t={t}
        replies={null}
        focusSignal={0}
        onTakeOver={noop}
        onGiveBack={noop}
        onReopen={noop}
        onReadMore={noop}
        onSend={noop}
        onAttach={noop}
        onReplies={noop}
        contactName="Lucía Fernández"
      />,
    );
    expect(screen.getByRole("button", { name: "Atender a Lucía" })).toBeTruthy();
  });
});

describe("the menu (R11.4)", () => {
  const handlers = () => ({ onGiveBack: jest.fn(), onContact: jest.fn(), onUnread: jest.fn(), onResolve: jest.fn(), onReopen: jest.fn(), onClear: jest.fn(), onDelete: jest.fn() });

  it("Contacto, no leída, Resolver, and last Vaciar and Eliminar — destructive", async () => {
    await render(<ConversationToolbar mine={false} agentName="Recepción" resolved={false} online {...handlers()} />);
    const items = screen.getAllByTestId("toolbar-menu-action");
    expect(items.map((n) => n.props.accessibilityLabel)).toEqual(["Datos del contacto", "Marcar como no leída", "Marcar como resuelta", "Vaciar chat", "Eliminar chat"]);
    expect(items.slice(-2).map((n) => n.props.accessibilityHint)).toEqual(["destructive", "destructive"]);
  });

  it("Android's sheet has the same list, and offline what writes is off", () => {
    const os = jest.replaceProperty(Platform, "OS", "android");
    const list = conversationMenu({ mine: true, agentName: "Recepción", resolved: true, online: false, ...handlers() }, t);
    expect(list.map((a) => [a.label, !!a.disabled, !!a.destructive])).toEqual([
      ["Devolver a Recepción", true, false],
      ["Datos del contacto", false, false],
      ["Marcar como no leída", true, false],
      ["Reabrir", true, false],
      ["Vaciar chat", true, true],
      ["Eliminar chat", true, true],
    ]);
    os.restore();
  });

  it("«Eliminar chat» asks first, archives, goes back and says so", async () => {
    const alert = jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
    mockApi.archive.mockResolvedValue(undefined);
    const { result } = await chat();
    await act(async () => result.current.confirmDelete());
    const [title, body, buttons] = alert.mock.calls[0] as [string, string, { text: string; style?: string; onPress?: () => void }[]];
    expect(title).toBe("¿Eliminar este chat?");
    expect(body).toBe(t("inbox.delete.body"));
    expect(mockApi.archive).not.toHaveBeenCalled();
    const del = buttons.find((b) => b.style === "destructive")!;
    expect(del.text).toBe("Eliminar chat");
    await act(async () => del.onPress?.());
    expect(mockApi.archive).toHaveBeenCalledWith("c1");
    expect(mockBack).toHaveBeenCalled();
    expect(mockShow.mock.calls.at(-1)![0]).toMatchObject({ text: "Chat eliminado" });
    alert.mockRestore();
  });

  it("«Vaciar chat» asks first and paints the conversation as the API answers it", async () => {
    const alert = jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
    mockApi.clear.mockResolvedValue({ id: "c1", control_version: 2 });
    const { result } = await chat();
    await act(async () => result.current.confirmClear());
    const buttons = alert.mock.calls[0]![2] as { style?: string; onPress?: () => void }[];
    expect(alert.mock.calls[0]![0]).toBe("¿Vaciar este chat?");
    await act(async () => buttons.find((b) => b.style === "destructive")!.onPress?.());
    expect(mockApi.clear).toHaveBeenCalledWith("c1");
    expect(qc.getQueryData(keys.conversation("c1"))).toEqual({ id: "c1", control_version: 2 });
    expect(mockShow.mock.calls.at(-1)![0]).toMatchObject({ text: "Chat vaciado" });
    expect(mockBack).not.toHaveBeenCalled();
    alert.mockRestore();
  });

  it("a refusal says so and stays", async () => {
    const alert = jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
    mockApi.archive.mockRejectedValue(new Error("no"));
    const { result } = await chat();
    await act(async () => result.current.remove());
    expect(mockBack).not.toHaveBeenCalled();
    expect(mockShow.mock.calls.at(-1)![0]).toMatchObject({ text: t("inbox.error.action"), tone: "warn" });
    alert.mockRestore();
  });

  it("«Marcar como no leída» goes back to the list with «Deshacer»", async () => {
    mockEndpoints.markRead.mockResolvedValue(undefined);
    const { result } = await chat();
    await act(async () => result.current.markUnread());
    expect(mockBack).toHaveBeenCalled();
    const toast = mockShow.mock.calls.at(-1)![0] as { text: string; action: { label: string; onPress: () => void } };
    expect(toast).toMatchObject({ text: "Marcada como no leída", action: { label: "Deshacer" } });
    await act(async () => toast.action.onPress());
    expect(mockEndpoints.markRead).toHaveBeenCalledWith("c1");
  });

  it("«Resolver» stays, with «Deshacer» that reopens", async () => {
    mockEndpoints.reopen.mockResolvedValue({ id: "c1", state: "agent" });
    const { result } = await chat();
    await act(async () => result.current.resolve());
    const toast = mockShow.mock.calls.at(-1)![0] as { text: string; action: { onPress: () => void } };
    expect(toast.text).toBe("Resuelta. Descansa en Resueltas.");
    expect(mockBack).not.toHaveBeenCalled();
    await act(async () => toast.action.onPress());
    expect(mockEndpoints.reopen).toHaveBeenCalledWith("c1");
  });
});

describe("the header (R11.1)", () => {
  it("who, the channel's mark on the avatar, and who answers with its dot", async () => {
    await render(
      <ConversationTitle name="Sofía Herrera" line="Respondes tú" mode="mine" initials="SH" channel="instagram" hint="Datos del contacto" onPress={noop} />,
    );
    expect(screen.getByRole("button", { name: "Sofía Herrera. Instagram. Respondes tú" })).toBeTruthy();
    expect(screen.getByTestId("avatar-channel-instagram", { includeHiddenElements: true })).toBeTruthy();
    expect(screen.getByTestId("mode-dot")).toBeTruthy();
  });

  it("resolved: no dot, the words say it", async () => {
    await render(<ConversationTitle name="Pedro" line="Resuelta" mode="resolved" initials="P" hint="Datos del contacto" onPress={noop} />);
    expect(screen.queryByTestId("mode-dot")).toBeNull();
  });
});

describe("the thread (R11.6, R21.3, micro 7)", () => {
  it("a comment shows the post it was left on, and its link opens it", async () => {
    mockApi.post.mockResolvedValue({ text: "Nuevo horario de verano", permalink: "https://instagram.com/p/abc", image_url: null });
    const open = jest.spyOn(Linking, "openURL").mockResolvedValue(undefined);
    await render(<CommentPost conversationId="c1" messageId="m1" t={t} />, { wrapper });
    await waitFor(() => expect(screen.getByText("Comentó en esta publicación")).toBeTruthy());
    expect(mockApi.post).toHaveBeenCalledWith("c1", "m1");
    expect(screen.getByText("Nuevo horario de verano")).toBeTruthy();
    await fireEvent.press(screen.getByRole("link", { name: "Ver la publicación" }));
    expect(open).toHaveBeenCalledWith("https://instagram.com/p/abc");
    open.mockRestore();
  });

  it("without the post from Meta, the comment reads on its own", async () => {
    mockApi.post.mockResolvedValue(null);
    await render(<CommentPost conversationId="c1" messageId="m2" t={t} />, { wrapper });
    await waitFor(() => expect(mockApi.post).toHaveBeenCalled());
    expect(screen.queryByText("Comentó en esta publicación")).toBeNull();
  });

  it("the agent's answer under its name from the data, and «Leído» only when the API says so", async () => {
    const item = {
      type: "message",
      id: "m3",
      at: "2026-11-20T10:00:00Z",
      direction: "outbound",
      author: { kind: "agent", name: "Recepción", is_me: false },
      text: "Te esperamos",
      media: null,
      delivery: null,
      failure_reason: null,
      comment: false,
      unsent: false,
      opted_out: false,
    } as ThreadItem;
    await render(<MessageBubble item={item} t={t} locale="es" onOpen={noop} onCorrect={noop} />);
    expect(screen.getByText("Recepción")).toBeTruthy();
    expect(screen.queryByText(/Leído/)).toBeNull();
    expect(screen.getByRole("button", { name: "Corregir esta respuesta" })).toBeTruthy();
  });

  it("the send button only comes out with text", async () => {
    await render(<Composer mode={{ kind: "mine", blocked: null }} online focusSignal={0} replies={null} t={t} onSend={noop} onAttach={noop} onReplies={noop} />);
    expect(screen.queryByRole("button", { name: "Enviar" })).toBeNull();
    await fireEvent.changeText(screen.getByLabelText("Escribir un mensaje"), "Hola");
    expect(screen.getByRole("button", { name: "Enviar" })).toBeTruthy();
  });
});
