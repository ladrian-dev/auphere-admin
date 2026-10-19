import { cn } from "@nexus/ui";

import { BRAND_BACKGROUND, type BrandMark } from "./brand-marks";

export const BRAND_TILE_SIZE = {
  sm: { tile: "size-6 rounded-sm", glyph: "size-3" },
  md: { tile: "size-8 rounded-md", glyph: "size-4" },
  lg: { tile: "size-10 rounded-md", glyph: "size-5" },
  xl: { tile: "size-12 rounded-md", glyph: "size-6" },
} as const;

export type BrandTileSize = keyof typeof BRAND_TILE_SIZE;

/**
 * An app's icon as people know it from their phone: the brand's own colour
 * (or gradient) with its mark in white. Black marks get a hairline so they
 * keep their edge on the dark theme.
 */
export function BrandTile({
  mark,
  size = "md",
  className,
}: {
  mark: BrandMark & { key: string };
  size?: BrandTileSize;
  className?: string;
}) {
  const s = BRAND_TILE_SIZE[size];
  return (
    <span
      aria-hidden="true"
      className={cn("grid shrink-0 place-items-center ring-1 ring-foreground/10", s.tile, className)}
      style={{ background: BRAND_BACKGROUND[mark.key] ?? mark.hex }}
    >
      <svg viewBox="0 0 24 24" className={cn("fill-white", s.glyph)} role="presentation">
        <path d={mark.path} />
      </svg>
    </span>
  );
}
