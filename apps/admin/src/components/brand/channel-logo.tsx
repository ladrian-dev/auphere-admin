import { MessageCircle } from "lucide-react";

import { cn } from "@nexus/ui";

import { brandFor } from "./brand-marks";
import { BRAND_TILE_SIZE, BrandTile, type BrandTileSize } from "./brand-tile";

/** Spec 035: a messaging channel's app icon (WhatsApp, TikTok, Instagram…). */
export function ChannelLogo({
  channel,
  size = "md",
  className,
}: {
  channel: string;
  size?: BrandTileSize;
  className?: string;
}) {
  const mark = brandFor(channel);
  if (mark) return <BrandTile mark={mark} size={size} className={className} />;
  const s = BRAND_TILE_SIZE[size];
  return (
    <span aria-hidden="true" className={cn("grid shrink-0 place-items-center bg-muted", s.tile, className)}>
      <MessageCircle className={cn("text-muted-foreground", s.glyph)} />
    </span>
  );
}
