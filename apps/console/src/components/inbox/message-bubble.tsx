import { AlertTriangle, FileText, ImageIcon, Mic, Video } from "lucide-react";
import * as React from "react";

import { cn } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import type { InboxThreadItem } from "@/lib/backend/inbox";
import { inboxMediaUrl } from "@/lib/inbox-urls";

import { clock } from "./inbox-model";

/**
 * One message of the thread (spec 030, R8). The contact on the left; the
 * agent, a person of the business and the Auphere team on the right, each
 * in its own tone so a glance says who wrote. An outbound says whether it
 * arrived; a failed one says why (R8.4).
 */
export function MessageBubble({ item, contactInitials }: { item: InboxThreadItem; contactInitials: string }) {
  const t = useT();
  const locale = useLocale();
  const time = clock(item.at, locale);
  const inbound = item.direction === "inbound";
  const author = item.author;

  if (inbound) {
    return (
      <div className="flex max-w-[72%] items-end gap-2 self-start">
        <span
          aria-hidden="true"
          className="mb-5 grid size-7 shrink-0 place-items-center rounded-full bg-accent-soft text-xs font-semibold text-accent-deep"
        >
          {contactInitials}
        </span>
        <div className="flex min-w-0 flex-col items-start gap-1">
          <MediaPreview item={item} tone="light" />
          {item.text ? <Text tone="contact">{item.text}</Text> : null}
          <span className="text-xs text-muted-foreground">{time}</span>
        </div>
      </div>
    );
  }

  const who =
    author?.kind === "member"
      ? author.is_me
        ? t("inbox.who.you")
        : (author.name ?? t("inbox.who.someone"))
      : author?.kind === "operator"
        ? t("inbox.who.operator")
        : t("inbox.who.agent");
  const tone = author?.kind === "agent" || !author ? "agent" : "person";
  const failed = item.delivery === "failed";

  return (
    <div className="flex max-w-[72%] min-w-0 flex-col items-end gap-1 self-end">
      <MediaPreview item={item} tone={tone === "agent" ? "light" : "dark"} />
      {item.text ? <Text tone={tone}>{item.text}</Text> : null}
      <span className="flex flex-wrap items-center justify-end gap-1 text-xs text-muted-foreground">
        <span>
          {who} · {time}
        </span>
        {item.delivery && !failed ? <span>· {deliveryText(item.delivery, t)}</span> : null}
      </span>
      {failed ? (
        <span role="status" className="flex items-center gap-1 text-xs text-status-danger-text">
          <AlertTriangle className="size-3" aria-hidden="true" />
          {item.failure_reason
            ? t("inbox.delivery.failed.reason", { reason: item.failure_reason })
            : t("inbox.delivery.failed")}
        </span>
      ) : null}
    </div>
  );
}

function deliveryText(d: NonNullable<InboxThreadItem["delivery"]>, t: ReturnType<typeof useT>): string {
  switch (d) {
    case "pending":
      return t("inbox.delivery.pending");
    case "sent":
      return t("inbox.delivery.sent");
    case "delivered":
      return t("inbox.delivery.delivered");
    case "read":
      return t("inbox.delivery.read");
    default:
      return t("inbox.delivery.failed");
  }
}

function Text({ tone, children }: { tone: "contact" | "agent" | "person"; children: string }) {
  return (
    <p
      className={cn(
        "max-w-full rounded-md px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap text-pretty [overflow-wrap:anywhere]",
        tone === "contact" && "bg-muted text-foreground",
        // Primary at 15 % — not `accent-soft`: that pistachio does not follow
        // the theme, and under dark `text-foreground` it read light on light.
        tone === "agent" && "bg-primary/15 text-foreground",
        tone === "person" && "bg-bg-inverse text-fg-on-dark",
      )}
    >
      {children}
    </p>
  );
}

/**
 * A received or sent file. The bytes come through the BFF
 * (`/api/lite/inbox/media/{id}`), never from a storage link. Images keep a
 * fixed box so the thread does not jump while they load (CLS).
 */
export function MediaPreview({ item, tone }: { item: InboxThreadItem; tone: "light" | "dark" }) {
  const t = useT();
  const media = item.media;
  // An image that does not load (expired, removed) falls back to the file
  // link below — never the browser's broken-image icon.
  const [broken, setBroken] = React.useState(false);
  if (!media?.kind) return null;
  const src = inboxMediaUrl(item.id);
  const box = cn(
    "flex max-w-full items-center gap-2 rounded-md px-3 py-2 text-sm",
    tone === "dark" ? "bg-bg-inverse text-fg-on-dark" : "bg-muted text-foreground",
  );
  if ((media.kind === "image" || media.kind === "sticker") && !broken) {
    const alt = media.filename ?? t("inbox.media.image");
    return (
      <a href={src} target="_blank" rel="noreferrer" className="block max-w-full overflow-hidden rounded-md bg-muted">
        {/* eslint-disable-next-line @next/next/no-img-element -- the bytes come from our own BFF route, not a static asset */}
        <img
          src={src}
          alt={alt}
          width={220}
          height={148}
          loading="lazy"
          onError={() => setBroken(true)}
          className="block h-auto w-56 max-w-full object-cover"
        />
      </a>
    );
  }
  if (media.kind === "audio") {
    return (
      <div className="flex max-w-full flex-col gap-1">
        <span className={box}>
          <Mic className="size-4 shrink-0" aria-hidden="true" />
          <audio controls preload="none" src={src} className="h-8 w-56 max-w-full min-w-0">
            {t("inbox.media.audio")}
          </audio>
        </span>
        {media.transcript ? (
          <span className="max-w-xs text-xs text-muted-foreground italic text-pretty">
            {t("inbox.media.transcript", { text: media.transcript })}
          </span>
        ) : null}
      </div>
    );
  }
  const name =
    media.filename ??
    (media.kind === "video"
      ? t("inbox.media.video")
      : media.kind === "image" || media.kind === "sticker"
        ? t("inbox.media.image")
        : t("inbox.media.document"));
  const Icon = media.kind === "video" ? Video : media.kind === "image" || media.kind === "sticker" ? ImageIcon : FileText;
  return (
    <a href={src} target="_blank" rel="noreferrer" className={cn(box, "underline-offset-4 hover:underline")} aria-label={t("inbox.media.open", { name })}>
      <Icon className="size-4 shrink-0" aria-hidden="true" />
      <span className="min-w-0 truncate">{name}</span>
    </a>
  );
}
