import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { createParser } from "eventsource-parser";
import { fetch } from "expo/fetch";
import { useEffect, useSyncExternalStore } from "react";
import { AppState } from "react-native";

import { API_URL } from "@/config";

import { APP_HEADERS, accessToken, refresh, settleRefusal } from "./client";
import { invalidateInbox, keys } from "./query";

/**
 * The Bandeja, live (spec 031, D17, R5.4, R5.5). One stream while the app is
 * in the foreground, over `expo/fetch` with the phone's credential. Events say
 * WHAT changed, never the text: the app re-reads it through its routes. When
 * the line drops it says «Reconectando…» and retries with a growing pause; when
 * the app comes back from the background it re-reads before letting anyone act.
 */
export type LiveStatus = "off" | "connecting" | "live" | "reconnecting";

export type InboxEvent = {
  event: "conversation.updated" | "message.new" | "message.status";
  conversation_id: string;
};

const NAMES = new Set(["conversation.updated", "message.new", "message.status"]);

let status: LiveStatus = "off";
const watchers = new Set<() => void>();
function setStatus(next: LiveStatus) {
  if (next === status) return;
  status = next;
  for (const w of [...watchers]) w();
}

export function useLiveStatus(): LiveStatus {
  return useSyncExternalStore(
    (cb) => {
      watchers.add(cb);
      return () => watchers.delete(cb);
    },
    () => status,
  );
}

/** Pause before the n-th retry: 1, 2, 4, 8, then every 10 s. */
export function backoff(attempt: number): number {
  return Math.min(10_000, 1000 * 2 ** Math.max(0, attempt - 1));
}

/** «Reconectando…» only after this long without a line: a blip is not news. */
export const RECONNECTING_AFTER_MS = 3000;

/** What one event makes stale. Debounced by the caller: a burst is one re-read. */
export function invalidationsFor(e: InboxEvent): { lists: true; conversation: string } {
  return { lists: true, conversation: e.conversation_id };
}

/** One SSE frame as the app reads it, or `null` for anything it does not act on. */
export function parseFrame(event: string | undefined, data: string): InboxEvent | null {
  if (!event || !NAMES.has(event)) return null;
  try {
    const parsed = JSON.parse(data) as Partial<InboxEvent>;
    return typeof parsed.conversation_id === "string"
      ? { event: event as InboxEvent["event"], conversation_id: parsed.conversation_id }
      : null;
  } catch {
    return null; // a malformed frame is ignored, never painted
  }
}

/** Back after a drop or from the background: everything the inbox shows, and Inicio. */
function rereadAll(qc: QueryClient): void {
  void qc.invalidateQueries({ queryKey: ["inbox"] });
  void qc.invalidateQueries({ queryKey: keys.home });
}

function makeInvalidator(qc: QueryClient) {
  let lists: ReturnType<typeof setTimeout> | null = null;
  const open = new Map<string, ReturnType<typeof setTimeout>>();
  return {
    handle(e: InboxEvent) {
      const what = invalidationsFor(e);
      if (lists) clearTimeout(lists);
      lists = setTimeout(() => invalidateInbox(qc), 400);
      const id = what.conversation;
      const prev = open.get(id);
      if (prev) clearTimeout(prev);
      open.set(
        id,
        setTimeout(() => {
          open.delete(id);
          void qc.invalidateQueries({ queryKey: keys.conversation(id) });
          void qc.invalidateQueries({ queryKey: keys.thread(id) });
        }, 250),
      );
    },
    cancel() {
      if (lists) clearTimeout(lists);
      for (const t of open.values()) clearTimeout(t);
      open.clear();
    },
  };
}

export function useInboxStream(enabled: boolean): void {
  const qc = useQueryClient();
  useEffect(() => {
    if (!enabled) return;
    const invalidator = makeInvalidator(qc);
    let controller: AbortController | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let downTimer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;
    let wasDown = false;
    let running = false;
    let foreground = AppState.currentState === "active";

    const stop = () => {
      running = false;
      controller?.abort();
      controller = null;
      if (timer) clearTimeout(timer);
      if (downTimer) clearTimeout(downTimer);
      timer = null;
      downTimer = null;
    };

    const connect = async () => {
      if (!foreground) return;
      running = true;
      controller = new AbortController();
      const signal = controller.signal;
      if (attempt === 0 && !wasDown) setStatus("connecting");
      try {
        const token = await accessToken();
        if (!token) return stop();
        const res = await fetch(`${API_URL}/console/lite/inbox/stream`, {
          headers: { ...APP_HEADERS, Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
          signal,
        });
        if (res.status === 401) {
          if (!(await refresh())) return stop();
          throw new Error("renewed");
        }
        // A closed phone, a person removed, the Bandeja turned off: knocking
        // again will not open it. The session hears why; the next return to
        // the foreground tries once more.
        if (res.status === 403) {
          await settleRefusal(res);
          setStatus("off");
          return stop();
        }
        if (!res.ok || !res.body) throw new Error(`stream ${res.status}`);
        const parser = createParser({
          onEvent: (msg) => {
            if (msg.event === "ready") {
              attempt = 0;
              if (downTimer) clearTimeout(downTimer);
              downTimer = null;
              // Back after a drop: whatever happened meanwhile is re-read, not guessed.
              if (wasDown) rereadAll(qc);
              wasDown = false;
              setStatus("live");
              return;
            }
            const event = parseFrame(msg.event, msg.data);
            if (event) invalidator.handle(event);
          },
        });
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          parser.feed(decoder.decode(value, { stream: true }));
        }
      } catch {
        /* dropped: handled below */
      }
      if (!running || signal.aborted || !foreground) return;
      attempt += 1;
      if (!wasDown) {
        wasDown = true;
        downTimer = setTimeout(() => setStatus("reconnecting"), RECONNECTING_AFTER_MS);
      }
      // While the line is down, the counts are what tells a stale screen apart.
      void qc.invalidateQueries({ queryKey: keys.counts });
      timer = setTimeout(() => void connect(), backoff(attempt));
    };

    const sub = AppState.addEventListener("change", (next) => {
      const wasForeground = foreground;
      foreground = next === "active";
      if (!foreground && wasForeground) {
        stop();
        setStatus("off");
      } else if (foreground && !wasForeground) {
        // R5.5: back from the background, re-read before anyone acts on it.
        rereadAll(qc);
        attempt = 0;
        wasDown = false;
        void connect();
      }
    });
    void connect();
    return () => {
      sub.remove();
      stop();
      invalidator.cancel();
      setStatus("off");
    };
  }, [enabled, qc]);
}
