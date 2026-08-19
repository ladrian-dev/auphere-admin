"use client";

import { Clock, ShieldAlert, ShieldCheck } from "lucide-react";
import * as React from "react";

import { Alert, AlertDescription, AlertTitle, Badge, Button, Textarea } from "@nexus/ui";

import { useT } from "@/i18n/client";

import { optionalKey } from "./i18n";
import type { ActionItem } from "./state";
import type { Decision, DiffLine, ImpactItem } from "./types";

/**
 * The confirmation card (§2.3 / §2.4 of the contract) — the one thing in
 * the drawer that demands attention rather than reporting.
 *
 * Rules that are not style choices:
 *
 * - **`expires_at` is the only source of the countdown.** The UI does not
 *   count 15 minutes on its own; if the backend changes the window, the UI
 *   follows. Once past, the buttons go away: offering a decision that can
 *   no longer be taken is a lie.
 * - **Three outcomes, not two.** `edit` and `cancel` both carry a `note`
 *   back to the model, so a refusal adjusts the plan instead of ending the
 *   conversation. That is what `deny_message` buys, implemented as a field.
 * - **409 and 412 are different sentences.** "You ran out of time" and
 *   "someone changed this while you were deciding" have the same way out
 *   (propose again) but a person needs to know which happened.
 * - `by` is a `principal_id`, never an email: §14 forbids full third-party
 *   addresses in the chat.
 */
type Props = {
  item: ActionItem;
  currentUserId: string | null;
  busy: boolean;
  failure: { status: number; code: string | null } | null;
  onDecide: (decision: Decision, note?: string) => void;
};

function remaining(expiresAt: string | null, now: number): number | null {
  if (!expiresAt) return null;
  const ms = Date.parse(expiresAt);
  if (!Number.isFinite(ms)) return null;
  return Math.max(0, Math.floor((ms - now) / 1000));
}

function mmss(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function ConfirmCard({ item, currentUserId, busy, failure, onDecide }: Props) {
  const t = useT();
  const [now, setNow] = React.useState(() => Date.now());
  const [editing, setEditing] = React.useState(false);
  const [note, setNote] = React.useState("");
  const noteRef = React.useRef<HTMLTextAreaElement | null>(null);

  const pending = item.state === "pending";
  React.useEffect(() => {
    if (!pending || !item.expiresAt) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [pending, item.expiresAt]);

  React.useEffect(() => {
    if (editing) noteRef.current?.focus();
  }, [editing]);

  const left = remaining(item.expiresAt, now);
  const expired = left !== null && left === 0;
  const kindKey = optionalKey(`companion.kind.${item.actionKind}`);
  const kindLabel = kindKey ? t(kindKey) : t("companion.kind.unknown");

  return (
    <section
      aria-label={t("companion.confirm.title")}
      className={`min-w-0 rounded-sm border-2 p-3 ${
        pending && !expired ? "border-primary bg-card" : "border-border bg-card"
      }`}
    >
      <div className="flex min-w-0 items-center gap-2">
        {pending && !expired ? (
          <ShieldAlert aria-hidden="true" className="size-4 shrink-0 text-primary" />
        ) : (
          <ShieldCheck aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
        )}
        <h3 className="min-w-0 flex-1 text-sm font-medium text-pretty">{item.title}</h3>
        <Badge variant="outline" className="shrink-0">
          {kindLabel}
        </Badge>
      </div>

      {item.preview && Object.keys(item.preview).length > 0 ? <Preview preview={item.preview} /> : null}
      {item.diff && item.diff.length > 0 ? <Diff lines={item.diff} /> : null}
      {item.impact.length > 0 ? <Impact items={item.impact} /> : null}

      {/* ── resolved: the card is sealed, never duplicated ─────────── */}
      {item.state === "resolved" ? (
        <ResolvedFooter item={item} currentUserId={currentUserId} />
      ) : expired ? (
        <Alert className="mt-3">
          <AlertTitle>{t("companion.confirm.expired.title")}</AlertTitle>
          <AlertDescription>{t("companion.confirm.expired.body")}</AlertDescription>
        </Alert>
      ) : (
        <div className="mt-3 min-w-0 space-y-2 border-t border-border pt-3">
          {failure ? <Failure failure={failure} /> : null}

          {left !== null ? (
            <p className="flex items-center gap-1 text-xs text-muted-foreground">
              <Clock aria-hidden="true" className="size-3 shrink-0" />
              <span aria-live="off">{t("companion.confirm.expires", { time: mmss(left) })}</span>
            </p>
          ) : null}

          {editing ? (
            <div className="min-w-0 space-y-2">
              <label htmlFor={`note-${item.id}`} className="text-xs font-medium">
                {t("companion.confirm.note.label")}
              </label>
              <Textarea
                id={`note-${item.id}`}
                ref={noteRef}
                rows={2}
                maxLength={2000}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder={t("companion.confirm.note.placeholder")}
                className="text-sm"
              />
              <p className="text-xs text-pretty text-muted-foreground">{t("companion.confirm.note.hint")}</p>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" disabled={busy} onClick={() => onDecide("edit", note.trim() || undefined)}>
                  {t("companion.confirm.note.send")}
                </Button>
                <Button size="sm" variant="ghost" disabled={busy} onClick={() => setEditing(false)}>
                  {t("companion.confirm.cancel")}
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex min-w-0 flex-wrap gap-2">
              <Button size="sm" disabled={busy} onClick={() => onDecide("confirm")}>
                {t("companion.confirm.confirm")}
              </Button>
              <Button size="sm" variant="outline" disabled={busy} onClick={() => setEditing(true)}>
                {t("companion.confirm.edit")}
              </Button>
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => onDecide("cancel")}>
                {t("companion.confirm.cancel")}
              </Button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function Failure({ failure }: { failure: { status: number; code: string | null } }) {
  const t = useT();
  // 412 is state drift ONLY; time expiry is 409 `action_expired`. Same way
  // out, different sentence — §4.2.
  const stale = failure.status === 412 || failure.code === "state_changed";
  const expired = failure.code === "action_expired";
  const decided = failure.code === "action_already_decided";
  return (
    <Alert>
      <AlertTitle>
        {stale
          ? t("companion.confirm.stale.title")
          : expired
            ? t("companion.confirm.expired.title")
            : t("companion.confirm.failed")}
      </AlertTitle>
      <AlertDescription>
        {stale
          ? t("companion.confirm.stale.body")
          : expired
            ? t("companion.confirm.expired.body")
            : decided
              ? t("companion.confirm.decided")
              : t("companion.confirm.failed")}
      </AlertDescription>
    </Alert>
  );
}

function ResolvedFooter({ item, currentUserId }: { item: ActionItem; currentUserId: string | null }) {
  const t = useT();
  const decision: Decision = item.decision ?? "confirm";
  const by = item.by === currentUserId ? t("companion.confirm.resolved.you") : (item.by ?? "—");
  return (
    <div className="mt-3 min-w-0 border-t border-border pt-2">
      <p className="text-xs text-muted-foreground">{t(`companion.confirm.resolved.${decision}` as const, { by })}</p>
      {item.note ? <p className="mt-1 text-xs text-pretty text-foreground">“{item.note}”</p> : null}
    </div>
  );
}

/**
 * `preview` is a free object by design (§3.4). Known keys get a proper
 * label; **an unknown `kind` falls back to a generic key/value view** —
 * that fallback is what lets CO-04 add a kind without breaking this app.
 */
function Preview({ preview }: { preview: Record<string, unknown> }) {
  const t = useT();
  const entries = Object.entries(preview).filter(([, v]) => v !== null && v !== undefined && v !== "");
  if (entries.length === 0) return null;
  return (
    <dl className="mt-2 grid min-w-0 grid-cols-[minmax(0,auto)_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
      {entries.map(([key, value]) => {
        const labelKey = optionalKey(`companion.preview.${key}`);
        return (
          <React.Fragment key={key}>
            <dt className="min-w-0 truncate text-muted-foreground">{labelKey ? t(labelKey) : key}</dt>
            <dd className="min-w-0 text-pretty break-words text-foreground">{renderValue(value, t)}</dd>
          </React.Fragment>
        );
      })}
    </dl>
  );
}

function renderValue(value: unknown, t: ReturnType<typeof useT>): string {
  if (typeof value === "boolean") return value ? t("companion.preview.yes") : t("companion.preview.no");
  if (typeof value === "string" || typeof value === "number") return String(value);
  return JSON.stringify(value);
}

function Diff({ lines }: { lines: DiffLine[] }) {
  const t = useT();
  return (
    <div className="mt-3 min-w-0">
      <p className="text-xs font-medium text-muted-foreground">{t("companion.confirm.diff")}</p>
      <ul className="mt-1 min-w-0 overflow-x-auto rounded-sm bg-muted p-2 font-mono text-xs">
        {lines.map((line, i) => {
          const text = line.op === "del" ? (line.before ?? "") : (line.after ?? line.before ?? "");
          return (
            <li key={`${line.op}-${line.line}-${i}`} className="flex min-w-0 gap-2 whitespace-pre-wrap">
              <span className="shrink-0 tabular-nums text-muted-foreground/60">{line.line}</span>
              <span
                aria-hidden="true"
                className={`shrink-0 ${line.op === "add" ? "text-status-positive" : line.op === "del" ? "text-status-danger" : "text-muted-foreground/60"}`}
              >
                {line.op === "add" ? "+" : line.op === "del" ? "−" : " "}
              </span>
              {/* The +/− glyph carries meaning; screen readers get words. */}
              {line.op !== "ctx" ? (
                <span className="sr-only">
                  {line.op === "add" ? t("companion.confirm.diff.add") : t("companion.confirm.diff.del")}
                </span>
              ) : null}
              <span className={`min-w-0 ${line.op === "ctx" ? "text-muted-foreground" : "text-foreground"}`}>{text}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

const SEVERITY_TONE: Record<ImpactItem["severity"], string> = {
  info: "text-muted-foreground",
  warn: "text-status-warning",
  danger: "text-status-danger",
};

function Impact({ items }: { items: ImpactItem[] }) {
  const t = useT();
  return (
    <div className="mt-3 min-w-0">
      <p className="text-xs font-medium text-muted-foreground">{t("companion.confirm.impact")}</p>
      <ul className="mt-1 min-w-0 space-y-1">
        {items.map((i) => {
          const labelKey = optionalKey(`companion.impact.${i.key}`);
          return (
            <li key={i.key} className="flex min-w-0 items-baseline justify-between gap-3 text-xs">
              <span className="min-w-0 truncate text-muted-foreground">{labelKey ? t(labelKey) : i.key}</span>
              <span className={`shrink-0 font-mono tabular-nums ${SEVERITY_TONE[i.severity]}`}>{i.value}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
