"use client";

import { MessageSquarePlus, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button, Sheet, SheetContent, SheetDescription, SheetTitle } from "@nexus/ui";

import { useT } from "@/i18n/client";

import { Composer } from "./composer";
import {
  MAX_WIDTH,
  MIN_WIDTH,
  companionClient,
  getMode,
  getModeServer,
  getWidth,
  getWidthServer,
  setMode,
  setWidth,
  subscribeUi,
} from "./client";
import { Meters } from "./meters";
import type { PageContext } from "./page-context";
import { pendingAction } from "./state";
import { Timeline } from "./timeline";
import type { CompanionController } from "./use-companion";
import type { Decision, IntakeSlot } from "./types";

/**
 * The drawer (§4.2 / §14).
 *
 * Three decisions live here and each has a reason beyond taste:
 *
 * - **Width is resizable with the keyboard, not only by dragging.** WCAG
 *   2.2 adds 2.5.7 Dragging Movements: a function available only through a
 *   drag fails. So the grabber is a focusable `separator` with arrow keys,
 *   and the drag is the shortcut, not the mechanism.
 * - **`Esc` closes — unless a confirmation is pending.** Base UI hands us
 *   the reason for the close and a `cancel()`, so escape and outside-press
 *   are refused while a decision is owed, and we say why. Losing a pending
 *   decision to a stray keypress is the expensive mistake here.
 * - **The active thread lives in the URL, written with
 *   `history.replaceState`.** `?companion=<id>` has to be shareable inside
 *   the team, but the drawer is mounted in the layout: `router.replace`
 *   would re-run the page's server components on every open. Shallow
 *   history also spares us wrapping this in `<Suspense>` for
 *   `useSearchParams`.
 */
const URL_PARAM = "companion";
const WIDTH_STEP = 16;
const WIDTH_STEP_LARGE = 64;

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  controller: CompanionController;
  pageContext: PageContext;
  suggestions: string[];
  currentUserId: string | null;
  exhausted: boolean;
};

export function CompanionDrawer({
  open,
  onOpenChange,
  controller,
  pageContext,
  suggestions,
  currentUserId,
  exhausted,
}: Props) {
  const t = useT();
  const { state, threads, threadId, status, errorDetail, partial, reconnecting, deciding, decisionFailure } = controller;

  // `localStorage` is an external system, so it is subscribed to rather
  // than copied into state inside an effect. The server snapshot is the
  // default width, which is what hydration renders.
  const width = React.useSyncExternalStore(subscribeUi, getWidth, getWidthServer);
  const mode = React.useSyncExternalStore(subscribeUi, getMode, getModeServer);
  const [text, setText] = React.useState("");
  const composerRef = React.useRef<HTMLTextAreaElement | null>(null);
  const [now, setNow] = React.useState(() => Date.now());
  const [blocked, setBlocked] = React.useState<string | null>(null);

  // Only for expiry of the pending card; one tick a second is enough.
  React.useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const pending = pendingAction(state, now);
  const busy = state.runStatus === "running";

  const onModeChange = React.useCallback(
    (next: "consult" | "build") => {
      setMode(next);
      // The thread carries its own mode too: whoever opens the shared URL
      // must get the same tool set. `localStorage` only seeds a new thread.
      if (threadId) void companionClient.patchThread(threadId, { mode: next });
    },
    [threadId],
  );

  const onSend = React.useCallback(() => {
    const value = text.trim();
    if (!value) return;
    setText("");
    void controller.send(value, pageContext, mode);
  }, [controller, mode, pageContext, text]);

  const onSuggestion = React.useCallback(
    (suggestion: string) => {
      setText(suggestion);
      composerRef.current?.focus();
    },
    [],
  );

  // Answering an intake slot is an ordinary turn in the same thread — not
  // a form submit and not a new endpoint (§2.2).
  const onAnswerSlot = React.useCallback((slot: IntakeSlot) => {
    setText((prev) => (prev ? `${prev}\n${slot.label}: ` : `${slot.label}: `));
    composerRef.current?.focus();
  }, []);

  const onDecide = React.useCallback(
    (actionId: string, decision: Decision, note?: string) => {
      void controller.decide(actionId, decision, note);
    },
    [controller],
  );

  /**
   * Refusing to close is only legitimate if the user is TOLD why (WCAG
   * 2.1.2: they must be advised of the method to leave). The toast alone
   * does not do that: `Toaster` is mounted in the root layout, outside
   * this dialog, and a modal Base UI dialog marks outside content inert —
   * so a screen reader would never hear it. The message is therefore
   * announced from a live region INSIDE the drawer, with the toast as the
   * visual echo for sighted users looking elsewhere.
   */
  function requestClose(next: boolean, reason?: string): boolean {
    if (next) return true;
    if (pending && (reason === "escape-key" || reason === "outside-press")) {
      announceBlocked();
      return false;
    }
    return true;
  }

  function announceBlocked(): void {
    setBlocked(t("companion.closeBlocked"));
    toast.warning(t("companion.closeBlocked"));
  }

  const clientRef = pageContext.client_ref;
  const phaseLabel = state.phase ? t(`companion.phase.${state.phase}` as const) : null;

  return (
    <Sheet
      open={open}
      onOpenChange={(nextOpen, details) => {
        if (!requestClose(nextOpen, details.reason)) {
          details.cancel();
          return;
        }
        onOpenChange(nextOpen);
      }}
    >
      <SheetContent
        side="right"
        showCloseButton={false}
        aria-describedby={undefined}
        className="flex w-full flex-col gap-0 p-0 sm:max-w-none md:w-[var(--companion-width)]"
        style={{ "--companion-width": `${width}px` } as React.CSSProperties}
      >
        <ResizeHandle width={width} onWidth={setWidth} />

        <header className="flex min-w-0 items-center gap-2 border-b border-border px-4 py-3">
          <div className="min-w-0 flex-1">
            <SheetTitle className="truncate text-sm">{t("companion.title")}</SheetTitle>
            <SheetDescription className="sr-only">{t("companion.empty.body")}</SheetDescription>
            <p className="mt-1 flex min-w-0 flex-wrap items-center gap-2 text-xs text-muted-foreground">
              {clientRef ? (
                <span className="truncate font-mono">{t("companion.context.client", { ref: clientRef })}</span>
              ) : (
                <span className="truncate font-mono">{t("companion.context.here", { route: pageContext.route })}</span>
              )}
              {phaseLabel && busy ? (
                <span className="shrink-0 rounded-full border border-border px-2 py-px">{phaseLabel}</span>
              ) : null}
              {reconnecting ? <span className="shrink-0">{t("companion.reconnecting")}</span> : null}
            </p>
          </div>

          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={t("companion.thread.new")}
            disabled={!!pending}
            onClick={() => {
              controller.setThreadId(null);
              setText("");
              composerRef.current?.focus();
            }}
          >
            <MessageSquarePlus aria-hidden="true" />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={t("companion.close")}
            onClick={() => {
              // The explicit ✕ is guarded too: an accidental click must not
              // discard a decision the graph is blocked on.
              if (pending) {
                announceBlocked();
                return;
              }
              onOpenChange(false);
            }}
          >
            <X aria-hidden="true" />
          </Button>
        </header>

        {threads.length > 0 ? (
          <div className="min-w-0 border-b border-border px-4 py-2">
            <label htmlFor="companion-thread" className="sr-only">
              {t("companion.thread.select")}
            </label>
            <select
              id="companion-thread"
              value={threadId ?? ""}
              disabled={!!pending}
              onChange={(e) => {
                const id = e.target.value;
                if (!id) return;
                void controller.openThread(id);
              }}
              className="h-8 w-full min-w-0 rounded-sm border border-border bg-background px-2 text-xs focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
            >
              <option value="">{t("companion.thread.new")}</option>
              {threads.map((th) => (
                <option key={th.id} value={th.id}>
                  {th.title || t("companion.thread.untitled")}
                </option>
              ))}
            </select>
          </div>
        ) : null}

        <Timeline
          state={state}
          status={status}
          errorDetail={errorDetail}
          partial={partial}
          currentUserId={currentUserId}
          deciding={deciding}
          decisionFailure={decisionFailure}
          suggestions={suggestions}
          onRetry={() => {
            if (threadId) void controller.openThread(threadId);
            else void controller.refreshThreads();
          }}
          onSuggestion={onSuggestion}
          onAnswerSlot={onAnswerSlot}
          onDecide={onDecide}
        />

        {/* Inside the dialog, so it survives the modal's inert outside. */}
        <p role="status" aria-live="polite" className="sr-only">
          {pending ? (blocked ?? "") : ""}
        </p>

        <Composer
          ref={composerRef}
          value={text}
          mode={mode}
          busy={busy}
          blocked={!!pending}
          exhausted={exhausted}
          onChange={setText}
          onSend={onSend}
          onStop={() => void controller.stop()}
          onMode={onModeChange}
        />

        <footer className="min-w-0 border-t border-border px-4 py-2">
          <Meters cost={state.cost} context={state.context} budget={state.budget} />
        </footer>
      </SheetContent>
    </Sheet>
  );
}

/**
 * The width grabber. `separator` with a value, focusable, arrow keys —
 * WCAG 2.2 2.5.7 (a drag-only control fails) and 2.5.8 (24 px target).
 *
 * Hidden below the `md` breakpoint: there the drawer is full screen, so
 * there is nothing to resize and a dead touch target is worse than none.
 */
function ResizeHandle({ width, onWidth }: { width: number; onWidth: (px: number) => void }) {
  const t = useT();
  const draggingRef = React.useRef(false);

  React.useEffect(() => {
    function onMove(e: PointerEvent) {
      if (!draggingRef.current) return;
      // The drawer is anchored right: width grows as the pointer moves left.
      onWidth(window.innerWidth - e.clientX);
    }
    function onUp() {
      draggingRef.current = false;
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [onWidth]);

  return (
    <div
      role="separator"
      tabIndex={0}
      aria-orientation="vertical"
      aria-label={t("companion.resize")}
      aria-valuenow={width}
      aria-valuemin={MIN_WIDTH}
      aria-valuemax={MAX_WIDTH}
      title={t("companion.resize.hint")}
      onPointerDown={(e) => {
        draggingRef.current = true;
        e.currentTarget.setPointerCapture?.(e.pointerId);
      }}
      onKeyDown={(e) => {
        const step = e.shiftKey ? WIDTH_STEP_LARGE : WIDTH_STEP;
        if (e.key === "ArrowLeft") {
          e.preventDefault();
          onWidth(width + step);
        } else if (e.key === "ArrowRight") {
          e.preventDefault();
          onWidth(width - step);
        } else if (e.key === "Home") {
          e.preventDefault();
          onWidth(MAX_WIDTH);
        } else if (e.key === "End") {
          e.preventDefault();
          onWidth(MIN_WIDTH);
        }
      }}
      className="absolute inset-y-0 left-0 hidden w-6 cursor-col-resize touch-none items-center justify-center focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none md:flex"
    >
      <span aria-hidden="true" className="h-8 w-px rounded-full bg-border" />
    </div>
  );
}

export { URL_PARAM };
