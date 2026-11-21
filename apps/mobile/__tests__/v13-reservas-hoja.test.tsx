import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { act, fireEvent, render, renderHook, screen } from "@testing-library/react-native";
import type { ReactNode } from "react";
import { StyleSheet } from "react-native";

import { t as translate, type T } from "@/i18n/t";

import { marcos, peinado, res, servicesConfig, TODAY } from "../test/reservas-fixtures";

const mockCancel = jest.fn(async () => ({}));
jest.mock("@/api/reservas", () => {
  const actual = jest.requireActual("@/api/reservas");
  return { ...actual, reservasSource: () => ({ cancel: mockCancel, removeWait: mockCancel }) };
});

const { ReservaSheet } = require("@/features/reservas/sheet") as typeof import("@/features/reservas/sheet");
const { CancelPanel } = require("@/features/reservas/cancel-panel") as typeof import("@/features/reservas/cancel-panel");
const hooks = require("@/api/reservas-hooks") as typeof import("@/api/reservas-hooks");

/**
 * Spec 069, Requisito 14 (enmienda a la 044: mover y pedir confirmación se
 * ofrecen en el teléfono, como en la web) y micro 6: one reservation, the
 * actions the API allows, and a cancellation that asks what to do and keeps
 * «Deshacer» honest.
 */
const t: T = (k, v) => translate("es", k, v);
const noop = () => undefined;

const pending = res({
  id: "p",
  start: 17 * 60,
  end: 17 * 60 + 45,
  date: "2026-10-23",
  state: "pending",
  service: peinado,
  pro: marcos,
  customer: { name: "Lucía Fernández", phone: "+56 9 6123 4567", conversationId: "c-lucia" },
  actions: ["confirm", "cancel"],
  moreActions: ["move", "request_confirmation"],
});

describe("the sheet's actions (R14.1)", () => {
  it("offers «Pedir confirmación» and «Mover» when the API allows them", async () => {
    const onMore = jest.fn();
    await render(<ReservaSheet r={pending} config={servicesConfig} today={TODAY} online onAct={noop} onMore={onMore} onCancel={noop} t={t} locale="es" />);
    await fireEvent.press(screen.getByRole("button", { name: "Pedir confirmación" }));
    expect(onMore).toHaveBeenCalledWith("request_confirmation");
    await fireEvent.press(screen.getByRole("button", { name: "Mover" }));
    expect(onMore).toHaveBeenCalledWith("move");
  });

  it("side by side only when their words fit on one line: each takes its words' width and drops to its own line when they don't (iOS simulator, T052)", async () => {
    // With two equal halves, «Pedir confirmación» broke inside the word beside its bell («confirmació / n»).
    await render(<ReservaSheet r={pending} config={servicesConfig} today={TODAY} online onAct={noop} onMore={noop} onCancel={noop} t={t} locale="es" />);
    type Node = { props: { style?: unknown }; parent: Node | null };
    const flat = (n: Node | null) => (n ? ((StyleSheet.flatten(n.props.style as never) ?? {}) as Record<string, unknown>) : {});
    for (const name of ["Marcar confirmada", "Pedir confirmación", "Mover"]) {
      let n = screen.getByRole("button", { name }) as unknown as Node | null;
      // The slot is the child of the wrapping row of actions.
      while (n && flat(n.parent).flexWrap !== "wrap") n = n.parent;
      expect(flat(n)).toMatchObject({ flexBasis: "auto", flexGrow: 1, flexShrink: 1 });
    }
  });

  it("and not when it does not", async () => {
    const done = { ...pending, state: "confirmed" as const, actions: [], moreActions: [] };
    await render(<ReservaSheet r={done} config={servicesConfig} today={TODAY} online onAct={noop} onMore={noop} onCancel={noop} t={t} locale="es" />);
    expect(screen.queryByText("Pedir confirmación")).toBeNull();
    expect(screen.queryByText("Mover")).toBeNull();
  });

  it("«Abrir el chat» only with its conversation and the Bandeja", async () => {
    const onChat = jest.fn();
    await render(<ReservaSheet r={pending} config={servicesConfig} today={TODAY} online onAct={noop} onCancel={noop} onChat={onChat} t={t} locale="es" />);
    await fireEvent.press(screen.getByRole("button", { name: "Abrir el chat" }));
    expect(onChat).toHaveBeenCalledWith("c-lucia");
  });

  it("says the state and the origin in pills, once each, with the price in the business's currency", async () => {
    await render(<ReservaSheet r={pending} config={{ ...servicesConfig, currency: "EUR" }} today={TODAY} online onAct={noop} onCancel={noop} t={t} locale="es" />);
    expect(screen.getAllByText("Sin confirmar", { includeHiddenElements: true })).toHaveLength(1);
    expect(screen.getAllByText("La reservó el agente por WhatsApp")).toHaveLength(1);
    expect(screen.getByText(/Corte y peinado · 45 min · 180,00\s€/)).toBeTruthy();
  });

  it("an attended booking of the last days can still be marked «No vino», as the API allows (064 R2, Requisito 20)", async () => {
    const onAct = jest.fn();
    const attended = { ...pending, date: "2026-10-20", state: "done" as const, actions: ["noshow" as const], moreActions: [] };
    await render(<ReservaSheet r={attended} config={servicesConfig} today={TODAY} online onAct={onAct} onCancel={noop} t={t} locale="es" />);
    expect(screen.getByText("Atendida")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "No vino" }));
    expect(onAct).toHaveBeenCalledWith("noshow");
  });

  it("offline, none of the new actions either", async () => {
    await render(<ReservaSheet r={pending} config={servicesConfig} today={TODAY} online={false} onAct={noop} onMore={noop} onCancel={noop} onChat={noop} t={t} locale="es" />);
    expect(screen.queryByText("Mover")).toBeNull();
    expect(screen.queryByText("Pedir confirmación")).toBeNull();
  });
});

describe("cancelling asks what to do (R14.2)", () => {
  it("tells the customer by default, and the person can say no", async () => {
    const onConfirm = jest.fn();
    await render(<CancelPanel r={pending} mode="services" preview={{ canOffer: false, candidates: 0, whyNot: "nobody_fits" }} previewLoading={false} leadHours={2} today={TODAY} onConfirm={onConfirm} onBack={noop} t={t} locale="es" />);
    expect(screen.getByText("¿Cancelar esta reserva?")).toBeTruthy();
    expect(screen.getByText("Nadie de la lista de espera encaja en este hueco.")).toBeTruthy();
    const notify = screen.getByRole("switch", { name: "Avisar a Lucía por WhatsApp" });
    expect(notify.props.accessibilityState).toMatchObject({ checked: true });
    await fireEvent(notify, "valueChange", false);
    await fireEvent.press(screen.getByRole("button", { name: "Cancelar reserva" }));
    expect(onConfirm).toHaveBeenCalledWith({ notify: false, offerSlot: false });
  });

  it("offers the slot to the waitlist when someone fits, yes by default", async () => {
    const onConfirm = jest.fn();
    await render(<CancelPanel r={pending} mode="services" preview={{ canOffer: true, candidates: 3, whyNot: null }} previewLoading={false} leadHours={2} today={TODAY} onConfirm={onConfirm} onBack={noop} t={t} locale="es" />);
    expect(screen.getByText("¿Quieres que el agente intente llenar el hueco?")).toBeTruthy();
    expect(screen.getByText("3 personas encajan. Les escribe de una en una, hasta 5.")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Cancelar reserva" }));
    expect(onConfirm).toHaveBeenLastCalledWith({ notify: true, offerSlot: true });
    await fireEvent.press(screen.getByRole("radio", { name: "No, dejar el hueco libre" }));
    await fireEvent.press(screen.getByRole("button", { name: "Cancelar reserva" }));
    expect(onConfirm).toHaveBeenLastCalledWith({ notify: true, offerSlot: false });
  });

  it("without a phone it says they cannot be told, and asks nothing about it", async () => {
    const onConfirm = jest.fn();
    const noPhone = { ...pending, customer: { name: "Ana", phone: null } };
    await render(<CancelPanel r={noPhone} mode="services" preview={null} previewLoading={false} leadHours={2} today={TODAY} onConfirm={onConfirm} onBack={noop} t={t} locale="es" />);
    expect(screen.queryByRole("switch")).toBeNull();
    expect(screen.getByText("No dejó teléfono: no se le puede avisar. El hueco queda libre.")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Cancelar reserva" }));
    expect(onConfirm).toHaveBeenCalledWith({ notify: false, offerSlot: false });
  });

  it("too soon for the list says why, with the lead in hours", async () => {
    await render(<CancelPanel r={pending} mode="services" preview={{ canOffer: false, candidates: 0, whyNot: "too_soon" }} previewLoading={false} leadHours={2} today={TODAY} onConfirm={noop} onBack={noop} t={t} locale="es" />);
    expect(screen.getByText("Empieza en menos de 2 h: no da tiempo a ofrecerlo a la lista.")).toBeTruthy();
  });

  it("«Mantenerla» goes back without cancelling", async () => {
    const onBack = jest.fn();
    const onConfirm = jest.fn();
    await render(<CancelPanel r={pending} mode="services" preview={null} previewLoading={false} leadHours={2} today={TODAY} onConfirm={onConfirm} onBack={onBack} t={t} locale="es" />);
    await fireEvent.press(screen.getByRole("button", { name: "Mantenerla" }));
    expect(onBack).toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });
});

describe("«Deshacer» is honest: nothing goes out while it is offered (micro 6)", () => {
  jest.useFakeTimers({ doNotFake: ["Date"] });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>;

  beforeEach(() => {
    mockCancel.mockClear();
    hooks.resetPendingWrites();
  });

  it("the cancellation reaches the API only once the notice has gone", async () => {
    const { result } = await renderHook(() => ({ cancel: hooks.useDeferredCancel(), items: hooks.useWithPendingCancels([pending]) }), { wrapper });
    await act(async () => {
      result.current.cancel(pending, { notify: true, offerSlot: false }, noop);
    });
    expect(result.current.items?.[0]?.state).toBe("cancelled");
    expect(mockCancel).not.toHaveBeenCalled();
    await act(async () => {
      await jest.advanceTimersByTimeAsync(hooks.UNDO_MS + 10);
    });
    expect(mockCancel).toHaveBeenCalledWith(pending, { notify: true, offerSlot: false });
  });

  it("with a screen reader on, it waits as long as the notice does: 20 s (review H10)", async () => {
    const { AccessibilityInfo } = require("react-native") as typeof import("react-native");
    const { SafeAreaProvider } = require("react-native-safe-area-context") as typeof import("react-native-safe-area-context");
    const { ToastProvider, TOAST_UNDO_READER_MS } = require("@/ui/toast") as typeof import("@/ui/toast");
    const reader = jest.spyOn(AccessibilityInfo, "isScreenReaderEnabled").mockResolvedValue(true);
    const metrics = { frame: { x: 0, y: 0, width: 390, height: 844 }, insets: { top: 47, left: 0, right: 0, bottom: 34 } };
    const withToast = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={new QueryClient()}>
        <SafeAreaProvider initialMetrics={metrics}>
          <ToastProvider>{children}</ToastProvider>
        </SafeAreaProvider>
      </QueryClientProvider>
    );
    try {
      const { result } = await renderHook(() => hooks.useDeferredCancel(), { wrapper: withToast });
      await act(async () => undefined);
      await act(async () => {
        result.current(pending, { notify: true, offerSlot: false }, noop);
      });
      await act(async () => {
        await jest.advanceTimersByTimeAsync(hooks.UNDO_MS + 10);
      });
      expect(mockCancel).not.toHaveBeenCalled();
      await act(async () => {
        await jest.advanceTimersByTimeAsync(TOAST_UNDO_READER_MS - hooks.UNDO_MS);
      });
      expect(mockCancel).toHaveBeenCalled();
    } finally {
      reader.mockResolvedValue(false);
      // The provider is gone; its last reading stays: read «off» again with a fresh provider.
      await render(
        <SafeAreaProvider initialMetrics={metrics}>
          <ToastProvider>{null}</ToastProvider>
        </SafeAreaProvider>,
      );
      await act(async () => undefined);
    }
  });

  it("«Deshacer» drops it: the customer is never told", async () => {
    const { result } = await renderHook(() => ({ cancel: hooks.useDeferredCancel(), items: hooks.useWithPendingCancels([pending]) }), { wrapper });
    let undo: () => boolean = () => false;
    await act(async () => {
      undo = result.current.cancel(pending, { notify: true, offerSlot: false }, noop);
    });
    await act(async () => {
      expect(undo()).toBe(true);
      await jest.advanceTimersByTimeAsync(hooks.UNDO_MS + 10);
    });
    expect(mockCancel).not.toHaveBeenCalled();
    expect(result.current.items?.[0]?.state).toBe("pending");
  });

  it("a screen that keeps the same list still sees the change (React Compiler memoises on what it reads)", async () => {
    const items = [pending];
    const { result } = await renderHook(() => ({ cancel: hooks.useDeferredCancel(), items: hooks.useWithPendingCancels(items) }), { wrapper });
    expect(result.current.items?.[0]?.state).toBe("pending");
    let undo: () => boolean = () => false;
    await act(async () => {
      undo = result.current.cancel(pending, { notify: false, offerSlot: false }, noop);
    });
    expect(result.current.items?.[0]?.state).toBe("cancelled");
    await act(async () => {
      expect(undo()).toBe(true);
    });
    expect(result.current.items?.[0]?.state).toBe("pending");
  });

  it("leaving the app sends what waited, and «Deshacer» then says it is too late", async () => {
    const { result } = await renderHook(() => hooks.useDeferredCancel(), { wrapper });
    let undo: () => boolean = () => true;
    await act(async () => {
      undo = result.current(pending, { notify: true, offerSlot: true }, noop);
    });
    await act(async () => {
      hooks.flushPendingWrites();
    });
    expect(mockCancel).toHaveBeenCalledWith(pending, { notify: true, offerSlot: true });
    expect(undo()).toBe(false);
    // And nothing goes twice when the timer would have fired.
    await act(async () => {
      await jest.advanceTimersByTimeAsync(hooks.UNDO_MS + 10);
    });
    expect(mockCancel).toHaveBeenCalledTimes(1);
  });

  it("«Deshacer» of a booking just saved works after its form is gone, and tells the customer if they were told", async () => {
    const { result, unmount } = await renderHook(() => hooks.useUndoCreate(), { wrapper });
    const undo = result.current;
    await unmount();
    await act(async () => {
      await undo(pending);
    });
    expect(mockCancel).toHaveBeenCalledWith(pending, { notify: true, offerSlot: false });
  });

  it("once sent, it stays cancelled until the re-read brings the truth: it never flickers back", async () => {
    const client = new QueryClient();
    let server: (typeof pending)[] = [pending];
    const wrap = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    const { result } = await renderHook(
      () => {
        const q = useQuery({ queryKey: ["reservas", "range", "a", "b"], queryFn: () => new Promise<(typeof pending)[]>((resolve) => setTimeout(() => resolve(server), 300)) });
        return { cancel: hooks.useDeferredCancel(), items: hooks.useWithPendingCancels(q.data) };
      },
      { wrapper: wrap },
    );
    await act(async () => {
      await jest.advanceTimersByTimeAsync(400);
    });
    expect(result.current.items?.[0]?.state).toBe("pending");
    await act(async () => {
      result.current.cancel(pending, { notify: true, offerSlot: false }, noop);
    });
    server = [{ ...pending, state: "cancelled" }];
    // Sent; the re-read is on its way (300 ms): still cancelled, not «pending» for a moment.
    await act(async () => {
      await jest.advanceTimersByTimeAsync(hooks.UNDO_MS + 50);
    });
    expect(mockCancel).toHaveBeenCalled();
    expect(result.current.items?.[0]?.state).toBe("cancelled");
    await act(async () => {
      await jest.advanceTimersByTimeAsync(400);
    });
    expect(result.current.items?.[0]?.state).toBe("cancelled");
    client.clear();
  });

  it("taking someone off the waitlist waits the same way", async () => {
    const entry = { id: "w1" } as import("@/api/reservas").WaitEntry;
    const { result } = await renderHook(() => ({ remove: hooks.useDeferredRemoveWait(), list: hooks.useWithPendingRemovals([entry]) }), { wrapper });
    await act(async () => {
      result.current.remove("w1", noop);
    });
    expect(result.current.list).toEqual([]);
    expect(mockCancel).not.toHaveBeenCalled();
    await act(async () => {
      await jest.advanceTimersByTimeAsync(hooks.UNDO_MS + 10);
    });
    expect(mockCancel).toHaveBeenCalledWith("w1");
  });
});

describe("a booking just saved enters its day once (micro 3)", () => {
  const arrival = require("@/features/reservas/arrival") as typeof import("@/features/reservas/arrival");

  it("is announced, and expires on its own so a later visit does not animate it again", async () => {
    const { result } = await renderHook(() => arrival.useArrivalSignal());
    await act(async () => {
      arrival.announceArrival("r-new", "2026-10-23");
    });
    expect(result.current).toMatchObject({ id: "r-new", date: "2026-10-23" });
    expect(arrival.arrives(result.current, "r-new")).toBe(true);
    expect(arrival.arrives(result.current, "r-other")).toBe(false);
    await act(async () => {
      await jest.advanceTimersByTimeAsync(4100);
    });
    expect(result.current).toBeNull();
  });
});
