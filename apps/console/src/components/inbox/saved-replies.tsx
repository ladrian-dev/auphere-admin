import { MessageSquareText, Pencil, Plus, Trash2 } from "lucide-react";
import * as React from "react";

import { Button, Input, Textarea } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { SavedReply } from "@/lib/backend/inbox";

export type RepliesApi = {
  create: (r: { title: string; body: string }) => Promise<boolean>;
  edit: (id: string, r: { title: string; body: string }) => Promise<boolean>;
  archive: (id: string) => Promise<boolean>;
};

/**
 * Saved replies (spec 030, R10.4): the business's own canned answers.
 * Picking one puts its text in the box — it never sends by itself. Created,
 * edited and «deleted» (archived: constitution §IV) from the same panel.
 * Escape closes it and gives the focus back to its button.
 */
export function SavedReplies({
  replies,
  api,
  disabled,
  onPick,
}: {
  replies: SavedReply[] | null;
  api: RepliesApi;
  disabled: boolean;
  onPick: (body: string) => void;
}) {
  const t = useT();
  const [open, setOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<SavedReply | "new" | null>(null);
  const button = React.useRef<HTMLButtonElement>(null);
  const panel = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!panel.current?.contains(e.target as Node) && !button.current?.contains(e.target as Node)) close();
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  });

  function close() {
    setOpen(false);
    setEditing(null);
    button.current?.focus();
  }

  // No `relative` here on purpose: the panel anchors to the composer box,
  // so on a phone it spans the box instead of running off the screen.
  return (
    <div>
      <Button
        ref={button}
        type="button"
        variant="ghost"
        size="icon"
        aria-label={t("inbox.replies")}
        title={t("inbox.replies")}
        aria-expanded={open}
        aria-haspopup="dialog"
        disabled={disabled}
        onClick={() => (open ? close() : setOpen(true))}
      >
        <MessageSquareText />
      </Button>
      {open ? (
        <div
          ref={panel}
          role="dialog"
          aria-label={t("inbox.replies")}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.stopPropagation();
              close();
            }
          }}
          className="absolute right-0 bottom-full left-0 z-40 mb-2 flex max-h-96 flex-col overflow-y-auto rounded-md bg-popover p-1 text-popover-foreground shadow-md ring-1 ring-border sm:right-auto sm:w-80"
        >
          <p className="px-2 pt-2 pb-1 text-xs font-medium tracking-eyebrow text-muted-foreground uppercase">{t("inbox.replies")}</p>
          {editing ? (
            <ReplyForm
              initial={editing === "new" ? null : editing}
              onCancel={() => setEditing(null)}
              onSave={async (r) => {
                const ok = editing === "new" ? await api.create(r) : await api.edit(editing.id, r);
                if (ok) setEditing(null);
                return ok;
              }}
            />
          ) : (
            <>
              {replies && replies.length === 0 ? <p className="px-2 py-3 text-sm text-muted-foreground">{t("inbox.replies.empty")}</p> : null}
              <ul className="flex flex-col">
                {(replies ?? []).map((r) => (
                  <li key={r.id} className="group flex items-start gap-1 rounded-sm hover:bg-muted">
                    <button
                      type="button"
                      onClick={() => {
                        onPick(r.body);
                        close();
                      }}
                      className="flex min-w-0 flex-1 flex-col gap-1 rounded-sm px-2 py-2 text-left focus-visible:outline-2 focus-visible:outline-ring"
                    >
                      <span className="truncate text-sm font-medium" title={r.title}>
                        {r.title}
                      </span>
                      <span className="truncate text-xs text-muted-foreground" title={r.body}>
                        {r.body}
                      </span>
                    </button>
                    <Button type="button" variant="ghost" size="icon-sm" aria-label={t("inbox.replies.edit", { title: r.title })} onClick={() => setEditing(r)}>
                      <Pencil />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      aria-label={t("inbox.replies.archive", { title: r.title })}
                      onClick={() => void api.archive(r.id)}
                    >
                      <Trash2 />
                    </Button>
                  </li>
                ))}
              </ul>
              <Button type="button" variant="ghost" size="sm" className="justify-start" onClick={() => setEditing("new")}>
                <Plus data-icon="inline-start" />
                {t("inbox.replies.new")}
              </Button>
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}

function ReplyForm({
  initial,
  onCancel,
  onSave,
}: {
  initial: SavedReply | null;
  onCancel: () => void;
  onSave: (r: { title: string; body: string }) => Promise<boolean>;
}) {
  const t = useT();
  const [title, setTitle] = React.useState(initial?.title ?? "");
  const [body, setBody] = React.useState(initial?.body ?? "");
  const [saving, setSaving] = React.useState(false);
  const valid = title.trim().length > 0 && body.trim().length > 0;
  return (
    <form
      className="flex flex-col gap-2 p-2"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!valid) return;
        setSaving(true);
        await onSave({ title: title.trim(), body: body.trim() });
        setSaving(false);
      }}
    >
      <label className="flex flex-col gap-1 text-xs font-medium">
        {t("inbox.replies.titleField")}
        <Input value={title} maxLength={80} onChange={(e) => setTitle(e.target.value)} autoFocus />
      </label>
      <label className="flex flex-col gap-1 text-xs font-medium">
        {t("inbox.replies.bodyField")}
        <Textarea value={body} maxLength={1000} rows={4} onChange={(e) => setBody(e.target.value)} />
      </label>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          {t("inbox.replies.cancel")}
        </Button>
        <Button type="submit" size="sm" disabled={!valid || saving}>
          {t("inbox.replies.save")}
        </Button>
      </div>
    </form>
  );
}
