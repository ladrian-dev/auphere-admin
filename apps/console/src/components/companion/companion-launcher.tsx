"use client";

import { Sparkles } from "lucide-react";
import { usePathname } from "next/navigation";
import * as React from "react";

import { Button } from "@nexus/ui";

import { useT } from "@/i18n/client";
import { type Role, can } from "@/lib/permissions";

import { companionClient } from "./client";
import { URL_PARAM, CompanionDrawer } from "./drawer";
import { readPageContext, suggestionKeys } from "./page-context";
import { pendingAction } from "./state";
import { useCompanion } from "./use-companion";

/**
 * `?companion=<thread>` as an external store.
 *
 * `popstate` covers back/forward; the drawer's own writes go through
 * `history.replaceState`, which fires no event, so the launcher notifies
 * itself via `companion:url` when it rewrites the URL. Cached by value:
 * `getSnapshot` has to be referentially stable or React loops.
 */
const URL_EVENT = "companion:url";

function subscribeToLocation(listener: () => void): () => void {
  window.addEventListener("popstate", listener);
  window.addEventListener(URL_EVENT, listener);
  return () => {
    window.removeEventListener("popstate", listener);
    window.removeEventListener(URL_EVENT, listener);
  };
}
function getUrlThread(): string | null {
  return new URLSearchParams(window.location.search).get(URL_PARAM);
}
function getUrlThreadServer(): string | null {
  return null;
}

/**
 * The bubble, and the mount point of the whole Companion (§4.1).
 *
 * Present across the console except `(auth)`, anchored bottom right, ⌘J
 * (⌘K is already the command palette). Four states: idle · working (an
 * activity ring) · a decision waiting (a dot) · disabled by role or cap,
 * with a tooltip saying which.
 *
 * `prefers-reduced-motion` replaces the ring with text rather than merely
 * slowing it: the ring IS the message, so removing the animation has to
 * leave the message behind, not nothing.
 *
 * Rendering nothing for a role without `companion:use` would be the easy
 * choice and the wrong one — a builder-less analyst would wonder where the
 * feature went. The bubble stays and explains itself.
 *
 * **The per-partner flag is the opposite case** (§10 of CONTRACT-V2).
 * `companion_enabled === false` means the partner does not have the
 * Companion at all, and then the bubble is **not mounted**: an off bubble
 * is absence, not a disabled button with a tooltip, because a disabled
 * button advertises something you cannot have. The two questions are
 * genuinely different and get genuinely different answers.
 *
 * While the flag is unknown, nothing is mounted either — a bubble that
 * appears and then vanishes is worse than one that arrives a beat late.
 * And a failed lookup stays closed: if we cannot show the partner has the
 * feature, we do not advertise it.
 */
export function CompanionLauncher({ role, userId }: { role: Role; userId: string | null }) {
  const t = useT();
  const pathname = usePathname();
  const allowed = can(role, "companion:use");

  // `null` = not asked yet. Distinct from `false` only in intent — both
  // render nothing — but keeping them apart is what makes the "loading"
  // and "empty" states of this component separately reachable and
  // separately testable.
  const [enabled, setEnabled] = React.useState<boolean | null>(null);

  React.useEffect(() => {
    let alive = true;
    void (async () => {
      const res = await companionClient.enabled();
      if (!alive) return;
      setEnabled(res.ok ? res.data.companion_enabled === true : false);
    })();
    return () => {
      alive = false;
    };
  }, []);

  // The URL is an external system too. Reading `?companion=` through a
  // store instead of an effect is what lets a pasted link open the drawer
  // without a setState-during-effect cascade — and it keeps working when
  // the user navigates back and forth.
  const urlThread = React.useSyncExternalStore(subscribeToLocation, getUrlThread, getUrlThreadServer);
  const [userOpen, setUserOpen] = React.useState<boolean | null>(null);
  const open = userOpen ?? urlThread !== null;
  const setOpen = React.useCallback((next: boolean) => setUserOpen(next), []);

  const [budgetExhausted, setBudgetExhausted] = React.useState(false);
  const [now, setNow] = React.useState(() => Date.now());
  const controller = useCompanion();
  const { openThread, refreshThreads, state } = controller;

  const pageContext = React.useMemo(() => readPageContext(pathname), [pathname]);
  const suggestions = React.useMemo(
    () => suggestionKeys(pageContext).map((key) => t(key, { client: pageContext.client_ref ?? "" })),
    [pageContext, t],
  );

  // ⌘J / Ctrl+J. ⌘K is already the command palette (CP-07).
  React.useEffect(() => {
    // A shortcut for a feature the partner does not have would be a
    // keypress that does nothing visible — worse than no shortcut.
    if (!allowed || enabled !== true) return;
    function onKey(e: KeyboardEvent) {
      if (e.key.toLowerCase() === "j" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setUserOpen((v) => !(v ?? false));
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [allowed, enabled]);

  React.useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 5000);
    return () => window.clearInterval(id);
  }, []);

  // First open: load the threads, the budget, and whatever thread the URL
  // names. The URL is the shareable half of the feature, so it wins over
  // "the most recent thread".
  const loadedRef = React.useRef(false);
  React.useEffect(() => {
    if (!open || !allowed || enabled !== true || loadedRef.current) return;
    loadedRef.current = true;
    void (async () => {
      const [threads, budget] = await Promise.all([refreshThreads(), companionClient.budget()]);
      if (budget.ok) setBudgetExhausted(budget.data.exhausted);
      const wanted = new URLSearchParams(window.location.search).get(URL_PARAM);
      const target = wanted && threads.some((th) => th.id === wanted) ? wanted : null;
      if (target) await openThread(target);
    })();
  }, [allowed, enabled, open, openThread, refreshThreads]);

  // Shallow URL sync — no server re-render, no `useSearchParams` Suspense.
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    const current = url.searchParams.get(URL_PARAM);
    const next = open ? controller.threadId : null;
    if (current === next) return;
    if (next) url.searchParams.set(URL_PARAM, next);
    else url.searchParams.delete(URL_PARAM);
    window.history.replaceState(window.history.state, "", url.toString());
    window.dispatchEvent(new Event(URL_EVENT));
  }, [controller.threadId, open]);

  // §10 of CONTRACT-V2. AFTER every hook, so the hook order never varies
  // between renders — and after the URL effect, so a pasted
  // `?companion=<thread>` on a partner without the feature does not leave
  // a parameter behind that nothing will ever consume.
  //
  // `null` (not asked yet) and `false` (the partner does not have it) both
  // render nothing. Absence, not a disabled button.
  if (enabled !== true) return null;

  const pending = pendingAction(state, now);
  const busy = state.runStatus === "running";
  const disabledReason = !allowed
    ? t("companion.bubble.disabled.role")
    : budgetExhausted
      ? t("companion.bubble.disabled.cap")
      : null;

  const label = !allowed
    ? t("companion.bubble.disabled.role")
    : pending
      ? t("companion.bubble.awaiting")
      : busy
        ? t("companion.bubble.busy")
        : t("companion.open");

  return (
    <>
      <div className="fixed right-4 bottom-4 z-40 flex flex-col items-end gap-2 print:hidden">
        {/* Reduced motion: the ring carries the "working" message, so it is
            replaced by words rather than simply stopped. */}
        {busy ? (
          <span className="hidden rounded-full border border-border bg-popover px-2 py-1 text-xs text-muted-foreground motion-reduce:block">
            {t("companion.working")}
          </span>
        ) : null}

        <Button
          size="icon-lg"
          aria-label={label}
          aria-haspopup="dialog"
          aria-expanded={open}
          disabled={!allowed}
          title={disabledReason ?? t("companion.shortcut")}
          onClick={() => setOpen(true)}
          className="relative size-12 rounded-full shadow-lg"
        >
          <Sparkles aria-hidden="true" />
          {busy ? (
            <span
              aria-hidden="true"
              className="absolute inset-0 animate-ping rounded-full border-2 border-primary motion-reduce:animate-none motion-reduce:opacity-0"
            />
          ) : null}
          {pending ? (
            <span
              aria-hidden="true"
              className="absolute top-0 right-0 size-4 rounded-full border-2 border-background bg-status-warning"
            />
          ) : null}
        </Button>
      </div>

      {allowed ? (
        <CompanionDrawer
          open={open}
          onOpenChange={setOpen}
          controller={controller}
          pageContext={pageContext}
          suggestions={suggestions}
          currentUserId={userId}
          exhausted={budgetExhausted}
        />
      ) : null}
    </>
  );
}
