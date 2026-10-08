import { render } from "@testing-library/react";
import { vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import type { InboxInitial } from "../inbox-view";
import { conversation, page } from "./fixtures";

/**
 * Spec 030: renders the whole Inbox with its Server Actions as mocks (`a`)
 * and a controllable `EventSource` (`stream`). Each test file mocks
 * `@/app/(console)/inbox/actions` with `actionsMock` before importing.
 */
export const a = {
  listConversationsAction: vi.fn(),
  inboxCountsAction: vi.fn(),
  openConversationAction: vi.fn(),
  loadOlderAction: vi.fn(),
  markUnreadAction: vi.fn(),
  takeOverAction: vi.fn(),
  giveBackAction: vi.fn(),
  sendMessageAction: vi.fn(),
  resolveAction: vi.fn(),
  reopenAction: vi.fn(),
  setTagsAction: vi.fn(),
  suggestedTagsAction: vi.fn(),
  setNoteAction: vi.fn(),
  repliesAction: vi.fn(),
  createReplyAction: vi.fn(),
  editReplyAction: vi.fn(),
  archiveReplyAction: vi.fn(),
};

export class FakeEventSource {
  static last: FakeEventSource | null = null;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  listeners = new Map<string, Set<(e: MessageEvent<string>) => void>>();
  constructor(public url: string) {
    FakeEventSource.last = this;
  }
  addEventListener(name: string, fn: (e: MessageEvent<string>) => void) {
    if (!this.listeners.has(name)) this.listeners.set(name, new Set());
    this.listeners.get(name)!.add(fn);
  }
  removeEventListener(name: string, fn: (e: MessageEvent<string>) => void) {
    this.listeners.get(name)?.delete(fn);
  }
  emit(name: string, data: unknown) {
    for (const fn of this.listeners.get(name) ?? []) fn(new MessageEvent(name, { data: JSON.stringify(data) }));
  }
  close() {}
}

export function resetActions() {
  for (const fn of Object.values(a)) fn.mockReset();
  a.listConversationsAction.mockResolvedValue({ ok: true, data: page([conversation()]) });
  a.suggestedTagsAction.mockResolvedValue({ ok: true, data: { tags: [] } });
  a.repliesAction.mockResolvedValue({ ok: true, data: [] });
  a.inboxCountsAction.mockResolvedValue({ ok: true, data: { unread: 0, waiting: 0 } });
  vi.stubGlobal("EventSource", FakeEventSource);
}

export function renderInbox(initial: Partial<InboxInitial> = {}) {
  const full: InboxInitial = {
    filter: "all",
    query: "",
    agent: null,
    agents: [],
    page: page([conversation()]),
    selectedId: null,
    open: null,
    replies: [],
    suggested: [],
    ...initial,
  };
  return render(
    <LocaleProvider locale="es">
      <InboxViewRef.current initial={full} />
    </LocaleProvider>,
  );
}

/** Set by each test file after its dynamic import (the actions mock must load first). */
export const InboxViewRef: { current: React.ComponentType<{ initial: InboxInitial }> } = {
  current: () => null,
};
