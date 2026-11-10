import { MessageCircle } from "lucide-react";

import { cn } from "@nexus/ui";

import { BrandLogo, hasBrandLogo } from "@/components/brand-logo";

/**
 * The channel a conversation came through, on the corner of the contact's
 * picture (owner, 2026-11-01): the app's logo, or a neutral bubble for a kind
 * with none. Decorative: whoever needs the name gets it from the row's or the
 * panel's text.
 */
export function ChannelBadge({ kind, className }: { kind: string; className?: string }) {
  const corner = cn("absolute -right-1 -bottom-1 size-5 rounded-full ring-2 ring-card", className);
  if (hasBrandLogo(kind)) return <BrandLogo brand={kind} size="sm" className={corner} />;
  return (
    <span className={cn("grid place-items-center bg-card text-primary-text", corner)} aria-hidden="true">
      <MessageCircle className="size-3" />
    </span>
  );
}
