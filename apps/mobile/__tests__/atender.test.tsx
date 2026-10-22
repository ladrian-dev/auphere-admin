import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, renderHook, screen } from "@testing-library/react-native";
import * as Haptics from "expo-haptics";
import type { ReactNode } from "react";

import { ApiError } from "@/api/errors";
import { keys } from "@/api/query";
import { checkAttachment, composerMode } from "@/features/inbox/model";
import { Composer } from "@/features/inbox/thread/composer";
import { ControlCard } from "@/features/inbox/thread/control";
import { useConversationActions } from "@/features/inbox/thread/use-conversation";
import { t as translate, type MessageKey } from "@/i18n/t";

/**
 * Spec 031 (T075, R6.1–R6.7, R14.9): taking control and answering.
 */
const t = (k: MessageKey, v?: Record<string, string | number>) => translate("es", k, v);
const mockSend = jest.fn();
const mockTakeOver = jest.fn();
jest.mock("@/api/endpoints", () => ({
  endpoints: {
    send: (...a: unknown[]) => mockSend(...a),
    takeOver: (...a: unknown[]) => mockTakeOver(...a),
  },
}));

describe("the control card (R6.1)", () => {
  it("says why it waits before «Tomar el control», which is at the bottom", async () => {
    const onTakeOver = jest.fn();
    await render(
      <ControlCard mode={{ kind: "waiting", reason: "Pide hablar con alguien" }} busy={false} online t={t} onTakeOver={onTakeOver} onGiveBack={jest.fn()} onReopen={jest.fn()} />,
    );
    const tree = JSON.stringify(screen.toJSON());
    expect(tree.indexOf("Pide hablar con alguien")).toBeGreaterThan(-1);
    expect(tree.indexOf("Pide hablar con alguien")).toBeLessThan(tree.indexOf("Tomar el control"));
    await fireEvent.press(screen.getByRole("button", { name: "Tomar el control" }));
    expect(onTakeOver).toHaveBeenCalled();
  });

  it("offline, nothing that writes is offered", async () => {
    await render(<ControlCard mode={{ kind: "agent" }} busy={false} online={false} t={t} onTakeOver={jest.fn()} onGiveBack={jest.fn()} onReopen={jest.fn()} />);
    expect(screen.getByRole("button", { name: "Tomar el control" }).props.accessibilityState).toMatchObject({ disabled: true });
  });
});

describe("the box (R6.3, R6.5)", () => {
  it("with the 24 h window closed it says so before anyone types, and there is no box", async () => {
    await render(<Composer mode={{ kind: "mine", blocked: "window_closed" }} online focusSignal={0} replies={null} t={t} onSend={jest.fn()} onAttach={jest.fn()} onReplies={jest.fn()} />);
    expect(screen.getByText(/WhatsApp no deja escribirle hasta que vuelva a escribir/)).toBeTruthy();
    expect(screen.queryByLabelText("Escribir un mensaje")).toBeNull();
  });

  it("a saved reply lands in the box, not sent", async () => {
    const onSend = jest.fn();
    await render(
      <Composer
        mode={{ kind: "mine", blocked: null }}
        online
        focusSignal={0}
        replies={[{ id: "r1", title: "Horario", body: "Abrimos de 9 a 18." }]}
        t={t}
        onSend={onSend}
        onAttach={jest.fn()}
        onReplies={(insert) => insert("Abrimos de 9 a 18.")}
      />,
    );
    await fireEvent.press(screen.getByRole("button", { name: "Insertar respuesta guardada" }));
    expect(screen.getByLabelText("Escribir un mensaje").props.value).toBe("Abrimos de 9 a 18.");
    expect(onSend).not.toHaveBeenCalled();
  });

  it("modes follow who answers", () => {
    const base = { waiting_reason: null, window: { open: true, closes_at: null }, channel: { kind: "whatsapp", connected: true } };
    // Spec 044 (R11) adds since when and the agent's name; the kind and reason are the 031's.
    expect(composerMode({ ...base, state: "waiting", assignee: null })).toEqual({ kind: "waiting", reason: null, since: null, agent: null });
    expect(composerMode({ ...base, state: "person", assignee: { kind: "member", name: "Luis", is_me: false } })).toEqual({ kind: "other", name: "Luis" });
    expect(composerMode({ ...base, state: "person", assignee: { kind: "member", name: null, is_me: true }, channel: { kind: "whatsapp", connected: false } })).toEqual({
      kind: "mine",
      blocked: "channel_disconnected",
      agent: null,
    });
  });

  it("attachments are checked by type and size before uploading, saying the limit", () => {
    expect(checkAttachment({ type: "image/heic", size: 10 })).toEqual({ ok: false, reason: "type" });
    expect(checkAttachment({ type: "image/jpeg", size: 6 * 1024 * 1024 })).toEqual({ ok: false, reason: "size", maxMb: 5 });
    expect(checkAttachment({ type: "application/pdf", size: 10 * 1024 * 1024 })).toEqual({ ok: true });
    expect(t("inbox.composer.attach.size", { mb: 5 })).toBe("Ese archivo pasa de 5 MB.");
  });
});

describe("the foot of the thread is one surface (spec 042, T049–T051, R2.1, R2.3, R2.4, R2.5, R2.8, R2.9)", () => {
  const { ThreadFoot } = require("@/features/inbox/thread/foot") as typeof import("@/features/inbox/thread/foot");
  const noop = jest.fn();
  const foot = (mode: Parameters<typeof ThreadFoot>[0]["mode"], extra: Partial<Parameters<typeof ThreadFoot>[0]> = {}) => (
    <ThreadFoot
      mode={mode}
      busy={false}
      online
      t={t}
      replies={null}
      focusSignal={0}
      onTakeOver={noop}
      onGiveBack={noop}
      onReopen={noop}
      onSend={noop}
      onAttach={noop}
      onReplies={noop}
      onReadMore={noop}
      {...extra}
    />
  );

  it.each([
    [{ kind: "waiting", reason: "Pide hablar con alguien" }, "take-over"],
    [{ kind: "agent" }, "take-over"],
    [{ kind: "other", name: "Luis" }, "take-over"],
    [{ kind: "resolved" }, "reopen"],
    [{ kind: "mine", blocked: null }, "send"],
    [{ kind: "mine", blocked: "window_closed" }, "blocked"],
  ] as const)("renders one surface for %j, with its own control", async (mode, control) => {
    await render(foot(mode as Parameters<typeof ThreadFoot>[0]["mode"]));
    expect(screen.getAllByTestId("thread-surface")).toHaveLength(1);
    expect(screen.getByTestId(control)).toBeTruthy();
    if (mode.kind === "waiting") expect(screen.getByTestId("waiting-card")).toBeTruthy();
  });

  it("waiting: the reason comes before the action, in two lines, and «Leer más» opens it whole when it does not fit", async () => {
    const onReadMore = jest.fn();
    await render(foot({ kind: "waiting", reason: "Quiere cambiar su cita del jueves y el agente no puede mover reservas. Además pregunta por el tinte." }, { onReadMore }));
    const reason = screen.getByTestId("waiting-reason");
    expect(reason.props.numberOfLines).toBe(2);
    expect(screen.queryByRole("button", { name: "Leer más" })).toBeNull();
    // The hidden copy, laid out without a limit, is what says whether the words fit.
    await fireEvent(screen.getByTestId("waiting-reason-measure", { includeHiddenElements: true }), "textLayout", { nativeEvent: { lines: [{}, {}, {}] } });
    await fireEvent.press(screen.getByRole("button", { name: "Leer más" }));
    expect(onReadMore).toHaveBeenCalled();
    const tree = JSON.stringify(screen.toJSON());
    expect(tree.indexOf("Quiere cambiar")).toBeLessThan(tree.indexOf("Tomar el control"));
    expect(screen.getByRole("button", { name: "Devolver al agente" })).toBeTruthy();
  });

  it("with no reason, the panel says the agent gave none", async () => {
    await render(foot({ kind: "waiting", reason: null }));
    expect(screen.getByText(t("inbox.composer.waiting.noReason"))).toBeTruthy();
  });

  it("taking control changes the children of the same surface: the node stays, the box arrives with its testIDs", async () => {
    const { rerender } = await render(foot({ kind: "waiting", reason: "x" }));
    const before = screen.getByTestId("thread-surface");
    await rerender(foot({ kind: "mine", blocked: null }, { focusSignal: 1 }));
    expect(screen.getByTestId("thread-surface")).toBe(before);
    expect(screen.getByTestId("composer-input")).toBeTruthy();
    expect(screen.getByTestId("send")).toBeTruthy();
    expect(screen.queryByTestId("take-over")).toBeNull();
  });

  it("another person took it meanwhile: the panel shows the real state and offers nothing it cannot do", async () => {
    const { rerender } = await render(foot({ kind: "waiting", reason: "x" }));
    await rerender(foot({ kind: "other", name: "Luis" }));
    expect(screen.getByText(t("inbox.composer.other", { name: "Luis" }))).toBeTruthy();
    expect(screen.queryByTestId("waiting-card")).toBeNull();
  });
});

const testClient = () => new QueryClient({ defaultOptions: { queries: { gcTime: Infinity, retry: false } } });

describe("sending and control (R6.2, R6.4, R6.6)", () => {
  function wrapper(qc: QueryClient) {
    return function Wrapper({ children }: { children: ReactNode }) {
      return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
    };
  }

  beforeEach(() => {
    mockSend.mockReset();
    mockTakeOver.mockReset();
  });

  it("is optimistic, and a retry after a failure reuses the same Idempotency-Key with the text kept", async () => {
    const qc = testClient();
    mockSend.mockRejectedValueOnce(new ApiError(0, "offline")).mockResolvedValueOnce({ id: "m9", at: "", delivery: "pending" });
    const { result } = await renderHook(() => useConversationActions("c1", t), { wrapper: wrapper(qc) });
    await act(async () => void result.current.send("¿Te va bien a las 5?"));
    expect(result.current.pending).toHaveLength(1);
    expect(result.current.pending[0]).toMatchObject({ status: "failed", text: "¿Te va bien a las 5?" });
    const key = mockSend.mock.calls[0]![2];
    await act(async () => result.current.retry(result.current.pending[0]!.key));
    await act(async () => undefined);
    expect(mockSend.mock.calls[1]![2]).toBe(key);
    expect(mockSend.mock.calls[1]![1]).toBe("¿Te va bien a las 5?");
    expect(result.current.pending).toHaveLength(0);
  });

  it("a 412 paints who answers now, says so, and warns with a vibration", async () => {
    const qc = testClient();
    const now = { id: "c1", state: "person", assignee: { kind: "member", name: "Luis", is_me: false } };
    mockTakeOver.mockRejectedValue(new ApiError(412, null, { conversation: now }));
    const { result } = await renderHook(() => useConversationActions("c1", t), { wrapper: wrapper(qc) });
    await act(async () => result.current.takeOver(3));
    expect(qc.getQueryData(keys.conversation("c1"))).toEqual(now);
    expect(result.current.notice?.text).toBe("Alguien cambió esta conversación mientras la mirabas. Ya ves cómo está ahora.");
    expect(Haptics.notificationAsync).toHaveBeenCalledWith("warning");
  });

  it("taking control confirms with success and asks the box for focus", async () => {
    const qc = testClient();
    const spy = jest.spyOn(qc, "invalidateQueries");
    mockTakeOver.mockResolvedValue({ id: "c1", state: "person" });
    const { result } = await renderHook(() => useConversationActions("c1", t), { wrapper: wrapper(qc) });
    await act(async () => result.current.takeOver(3));
    expect(Haptics.notificationAsync).toHaveBeenCalledWith("success");
    expect(result.current.tookOver).toBe(1);
    // Back on Inicio, it no longer says the conversation waits.
    expect(spy.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey))).toContain(JSON.stringify(["home"]));
  });
});

/**
 * Spec 044, Historia 6, Requisito 11: whoever opens a waiting conversation
 * sees since when and who asked; with control, «Devolver» is one tap and the
 * saved replies are in view.
 */
describe("attending (spec 044, R11)", () => {
  const since = new Date(Date.now() - 12 * 60_000).toISOString();

  it("the waiting card says since when and who asked, before «Tomar el control»", async () => {
    await render(
      <ControlCard mode={{ kind: "waiting", reason: "Pide la seña", since, agent: "Soporte" }} busy={false} online t={t} onTakeOver={jest.fn()} onGiveBack={jest.fn()} onReopen={jest.fn()} />,
    );
    expect(screen.getByText("Espera hace 12 min · lo pidió Soporte")).toBeTruthy();
  });

  it("while the agent answers, it says what stepping in does", async () => {
    await render(<ControlCard mode={{ kind: "agent", agent: "Ventas" }} busy={false} online t={t} onTakeOver={jest.fn()} onGiveBack={jest.fn()} onReopen={jest.fn()} />);
    expect(screen.getByText("Responde Ventas. Si entras, deja de responder.")).toBeTruthy();
  });

  it("with control, «Devolver» is one tap away, not only in the menu", async () => {
    const onGiveBack = jest.fn();
    await render(
      <Composer mode={{ kind: "mine", blocked: null, agent: "Ventas" }} online focusSignal={0} replies={null} t={t} onSend={jest.fn()} onAttach={jest.fn()} onReplies={jest.fn()} onGiveBack={onGiveBack} />,
    );
    expect(screen.getByText("Atiendes tú · Ventas está en pausa")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Devolver" }));
    expect(onGiveBack).toHaveBeenCalled();
  });

  it("with the draft empty, the saved replies are chips that fill it", async () => {
    await render(
      <Composer
        mode={{ kind: "mine", blocked: null, agent: "Ventas" }}
        online
        focusSignal={0}
        replies={[{ id: "r1", title: "Horario de la semana y del sábado", body: "Abrimos de 9 a 19." }]}
        t={t}
        onSend={jest.fn()}
        onAttach={jest.fn()}
        onReplies={jest.fn()}
        onGiveBack={jest.fn()}
      />,
    );
    await fireEvent.press(screen.getByRole("button", { name: "Horario de la semana y del sábado" }));
    expect(screen.getByLabelText("Escribir un mensaje").props.value).toBe("Abrimos de 9 a 19.");
    expect(screen.queryByRole("button", { name: "Horario de la semana y del sábado" })).toBeNull();
  });

  it("the bar says the state in words (R11.2)", () => {
    const { attendsLine } = require("@/features/inbox/model") as typeof import("@/features/inbox/model");
    expect(attendsLine({ state: "waiting", assignee: null, agent: { id: "a", name: "Soporte" } }, t)).toBe("Espera a una persona");
    expect(attendsLine({ state: "resolved", assignee: null, agent: null }, t)).toBe("Resuelta");
    expect(attendsLine({ state: "agent", assignee: null, agent: { id: "a", name: "Soporte" } }, t)).toBe("Atiende Soporte");
    expect(attendsLine({ state: "person", assignee: { is_me: true, kind: "member", name: "Valeria" }, agent: null }, t)).toBe("Atiendes tú");
  });
});
