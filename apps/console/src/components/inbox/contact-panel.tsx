import { Bot, X } from "lucide-react";
import * as React from "react";

import { Button, Textarea, cn } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import type { InboxActivity, InboxDetail } from "@/lib/backend/inbox";

import { eventText } from "./event-text";
import { clock, dayLabel } from "./inbox-model";

/**
 * The contact panel (spec 030, R13): what the agent understood, who the
 * contact is, what happened, the business's tags and its internal note.
 * Each block is absent when its data is: no escalation, no summary section
 * — never an empty heading over nothing.
 */
export function ContactPanel({
  detail,
  initials,
  suggested,
  now,
  onClose,
  onTags,
  onNote,
}: {
  detail: InboxDetail;
  initials: string;
  suggested: string[];
  now: Date;
  onClose: () => void;
  onTags: (tags: string[]) => Promise<boolean>;
  onNote: (body: string) => Promise<boolean>;
}) {
  const t = useT();
  const locale = useLocale();
  const first = detail.contact.first_message_at;
  const firstText = first
    ? (() => {
        const d = dayLabel(first, now, locale);
        return d.kind === "today" ? t("inbox.time.today") : d.kind === "yesterday" ? t("inbox.time.yesterday") : d.text;
      })()
    : "—";
  const attends =
    detail.state === "agent" || (!detail.assignee && detail.state !== "waiting")
      ? t("inbox.who.agent")
      : detail.assignee
        ? detail.assignee.is_me
          ? t("inbox.who.you")
          : (detail.assignee.name ?? t("inbox.who.someone"))
        : t("inbox.assigned.nobody");

  return (
    <aside aria-label={t("inbox.panel")} className="flex min-h-0 w-full flex-col overflow-y-auto bg-card">
      <div className="flex items-center gap-3 border-b border-border p-4">
        <span aria-hidden="true" className="grid size-12 shrink-0 place-items-center rounded-full bg-accent-soft text-base font-semibold text-accent-deep">
          {initials}
        </span>
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-base font-semibold" title={detail.contact.name}>
            {detail.contact.name}
          </span>
          <span className="truncate text-sm font-medium text-primary-text">{detail.contact.handle}</span>
        </div>
        <Button type="button" variant="ghost" size="icon-sm" aria-label={t("inbox.action.panel.hide")} title={t("inbox.action.panel.hide")} onClick={onClose}>
          <X />
        </Button>
      </div>

      {detail.summary ? (
        <Block>
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <Bot className="size-4 text-primary-text" aria-hidden="true" />
            {t("inbox.panel.summary")}
          </h3>
          <p className="text-sm leading-relaxed text-muted-foreground text-pretty">{detail.summary}</p>
        </Block>
      ) : null}

      <Block>
        <h3 className="text-sm font-semibold">{t("inbox.panel.data")}</h3>
        <dl className="grid grid-cols-[minmax(0,7rem)_minmax(0,1fr)] gap-x-3 gap-y-2 text-sm">
          <dt className="text-muted-foreground">{t("inbox.panel.attends")}</dt>
          <dd className="min-w-0 truncate">{attends}</dd>
          <dt className="text-muted-foreground">{t("inbox.panel.channel")}</dt>
          <dd>{t("inbox.channel.whatsapp")}</dd>
          <dt className="text-muted-foreground">{t("inbox.panel.phone")}</dt>
          <dd className="[overflow-wrap:anywhere]">{detail.contact.handle}</dd>
          <dt className="text-muted-foreground">{t("inbox.panel.first")}</dt>
          <dd>{firstText}</dd>
          <dt className="text-muted-foreground">{t("inbox.panel.conversations")}</dt>
          <dd className="tabular-nums">{detail.contact.conversations}</dd>
        </dl>
      </Block>

      <Block>
        <h3 className="text-sm font-semibold">{t("inbox.panel.activity")}</h3>
        <ActivityList items={detail.activity} now={now} />
      </Block>

      <Block>
        <h3 className="text-sm font-semibold">{t("inbox.panel.tags")}</h3>
        <TagEditor key={detail.id} tags={detail.tags} suggested={suggested} onChange={onTags} />
      </Block>

      <Block last>
        <h3 className="text-sm font-semibold">
          <label htmlFor="inbox-note">{t("inbox.panel.note")}</label>
        </h3>
        <InternalNote key={detail.id} initial={detail.note.body} onSave={onNote} />
      </Block>
    </aside>
  );
}

function Block({ children, last }: { children: React.ReactNode; last?: boolean }) {
  return <section className={cn("flex flex-col gap-2 p-4", !last && "border-b border-border")}>{children}</section>;
}

export function ActivityList({ items, now }: { items: InboxActivity[]; now: Date }) {
  const t = useT();
  const locale = useLocale();
  if (items.length === 0) return <p className="text-sm text-muted-foreground">{t("inbox.panel.activity.empty")}</p>;
  const text = (a: InboxActivity) => eventText(a.kind, a.actor, a.detail, t);
  return (
    <ol className="flex flex-col">
      {items.map((a, i) => {
        const d = dayLabel(a.at, now, locale);
        const day = d.kind === "today" ? t("inbox.time.today") : d.kind === "yesterday" ? t("inbox.time.yesterday") : d.text;
        return (
          <li key={`${a.kind}-${a.at}-${i}`} className="flex gap-3">
            <span className="flex w-2 shrink-0 flex-col items-center" aria-hidden="true">
              <span className={cn("mt-2 size-2 rounded-full", a.kind === "escalated" ? "bg-status-warning" : "bg-primary")} />
              <span className="mt-1 w-px flex-1 bg-border" />
            </span>
            <span className="flex min-w-0 flex-col pb-3">
              <span className="text-sm text-pretty">{text(a)}</span>
              <span className="text-xs text-muted-foreground">
                {day} · {clock(a.at, locale)}
              </span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/** Tags of the conversation: clean on the way in, ≤ 20 (R13.4). */
export function TagEditor({
  tags,
  suggested,
  onChange,
}: {
  tags: string[];
  suggested: string[];
  onChange: (tags: string[]) => Promise<boolean>;
}) {
  const t = useT();
  const [current, setCurrent] = React.useState(tags);
  const [draft, setDraft] = React.useState("");
  const lower = new Set(current.map((x) => x.toLowerCase()));
  const offer = suggested.filter((s) => !lower.has(s.toLowerCase())).slice(0, 8);
  const full = current.length >= 20;

  async function commit(next: string[]) {
    const before = current;
    setCurrent(next);
    if (!(await onChange(next))) setCurrent(before);
  }
  function add(raw: string) {
    const clean = raw.split(/\s+/).join(" ").trim().slice(0, 40);
    if (!clean || lower.has(clean.toLowerCase()) || full) return;
    void commit([...current, clean]);
  }

  return (
    <div className="flex flex-col gap-2">
      {current.length > 0 ? (
        <ul className="flex flex-wrap gap-1">
          {current.map((tag) => (
            <li
              key={tag}
              className="flex h-6 items-center gap-1 rounded-full bg-accent-soft pr-1 pl-2 text-xs font-medium text-accent-deep ring-1 ring-primary/30 ring-inset"
            >
              <span className="max-w-40 truncate" title={tag}>
                {tag}
              </span>
              <button
                type="button"
                aria-label={t("inbox.panel.tags.remove", { tag })}
                onClick={() => void commit(current.filter((x) => x !== tag))}
                className="grid size-6 place-items-center rounded-full hover:bg-primary/15 focus-visible:outline-2 focus-visible:outline-ring"
              >
                <X className="size-3" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <input
        value={draft}
        maxLength={40}
        disabled={full}
        aria-label={t("inbox.panel.tags.add")}
        placeholder={t("inbox.panel.tags.add")}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            add(draft);
            setDraft("");
          }
        }}
        className="h-8 rounded-sm border border-border-strong bg-card px-3 text-sm outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-50"
      />
      {full ? <p className="text-xs text-muted-foreground">{t("inbox.panel.tags.max")}</p> : null}
      {offer.length > 0 && !full ? (
        <>
          <span className="text-xs text-muted-foreground">{t("inbox.panel.tags.suggested")}</span>
          <div className="flex flex-wrap gap-1">
            {offer.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => add(s)}
                className="h-6 rounded-full border border-dashed border-border-strong bg-card px-2 text-xs font-medium text-muted-foreground hover:border-solid hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring"
              >
                + {s}
              </button>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}

/** The internal note of the contact: only the team sees it (R13.5). */
export function InternalNote({ initial, onSave }: { initial: string; onSave: (body: string) => Promise<boolean> }) {
  const t = useT();
  const [body, setBody] = React.useState(initial);
  const [saved, setSaved] = React.useState(initial);
  const [status, setStatus] = React.useState<"idle" | "saving" | "saved" | "error">("idle");
  const dirty = body !== saved;

  async function save() {
    if (!dirty) return;
    setStatus("saving");
    const ok = await onSave(body);
    if (ok) setSaved(body);
    setStatus(ok ? "saved" : "error");
  }

  return (
    <div className="flex flex-col gap-2">
      <Textarea
        id="inbox-note"
        value={body}
        rows={4}
        maxLength={4000}
        placeholder={t("inbox.panel.note.placeholder")}
        onChange={(e) => {
          setBody(e.target.value);
          setStatus("idle");
        }}
        onBlur={() => void save()}
      />
      <div className="flex items-center justify-end gap-2">
        <span role="status" className={cn("text-xs", status === "error" ? "text-status-danger-text" : "text-muted-foreground")}>
          {status === "saving"
            ? t("inbox.panel.note.saving")
            : status === "saved"
              ? t("inbox.panel.note.saved")
              : status === "error"
                ? t("inbox.panel.note.error")
                : ""}
        </span>
        <Button type="button" size="sm" variant="outline" disabled={!dirty || status === "saving"} onClick={() => void save()}>
          {t("inbox.panel.note.save")}
        </Button>
      </div>
    </div>
  );
}
