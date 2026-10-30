"use client";

import * as React from "react";

import { cn } from "@nexus/ui";

import { inboxAvatarUrl } from "@/lib/inbox-urls";

/**
 * Who wrote, as a circle: their Instagram / Messenger picture when Auphere
 * stored one (owner, 2026-10-30), else their initials — also when the picture
 * fails to load. Decorative: the name is always written next to it.
 */
export function ContactAvatar({
  conversationId,
  hasAvatar,
  initials,
  className,
}: {
  conversationId: string;
  hasAvatar?: boolean;
  initials: string;
  className: string;
}) {
  const [broken, setBroken] = React.useState(false);
  if (hasAvatar && !broken) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- the bytes come from our own BFF route, not a static asset
      <img
        src={inboxAvatarUrl(conversationId)}
        alt=""
        aria-hidden="true"
        loading="lazy"
        onError={() => setBroken(true)}
        className={cn("shrink-0 rounded-full bg-accent-soft object-cover", className)}
      />
    );
  }
  return (
    <span aria-hidden="true" className={cn("grid shrink-0 place-items-center rounded-full bg-accent-soft font-semibold text-accent-deep", className)}>
      {initials}
    </span>
  );
}
