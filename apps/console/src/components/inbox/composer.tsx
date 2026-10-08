import { AlertTriangle, Bot, Paperclip, Send } from "lucide-react";
import * as React from "react";

import { Button } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { SavedReply } from "@/lib/backend/inbox";

import { ATTACH_ACCEPT, checkAttachment, type ComposerMode, type SendError } from "./inbox-model";
import { SavedReplies, type RepliesApi } from "./saved-replies";

/**
 * The bottom of an open conversation (spec 030, R9–R11). What it offers
 * depends on who answers — never a text box that cannot send:
 *
 * - **resolved**: says so, and «Reabrir»;
 * - **waiting**: the agent asked for help — why, and «Tomar el control»;
 * - **agent**: the agent answers — «Tomar el control»;
 * - **other**: another person answers — who, and «Tomar el control»;
 * - **mine**: the box. Enter sends, Shift+Enter adds a line. If WhatsApp
 *   would refuse (24 h window closed, number disconnected) the box says why
 *   instead of letting the person type into a wall.
 */
export function Composer({
  mode,
  busy,
  sendError,
  replies,
  repliesApi,
  attaching,
  onTakeOver,
  onGiveBack,
  onReopen,
  onSend,
  onAttach,
}: {
  mode: ComposerMode;
  busy: boolean;
  sendError: SendError | "generic" | null;
  replies: SavedReply[] | null;
  repliesApi: RepliesApi;
  attaching: string | null;
  onTakeOver: () => void;
  onGiveBack: () => void;
  onReopen: () => void;
  onSend: (text: string) => Promise<boolean>;
  onAttach: (file: File) => void;
}) {
  const t = useT();
  const [draft, setDraft] = React.useState("");
  const [fileError, setFileError] = React.useState<string | null>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);
  const boxRef = React.useRef<HTMLTextAreaElement>(null);

  if (mode.kind === "resolved") {
    return (
      <Shell>
        <div className="flex flex-wrap items-center gap-3 rounded-md p-3 ring-1 ring-border ring-inset">
          <p className="min-w-48 flex-1 text-sm text-muted-foreground text-pretty">{t("inbox.composer.resolved")}</p>
          <Button type="button" variant="outline" disabled={busy} onClick={onReopen}>
            {t("inbox.action.reopen")}
          </Button>
        </div>
      </Shell>
    );
  }

  if (mode.kind === "waiting") {
    return (
      <Shell>
        <div className="flex flex-wrap items-center gap-3 rounded-md bg-status-warning-bg p-3 ring-1 ring-status-warning-border ring-inset">
          <div className="flex min-w-48 flex-1 flex-col">
            <p className="text-sm font-semibold text-balance">{t("inbox.composer.waiting.title")}</p>
            <p className="text-sm text-muted-foreground text-pretty">{mode.reason ?? t("inbox.composer.waiting.noReason")}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" disabled={busy} onClick={onGiveBack}>
              {t("inbox.composer.giveBack")}
            </Button>
            <Button type="button" disabled={busy} onClick={onTakeOver}>
              {t("inbox.composer.takeover")}
            </Button>
          </div>
        </div>
      </Shell>
    );
  }

  if (mode.kind === "agent" || mode.kind === "other") {
    return (
      <Shell>
        <div className="flex flex-wrap items-center gap-3 rounded-md p-3 ring-1 ring-border ring-inset">
          <Bot className="size-5 shrink-0 text-primary-text" aria-hidden="true" />
          <p className="min-w-48 flex-1 text-sm text-muted-foreground text-pretty">
            {mode.kind === "agent"
              ? t("inbox.composer.agent")
              : t("inbox.composer.other", { name: mode.name ?? t("inbox.who.someone") })}
          </p>
          <Button type="button" variant="outline" disabled={busy} onClick={onTakeOver}>
            {t("inbox.composer.takeover")}
          </Button>
        </div>
      </Shell>
    );
  }

  const blocked = mode.blocked;
  const canSend = !blocked && !busy && draft.trim().length > 0;
  const send = async () => {
    if (!canSend) return;
    const text = draft;
    setDraft("");
    const ok = await onSend(text);
    if (!ok) setDraft((d) => d || text);
    boxRef.current?.focus();
  };
  const errorKey = sendError ?? null;

  return (
    <Shell>
      {blocked ? (
        <p role="status" className="mb-2 flex items-start gap-2 rounded-md bg-status-warning-bg p-3 text-sm text-status-warning-text ring-1 ring-status-warning-border ring-inset">
          <AlertTriangle className="mt-px size-4 shrink-0" aria-hidden="true" />
          <span className="text-pretty">{t(`inbox.composer.${blocked}`)}</span>
        </p>
      ) : null}
      <div className="relative flex flex-col gap-2 rounded-md border border-border bg-card p-3 focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ring">
        <label className="sr-only" htmlFor="inbox-composer">
          {t("inbox.composer")}
        </label>
        <textarea
          id="inbox-composer"
          ref={boxRef}
          value={draft}
          rows={2}
          maxLength={4096}
          disabled={Boolean(blocked)}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              void send();
            }
          }}
          placeholder={t("inbox.composer.placeholder")}
          aria-describedby="inbox-composer-hint"
          className="min-h-12 w-full resize-none border-0 bg-transparent text-sm leading-relaxed outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed"
        />
        <div className="flex flex-wrap items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={t("inbox.composer.attach")}
            title={t("inbox.composer.attach")}
            disabled={Boolean(blocked) || busy || attaching !== null}
            onClick={() => fileRef.current?.click()}
          >
            <Paperclip />
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept={ATTACH_ACCEPT}
            className="hidden"
            data-testid="inbox-file"
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (!file) return;
              const check = checkAttachment(file);
              if (!check.ok) {
                setFileError(
                  check.reason === "type"
                    ? t("inbox.composer.attach.type")
                    : t("inbox.composer.attach.size", { mb: check.maxMb }),
                );
                return;
              }
              setFileError(null);
              onAttach(file);
            }}
          />
          <SavedReplies
            replies={replies}
            api={repliesApi}
            disabled={Boolean(blocked)}
            onPick={(body) => {
              setDraft((d) => (d.trim() ? `${d.trimEnd()}\n${body}` : body));
              boxRef.current?.focus();
            }}
          />
          <span id="inbox-composer-hint" className="hidden px-2 text-xs text-muted-foreground lg:inline">
            {t("inbox.composer.hint")}
          </span>
          <span className="flex-1" />
          <Button type="button" variant="outline" size="sm" disabled={busy} onClick={onGiveBack}>
            {t("inbox.composer.giveBack")}
          </Button>
          <Button type="button" size="sm" disabled={!canSend} onClick={() => void send()}>
            {t("inbox.composer.send")}
            <Send data-icon="inline-end" />
          </Button>
        </div>
      </div>
      {attaching ? (
        <p role="status" className="mt-2 text-xs text-muted-foreground">
          {t("inbox.composer.attach.sending", { name: attaching })}
        </p>
      ) : null}
      {fileError ? (
        <p role="alert" className="mt-2 text-xs text-status-danger-text">
          {fileError}
        </p>
      ) : null}
      {errorKey ? (
        <p role="alert" className="mt-2 text-xs text-status-danger-text">
          {errorKey === "generic" ? t("inbox.error.action") : t(`inbox.composer.${errorKey}`)}
        </p>
      ) : null}
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return <div className="px-4 pb-4">{children}</div>;
}
