import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render } from "@testing-library/react-native";
import { createParser } from "eventsource-parser";
import { AppState, Text } from "react-native";

import { backoff, parseFrame, RECONNECTING_AFTER_MS, useInboxStream, useLiveStatus } from "@/api/sse";

/**
 * Spec 031 (T068, D17, R5.4, R5.5): the live Bandeja on the phone.
 */
const mockSettle = jest.fn(async (_res: unknown) => undefined);
jest.mock("@/api/client", () => ({
  APP_HEADERS: { "X-App-Platform": "ios", "X-App-Version": "1.0.0" },
  accessToken: async () => "tok",
  refresh: async () => null,
  settleRefusal: (res: unknown) => mockSettle(res),
}));

const mockFetch = jest.fn();
jest.mock("expo/fetch", () => ({ fetch: (...a: unknown[]) => mockFetch(...a) }));

/** A response whose body yields `chunks`, then ends (the line drops). */
function stream(chunks: string[]) {
  const enc = new TextEncoder();
  let i = 0;
  return {
    ok: true,
    status: 200,
    body: { getReader: () => ({ read: async () => (i < chunks.length ? { done: false, value: enc.encode(chunks[i++]) } : { done: true }) }) },
  };
}

describe("frames", () => {
  it("reads the three event kinds through eventsource-parser, and ignores the rest", () => {
    const seen: unknown[] = [];
    const parser = createParser({ onEvent: (m) => seen.push(parseFrame(m.event, m.data)) });
    parser.feed('event: ready\ndata: {}\n\nevent: message.new\ndata: {"conversation_id":"c1","message_id":"m"}\n\n');
    parser.feed('event: ping\ndata: {}\n\nevent: conversation.updated\ndata: {"conversation_id":"c2"}\n\nevent: message.status\ndata: oops\n\n');
    expect(seen).toEqual([null, { event: "message.new", conversation_id: "c1" }, null, { event: "conversation.updated", conversation_id: "c2" }, null]);
  });

  it("waits longer after each drop, up to 10 s", () => {
    expect([1, 2, 3, 4, 5, 9].map(backoff)).toEqual([1000, 2000, 4000, 8000, 10000, 10000]);
  });
});

describe("the stream", () => {
  let appListener: ((s: string) => void) | null = null;

  beforeEach(() => {
    jest.useFakeTimers();
    mockFetch.mockReset();
    Object.defineProperty(AppState, "currentState", { value: "active", configurable: true });
    jest.spyOn(AppState, "addEventListener").mockImplementation(((_: string, cb: (s: string) => void) => {
      appListener = cb;
      return { remove: () => (appListener = null) };
    }) as never);
  });
  afterEach(() => {
    jest.useRealTimers();
    jest.restoreAllMocks();
  });

  function Probe() {
    useInboxStream(true);
    return <Text testID="live">{useLiveStatus()}</Text>;
  }

  async function mount(qc = new QueryClient({ defaultOptions: { queries: { gcTime: Infinity, retry: false } } })) {
    const r = await render(
      <QueryClientProvider client={qc}>
        <Probe />
      </QueryClientProvider>,
    );
    return { ...r, qc };
  }

  const flush = () => act(async () => void (await Promise.resolve()));

  it("goes live on «ready», and an event re-reads what it names", async () => {
    mockFetch.mockResolvedValueOnce(stream(['event: ready\ndata: {}\n\nevent: message.new\ndata: {"conversation_id":"c9"}\n\n'])).mockReturnValue(new Promise(() => undefined));
    const qc = new QueryClient({ defaultOptions: { queries: { gcTime: Infinity, retry: false } } });
    const spy = jest.spyOn(qc, "invalidateQueries");
    const { getByTestId } = await mount(qc);
    await flush();
    await flush();
    expect(mockFetch.mock.calls[0]![1].headers.Authorization).toBe("Bearer tok");
    await act(async () => void jest.advanceTimersByTime(500));
    const keys = spy.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
    expect(keys).toContain(JSON.stringify(["inbox", "thread", "c9"]));
    expect(keys).toContain(JSON.stringify(["inbox", "list"]));
    // Inicio's «Necesita tu atención» is the same number as the tab's badge.
    expect(keys).toContain(JSON.stringify(["home"]));
    expect(getByTestId("live").props.children).not.toBe("reconnecting");
  });

  it("a closed phone hands the refusal to the session and does not knock again", async () => {
    // R7.2: the line is cut within its bound, and the reconnection is refused.
    const refused = { ok: false, status: 403, body: null };
    mockFetch.mockResolvedValue(refused);
    await mount();
    await flush();
    await flush();
    expect(mockSettle).toHaveBeenCalledWith(refused);
    await act(async () => void jest.advanceTimersByTime(60_000));
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("says «Reconectando…» only after 3 s without a line", async () => {
    mockFetch.mockRejectedValue(new Error("down"));
    const { getByTestId } = await mount();
    await flush();
    await flush();
    expect(getByTestId("live").props.children).not.toBe("reconnecting");
    await act(async () => void jest.advanceTimersByTime(RECONNECTING_AFTER_MS));
    expect(getByTestId("live").props.children).toBe("reconnecting");
  });

  it("closes in the background and reopens — re-reading — in front", async () => {
    mockFetch.mockReturnValue(new Promise(() => undefined));
    const qc = new QueryClient({ defaultOptions: { queries: { gcTime: Infinity, retry: false } } });
    const spy = jest.spyOn(qc, "invalidateQueries");
    const { getByTestId } = await mount(qc);
    await flush();
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const signal = mockFetch.mock.calls[0]![1].signal as AbortSignal;
    await act(async () => appListener?.("background"));
    expect(signal.aborted).toBe(true);
    expect(getByTestId("live").props.children).toBe("off");
    await act(async () => appListener?.("active"));
    await flush();
    expect(mockFetch).toHaveBeenCalledTimes(2);
    expect(spy.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey))).toContain(JSON.stringify(["inbox"]));
  });
});
