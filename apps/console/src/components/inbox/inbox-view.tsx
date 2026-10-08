"use client";

import { WifiOff } from "lucide-react";
import * as React from "react";

import { Alert, AlertDescription, Button, Sheet, SheetContent, SheetTitle, cn } from "@nexus/ui";

import {
  archiveReplyAction,
  createReplyAction,
  editReplyAction,
  giveBackAction,
  inboxCountsAction,
  listConversationsAction,
  loadOlderAction,
  markUnreadAction,
  openConversationAction,
  reopenAction,
  repliesAction,
  resolveAction,
  sendMessageAction,
  setNoteAction,
  setTagsAction,
  suggestedTagsAction,
  takeOverAction,
} from "@/app/(console)/inbox/actions";
import { useT } from "@/i18n/client";
import type { ActionResult } from "@/lib/actions";
import type {
  InboxCounts,
  InboxDetail,
  InboxFilter,
  InboxPage,
  InboxThread,
  InboxThreadItem,
  SavedReply,
} from "@/lib/backend/inbox";
import { inboxAttachmentUrl } from "@/lib/inbox-urls";

import { Composer } from "./composer";
import { ContactPanel } from "./contact-panel";
import { ConversationList } from "./conversation-list";
import { composerMode, initialsOf, sendErrorOf, type SendError } from "./inbox-model";
import { reloadPage } from "./reload";
import type { RepliesApi } from "./saved-replies";
import { Thread, ThreadSkeleton } from "./thread";
import { ThreadHeader } from "./thread-header";
import { announceCounts, useInboxStream, type InboxEvent } from "./use-inbox-stream";

export type InboxInitial = {
  filter: InboxFilter;
  query: string;
  /** Spec 030: one agent's numbers only; `agents` is empty with one agent. */
  agent: string | null;
  agents: { id: string; name: string }[];
  page: InboxPage | null;
  selectedId: string | null;
  open: { detail: InboxDetail; thread: InboxThread } | null;
  replies: SavedReply[] | null;
  suggested: string[];
};

const PANEL_KEY = "nexus.inbox.panel";
const PANEL_EVENT = "nexus:inbox-panel";
/** When storage is blocked (private window, preview) the panel still toggles; it just won't remember. */
let panelMemory: boolean | null = null;

function readPanelPref(): boolean | null {
  try {
    const v = window.localStorage.getItem(PANEL_KEY);
    return v === "open" ? true : v === "closed" ? false : panelMemory;
  } catch {
    return panelMemory;
  }
}

function writePanelPref(open: boolean): void {
  panelMemory = open;
  try {
    window.localStorage.setItem(PANEL_KEY, open ? "open" : "closed");
  } catch {
    /* blocked storage: `panelMemory` carries it for this tab */
  }
  window.dispatchEvent(new Event(PANEL_EVENT));
}

function subscribePanel(onChange: () => void): () => void {
  window.addEventListener(PANEL_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(PANEL_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

/** Remembered choice, else open from 1280 px up (folded below, as designed). */
const panelSnapshot = () => readPanelPref() ?? window.innerWidth >= 1280;
const panelServerSnapshot = () => false;

/** The panel is a column beside the thread only when the Inbox itself has
 *  room — list (320) + thread (≥ 480) + panel (300). Otherwise a modal sheet:
 *  as an overlay it hid the thread's own buttons from a keyboard user (WCAG
 *  2.4.11), and a sheet traps and returns the focus. Measured on the Inbox,
 *  not the window: an open or folded sidebar changes the room at the same
 *  window width. */
const WIDE_PX = 1100;
const WIDE_FALLBACK = "(min-width: 1280px)";

function useWide(ref: React.RefObject<HTMLElement | null>): boolean {
  const [wide, setWide] = React.useState(() =>
    typeof window !== "undefined" && typeof ResizeObserver === "undefined"
      ? window.matchMedia(WIDE_FALLBACK).matches
      : false,
  );
  React.useEffect(() => {
    const el = ref.current;
    if (el && typeof ResizeObserver !== "undefined") {
      const observer = new ResizeObserver((entries) => setWide((entries[0]?.contentRect.width ?? 0) >= WIDE_PX));
      observer.observe(el);
      return () => observer.disconnect();
    }
    // No ResizeObserver (very old browsers, tests): the window decides.
    const mql = window.matchMedia(WIDE_FALLBACK);
    const sync = () => setWide(mql.matches);
    mql.addEventListener("change", sync);
    return () => mql.removeEventListener("change", sync);
  }, [ref]);
  return wide;
}

function syncUrl(selectedId: string | null, filter: InboxFilter, query: string, agent: string | null): void {
  const params = new URLSearchParams();
  if (selectedId) params.set("c", selectedId);
  if (filter !== "all") params.set("filter", filter);
  if (query.trim()) params.set("q", query.trim());
  if (agent) params.set("agent", agent);
  const qs = params.toString();
  window.history.replaceState(null, "", qs ? `/inbox?${qs}` : "/inbox");
}

/** 401/403 from an action: the session expired or the Inbox was taken away —
 *  the page guard decides where this person belongs now. */
function guard<T>(r: ActionResult<T>): ActionResult<T> {
  if (!r.ok && (r.status === 401 || r.status === 403)) reloadPage();
  return r;
}

/**
 * The Bandeja de entrada (spec 030, US5–US10, US12). The list on the left
 * (320 px), the open conversation in the middle, the contact panel on the
 * right — folded by default under 1280 px and remembered per browser. On a
 * phone the list and the conversation take turns.
 *
 * Every read and write goes through Server Actions (the API decides, under
 * the client's RLS); the live stream only says WHAT changed and this view
 * re-reads it. A send appears at once (`useOptimistic`) and goes away if the
 * API refuses it, with the reason.
 */
export function InboxView({ initial }: { initial: InboxInitial }) {
  const t = useT();
  const [now, setNow] = React.useState(() => new Date());
  const [filter, setFilter] = React.useState<InboxFilter>(initial.filter);
  const [query, setQuery] = React.useState(initial.query);
  const [agent, setAgent] = React.useState<string | null>(initial.agent);
  const [page, setPage] = React.useState<InboxPage | null>(initial.page);
  const [listLoading, setListLoading] = React.useState(false);
  const [listFailed, setListFailed] = React.useState(initial.page === null);
  const [loadingMore, setLoadingMore] = React.useState(false);
  const [counts, setCounts] = React.useState<InboxCounts>(initial.page?.counts ?? { unread: 0, waiting: 0 });

  const [selectedId, setSelectedId] = React.useState<string | null>(initial.selectedId);
  const [detail, setDetail] = React.useState<InboxDetail | null>(initial.open?.detail ?? null);
  const [items, setItems] = React.useState<InboxThreadItem[]>(initial.open?.thread.items ?? []);
  const [nextBefore, setNextBefore] = React.useState<string | null>(initial.open?.thread.next_before ?? null);
  const [threadLoading, setThreadLoading] = React.useState(false);
  const [threadFailed, setThreadFailed] = React.useState(Boolean(initial.selectedId && !initial.open));
  const [loadingOlder, setLoadingOlder] = React.useState(false);

  const [busy, setBusy] = React.useState(false);
  const [sendError, setSendError] = React.useState<SendError | "generic" | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [attaching, setAttaching] = React.useState<string | null>(null);
  const [replies, setReplies] = React.useState<SavedReply[] | null>(initial.replies);
  const [suggested, setSuggested] = React.useState<string[]>(initial.suggested);
  const panelPref = React.useSyncExternalStore(subscribePanel, panelSnapshot, panelServerSnapshot);
  const frame = React.useRef<HTMLDivElement>(null);
  const wide = useWide(frame);
  // Below 1280 px the sheet is opened on purpose each time; it is not remembered.
  const [sheetOpen, setSheetOpen] = React.useState(false);
  const panelOpen = wide ? panelPref : sheetOpen;

  const [optimistic, addOptimistic] = React.useOptimistic(items, (state: InboxThreadItem[], item: InboxThreadItem) => [
    ...state,
    item,
  ]);
  const [, startTransition] = React.useTransition();

  // ── housekeeping ────────────────────────────────────────────────────
  React.useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(id);
  }, []);
  React.useEffect(() => announceCounts(counts), [counts]);
  React.useEffect(() => {
    if (!notice) return;
    const id = window.setTimeout(() => setNotice(null), 4000);
    return () => window.clearTimeout(id);
  }, [notice]);

  // ── reads ───────────────────────────────────────────────────────────
  const latest = React.useRef({ filter, query, agent, selectedId });
  latest.current = { filter, query, agent, selectedId };

  /** `reset`: the filter or the search changed — the old rows are not an answer
   *  any more, so the list shows its loading (or its error). A background
   *  refresh that fails keeps what is on screen. */
  const refreshList = React.useCallback(async (reset = false) => {
    const { filter: f, query: q, agent: a } = latest.current;
    if (reset) setPage(null);
    setListLoading(true);
    const r = guard(await listConversationsAction({ filter: f, q: q.trim() || undefined, agent: a ?? undefined }));
    setListLoading(false);
    if (r.ok) {
      setPage(r.data);
      setCounts(r.data.counts);
      setListFailed(false);
    } else if (reset) {
      setListFailed(true);
    }
  }, []);

  const refreshOpen = React.useCallback(async (id: string, markRead: boolean) => {
    const r = guard(await openConversationAction({ id, markRead }));
    if (latest.current.selectedId !== id) return;
    if (r.ok) {
      setDetail(r.data.detail);
      setItems(r.data.thread.items);
      setNextBefore(r.data.thread.next_before);
      setThreadFailed(false);
    } else {
      setThreadFailed(true);
    }
  }, []);

  const open = React.useCallback(
    async (id: string) => {
      setSelectedId(id);
      latest.current.selectedId = id;
      setSendError(null);
      setThreadLoading(true);
      setDetail(null);
      setItems([]);
      syncUrl(id, latest.current.filter, latest.current.query, latest.current.agent);
      await refreshOpen(id, true);
      setThreadLoading(false);
      setPage((p) => (p ? { ...p, items: p.items.map((c) => (c.id === id ? { ...c, unread: false } : c)) } : p));
      void refreshList();
    },
    [refreshOpen, refreshList],
  );

  // First paint with ?c= already loaded by the server: still mark it read.
  React.useEffect(() => {
    if (initial.selectedId && initial.open) void openConversationAction({ id: initial.selectedId, markRead: true });
  }, [initial.selectedId, initial.open]);

  // Filter now, search after a short pause.
  const firstRun = React.useRef(true);
  React.useEffect(() => {
    if (firstRun.current) {
      firstRun.current = false;
      return;
    }
    syncUrl(latest.current.selectedId, filter, query, agent);
    const id = window.setTimeout(() => void refreshList(true), query ? 250 : 0);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refreshList reads the latest filter/query itself
  }, [filter, query, agent]);

  // ── live ────────────────────────────────────────────────────────────
  const pendingList = React.useRef<number | null>(null);
  const pendingOpen = React.useRef<number | null>(null);
  const onEvent = React.useCallback(
    (e: InboxEvent) => {
      if (pendingList.current) window.clearTimeout(pendingList.current);
      pendingList.current = window.setTimeout(() => void refreshList(), 400);
      const current = latest.current.selectedId;
      if (current && e.conversation_id === current) {
        if (pendingOpen.current) window.clearTimeout(pendingOpen.current);
        pendingOpen.current = window.setTimeout(
          () => void refreshOpen(current, document.visibilityState === "visible"),
          250,
        );
      }
    },
    [refreshList, refreshOpen],
  );
  const live = useInboxStream(onEvent, () => {
    // A network blip rejects; that is what «Reconectando…» already says.
    void inboxCountsAction()
      .then(guard)
      .catch(() => undefined);
  });

  // ── writes ──────────────────────────────────────────────────────────
  async function control(r: ActionResult<InboxDetail>) {
    if (r.ok) {
      setDetail(r.data);
      setSendError(null);
    } else if (r.status === 412 && r.info && typeof r.info.conversation === "object" && r.info.conversation) {
      setDetail(r.info.conversation as InboxDetail);
      setNotice(t("inbox.stale"));
    } else {
      setNotice(t("inbox.error.action"));
    }
    if (detail) await refreshOpen(detail.id, false);
    void refreshList();
  }

  async function takeOver() {
    if (!detail) return;
    setBusy(true);
    await control(guard(await takeOverAction({ id: detail.id, version: detail.control_version })));
    setBusy(false);
  }
  async function giveBack() {
    if (!detail) return;
    setBusy(true);
    await control(guard(await giveBackAction({ id: detail.id, version: detail.control_version })));
    setBusy(false);
  }
  async function resolve() {
    if (!detail) return;
    setBusy(true);
    const r = guard(await resolveAction({ id: detail.id }));
    if (r.ok) setNotice(t("inbox.toast.resolved"));
    await control(r);
    setBusy(false);
  }
  async function reopen() {
    if (!detail) return;
    setBusy(true);
    await control(guard(await reopenAction({ id: detail.id })));
    setBusy(false);
  }
  async function markUnread() {
    if (!detail) return;
    const id = detail.id;
    const r = guard(await markUnreadAction({ id }));
    if (!r.ok) {
      setNotice(t("inbox.error.action"));
      return;
    }
    setNotice(t("inbox.toast.unread"));
    back();
    void refreshList();
  }
  function back() {
    setSelectedId(null);
    latest.current.selectedId = null;
    setDetail(null);
    setItems([]);
    syncUrl(null, latest.current.filter, latest.current.query, latest.current.agent);
  }

  function send(text: string): Promise<boolean> {
    const id = detail?.id;
    if (!id) return Promise.resolve(false);
    return new Promise((done) => {
      startTransition(async () => {
        addOptimistic({
          type: "message",
          id: `pending-${Date.now()}`,
          at: new Date().toISOString(),
          direction: "outbound",
          author: { kind: "member", name: null, is_me: true },
          text,
          media: null,
          delivery: "pending",
          failure_reason: null,
          kind: null,
          detail: null,
        });
        const r = guard(await sendMessageAction({ id, text }));
        if (r.ok) {
          setSendError(null);
          await refreshOpen(id, false);
          done(true);
        } else {
          setSendError(sendErrorOf(r.code));
          if (r.code) await refreshOpen(id, false);
          done(false);
        }
      });
    });
  }

  async function attach(file: File) {
    if (!detail) return;
    const id = detail.id;
    setAttaching(file.name);
    setSendError(null);
    try {
      const form = new FormData();
      form.set("file", file, file.name);
      const res = await fetch(inboxAttachmentUrl(id), { method: "POST", body: form });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { detail?: { code?: string } } | null;
        setSendError(sendErrorOf(body?.detail?.code));
      }
    } catch {
      setSendError("generic");
    } finally {
      setAttaching(null);
      await refreshOpen(id, false);
    }
  }

  async function setTags(tags: string[]): Promise<boolean> {
    if (!detail) return false;
    const r = guard(await setTagsAction({ id: detail.id, tags }));
    if (!r.ok) return false;
    setDetail((d) => (d ? { ...d, tags: r.data.tags } : d));
    const fresh = await suggestedTagsAction();
    if (fresh.ok) setSuggested(fresh.data.tags);
    void refreshList();
    return true;
  }

  async function setNote(body: string): Promise<boolean> {
    if (!detail) return false;
    const r = guard(await setNoteAction({ id: detail.id, body }));
    return r.ok;
  }

  const repliesApi: RepliesApi = {
    async create(reply) {
      const r = await createReplyAction(reply);
      if (r.ok) await reloadReplies();
      return r.ok;
    },
    async edit(id, reply) {
      const r = await editReplyAction({ id, ...reply });
      if (r.ok) await reloadReplies();
      return r.ok;
    },
    async archive(id) {
      const r = await archiveReplyAction({ id });
      if (r.ok) await reloadReplies();
      return r.ok;
    },
  };
  async function reloadReplies() {
    const r = await repliesAction();
    if (r.ok) setReplies(r.data);
  }

  async function more() {
    if (!page?.next_cursor) return;
    setLoadingMore(true);
    const r = await listConversationsAction({
      filter,
      q: query.trim() || undefined,
      agent: agent ?? undefined,
      cursor: page.next_cursor,
    });
    setLoadingMore(false);
    if (r.ok) setPage({ ...r.data, items: [...page.items, ...r.data.items] });
  }

  async function older() {
    if (!detail || !nextBefore) return;
    setLoadingOlder(true);
    const r = await loadOlderAction({ id: detail.id, before: nextBefore });
    setLoadingOlder(false);
    if (r.ok) {
      setItems((cur) => [...r.data.items, ...cur]);
      setNextBefore(r.data.next_before);
    }
  }

  function togglePanel() {
    if (wide) writePanelPref(!panelPref);
    else setSheetOpen((v) => !v);
  }

  // ── render ──────────────────────────────────────────────────────────
  const initials = detail ? initialsOf(detail.contact.name) : "·";
  return (
    <div
      ref={frame}
      className="flex h-[calc(100svh-8rem)] min-h-[32rem] flex-col overflow-hidden rounded-md border border-border bg-card"
    >
      <div className="flex items-center gap-3 border-b border-border px-4 py-2">
        <h1 className="text-base font-semibold">{t("inbox.title")}</h1>
        <span className="flex-1" />
        <span role="status" className="text-xs text-muted-foreground">
          {notice}
        </span>
        {live === "reconnecting" ? (
          <span role="status" className="flex items-center gap-1 text-xs text-status-warning-text" title={t("inbox.live.reconnecting.hint")}>
            <WifiOff className="size-3" aria-hidden="true" />
            {t("inbox.live.reconnecting")}
          </span>
        ) : null}
      </div>

      <div className="relative flex min-h-0 flex-1">
        <div className={cn("w-full shrink-0 border-border md:flex md:w-80 md:border-r", selectedId ? "hidden" : "flex")}>
          <ConversationList
            page={page}
            loading={listLoading}
            failed={listFailed}
            filter={filter}
            query={query}
            agent={agent}
            agents={initial.agents}
            counts={counts}
            selectedId={selectedId}
            now={now}
            loadingMore={loadingMore}
            onFilter={setFilter}
            onQuery={setQuery}
            onAgent={setAgent}
            onOpen={(id) => void open(id)}
            onMore={() => void more()}
            onRetry={() => void refreshList(true)}
            onClear={() => {
              setFilter("all");
              setQuery("");
              setAgent(null);
            }}
          />
        </div>

        <section
          aria-label={detail ? detail.contact.name : t("inbox.thread")}
          className={cn("min-w-0 flex-1 flex-col", selectedId ? "flex" : "hidden md:flex")}
        >
          {!selectedId ? (
            <p className="m-auto max-w-xs p-6 text-center text-sm text-muted-foreground text-pretty">{t("inbox.pick")}</p>
          ) : threadFailed ? (
            <div className="m-auto flex max-w-sm flex-col items-center gap-3 p-6">
              <Alert variant="destructive" role="alert">
                <AlertDescription>{t("inbox.thread.error")}</AlertDescription>
              </Alert>
              <Button type="button" variant="outline" onClick={() => selectedId && void open(selectedId)}>
                {t("inbox.thread.retry")}
              </Button>
            </div>
          ) : !detail || threadLoading ? (
            <ThreadSkeleton label={t("inbox.thread.loading")} />
          ) : (
            <>
              <ThreadHeader
                detail={detail}
                initials={initials}
                busy={busy}
                panelOpen={panelOpen}
                onBack={back}
                onUnread={() => void markUnread()}
                onResolve={() => void resolve()}
                onReopen={() => void reopen()}
                onTogglePanel={togglePanel}
              />
              <Thread
                items={optimistic}
                hasOlder={Boolean(nextBefore)}
                loadingOlder={loadingOlder}
                contactInitials={initials}
                now={now}
                onOlder={() => void older()}
              />
              <Composer
                key={detail.id}
                mode={composerMode(detail)}
                busy={busy}
                sendError={sendError}
                replies={replies}
                repliesApi={repliesApi}
                attaching={attaching}
                onTakeOver={() => void takeOver()}
                onGiveBack={() => void giveBack()}
                onReopen={() => void reopen()}
                onSend={send}
                onAttach={(f) => void attach(f)}
              />
            </>
          )}
        </section>

        {detail && wide && panelOpen && !threadLoading ? (
          <div className="flex w-75 shrink-0 border-l border-border">
            <ContactPanel
              detail={detail}
              initials={initials}
              suggested={suggested}
              now={now}
              onClose={togglePanel}
              onTags={setTags}
              onNote={setNote}
            />
          </div>
        ) : null}
        {detail && !wide ? (
          <Sheet open={sheetOpen && !threadLoading} onOpenChange={(open) => setSheetOpen(open)}>
            <SheetContent side="right" showCloseButton={false} className="w-80 max-w-full gap-0 p-0">
              <SheetTitle className="sr-only">{t("inbox.panel")}</SheetTitle>
              <ContactPanel
                detail={detail}
                initials={initials}
                suggested={suggested}
                now={now}
                onClose={() => setSheetOpen(false)}
                onTags={setTags}
                onNote={setNote}
              />
            </SheetContent>
          </Sheet>
        ) : null}
      </div>
    </div>
  );
}
