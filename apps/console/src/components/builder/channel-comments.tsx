"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button, Field, Input } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { ChannelPage, InstagramComments } from "@/lib/backend/channel-config-types";

import type { Result } from "./builder-model";

export const PUBLIC_REPLY_MAX = 300;

/**
 * Spec 049 (historia 3): los comentarios de una cuenta de Instagram. Si el
 * agente los atiende, contesta a la persona en privado; la línea pública es
 * lo que se publica bajo el comentario a la vez (vacía, nada). Guarda al
 * pulsar, aparte de la barra del canal, como el catálogo.
 *
 * Quien solo lee lo ve como texto (§V).
 */
export function InstagramCommentsSection({
  comments,
  canWrite,
  onSave,
  onSaved,
}: {
  comments: InstagramComments;
  canWrite: boolean;
  onSave: (next: InstagramComments) => Promise<Result<ChannelPage>>;
  onSaved: (page: ChannelPage) => void;
}) {
  const t = useT();
  const [enabled, setEnabled] = React.useState(comments.enabled);
  const [reply, setReply] = React.useState(comments.public_reply ?? "");
  const [busy, setBusy] = React.useState(false);
  const dirty = enabled !== comments.enabled || reply.trim() !== (comments.public_reply ?? "");
  const tooLong = reply.trim().length > PUBLIC_REPLY_MAX;

  if (!canWrite) {
    return (
      <dl className="grid min-w-0 gap-2 text-sm" data-slot="instagram-comments">
        <div className="grid min-w-0 gap-1">
          <dt className="text-muted-foreground">{t("builder.channel.comments.answer")}</dt>
          <dd>{t(comments.enabled ? "builder.channel.comments.on" : "builder.channel.comments.off")}</dd>
        </div>
        <div className="grid min-w-0 gap-1">
          <dt className="text-muted-foreground">{t("builder.channel.comments.public")}</dt>
          <dd className="break-words">{comments.public_reply ?? t("builder.channel.comments.public.none")}</dd>
        </div>
      </dl>
    );
  }

  async function save() {
    setBusy(true);
    const res = await onSave({ enabled, public_reply: reply.trim() || null });
    setBusy(false);
    if (res.ok) {
      onSaved(res.data);
      toast.success(t("builder.channel.comments.saved"));
      return;
    }
    toast.error(t("builder.channel.error"));
  }

  return (
    <div className="grid min-w-0 gap-4" data-slot="instagram-comments">
      <label className="flex min-w-0 items-start gap-3 text-sm">
        <input
          type="checkbox"
          className="mt-1 size-4 shrink-0 accent-primary"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
        />
        <span className="grid min-w-0 gap-1">
          <span className="font-medium">{t("builder.channel.comments.answer")}</span>
          <span className="text-pretty text-muted-foreground">{t("builder.channel.comments.answer.hint")}</span>
        </span>
      </label>
      <Field
        label={t("builder.channel.comments.public")}
        hint={t("builder.channel.comments.public.hint")}
        error={tooLong ? t("builder.channel.comments.public.tooLong") : undefined}
      >
        {(a11y) => (
          <Input
            {...a11y}
            value={reply}
            disabled={!enabled}
            maxLength={PUBLIC_REPLY_MAX + 50}
            placeholder={t("builder.channel.comments.public.placeholder")}
            onChange={(e) => setReply(e.target.value)}
          />
        )}
      </Field>
      <Button type="button" className="w-fit" disabled={!dirty || tooLong} loading={busy} onClick={() => void save()}>
        {t("builder.channel.comments.save")}
      </Button>
    </div>
  );
}
