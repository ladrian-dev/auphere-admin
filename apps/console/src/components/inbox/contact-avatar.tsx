"use client";

import * as React from "react";

import { UserRound } from "lucide-react";

import { cn } from "@nexus/ui";

import { inboxAvatarUrl } from "@/lib/inbox-urls";

/**
 * Spec 082 (5.1, 5.2): six tones, one per contact. Every one is a pair of
 * `@nexus/ui` tokens (greens, the neutral and the information blue — never
 * amber or red, which mean a state) that reads at 4.5:1 or more in both
 * themes. `light` and `dark` are the Tailwind colour names of the background
 * and the text; the test measures them on `tokens.css` and checks that
 * `className` is exactly those classes.
 */
export const AVATAR_TONES = [
  { light: ["pistachio", "pine"], dark: ["pine", "pistachio"], className: "bg-pistachio text-pine dark:bg-pine dark:text-pistachio" },
  { light: ["secondary", "secondary-foreground"], dark: ["secondary", "secondary-foreground"], className: "bg-secondary text-secondary-foreground" },
  { light: ["mint", "rich-black"], dark: ["mint", "rich-black"], className: "bg-mint text-rich-black" },
  { light: ["status-info", "rich-black"], dark: ["status-info", "rich-black"], className: "bg-status-info text-rich-black" },
  { light: ["basil", "anti-flash"], dark: ["basil", "anti-flash"], className: "bg-basil text-anti-flash" },
  {
    light: ["dark-green", "mountain-meadow"],
    dark: ["mountain-meadow", "rich-black"],
    className: "bg-dark-green text-mountain-meadow dark:bg-mountain-meadow dark:text-rich-black",
  },
] as const;

/**
 * The tone of a contact: a stable hash (FNV-1a) of the conversation id, which
 * the list, the thread and the panel all have — the same person, the same
 * colour everywhere.
 */
export function contactTone(id: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < id.length; i++) {
    h ^= id.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0) % AVATAR_TONES.length;
}

/**
 * Who wrote, as a circle: their Instagram / Messenger picture when Auphere
 * stored one (owner, 2026-10-30), else their initials on their own colour —
 * also when the picture fails to load. A name without letters (only a number)
 * gets a person icon instead of «·» (spec 082, 5.3). Decorative: the name is
 * always written next to it.
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
  const tone = AVATAR_TONES[contactTone(conversationId)]!.className;
  if (hasAvatar && !broken) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- the bytes come from our own BFF route, not a static asset
      <img
        src={inboxAvatarUrl(conversationId)}
        alt=""
        aria-hidden="true"
        loading="lazy"
        onError={() => setBroken(true)}
        data-slot="contact-avatar"
        className={cn("shrink-0 rounded-full object-cover", tone, className)}
      />
    );
  }
  const letters = /\p{L}/u.test(initials);
  return (
    <span aria-hidden="true" data-slot="contact-avatar" className={cn("grid shrink-0 place-items-center rounded-full font-semibold", tone, className)}>
      {letters ? initials : <UserRound className="size-1/2" strokeWidth={2} />}
    </span>
  );
}
