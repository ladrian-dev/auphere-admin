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
    expect(composerMode({ ...base, state: "waiting", assignee: null })).toEqual({ kind: "waiting", reason: null });
    expect(composerMode({ ...base, state: "person", assignee: { kind: "member", name: "Luis", is_me: false } })).toEqual({ kind: "other", name: "Luis" });
    expect(composerMode({ ...base, state: "person", assignee: { kind: "member", name: null, is_me: true }, channel: { kind: "whatsapp", connected: false } })).toEqual({
      kind: "mine",
      blocked: "channel_disconnected",
    });
  });

  it("attachments are checked by type and size before uploading, saying the limit", () => {
    expect(checkAttachment({ type: "image/heic", size: 10 })).toEqual({ ok: false, reason: "type" });
    expect(checkAttachment({ type: "image/jpeg", size: 6 * 1024 * 1024 })).toEqual({ ok: false, reason: "size", maxMb: 5 });
    expect(checkAttachment({ type: "application/pdf", size: 10 * 1024 * 1024 })).toEqual({ ok: true });
    expect(t("inbox.composer.attach.size", { mb: 5 })).toBe("Ese archivo pasa de 5 MB.");
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
