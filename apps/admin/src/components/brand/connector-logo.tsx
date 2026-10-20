"use client";

import { useState } from "react";

import { cn } from "@nexus/ui";

import type { Connector } from "@/lib/backend";

import { brandFor } from "./brand-marks";
import { BRAND_TILE_SIZE, BrandTile, type BrandTileSize } from "./brand-tile";

type ProviderMeta = {
  icon_url?: string;
  brand_color?: string;
  composio_toolkit_slug?: string;
};

/**
 * A connector's app icon. Resolution order:
 *
 * 1. The brand mark we ship (Simple Icons, `brand-marks.ts`) for the slug or
 *    its Composio toolkit — crisp at any size and in both themes.
 * 2. `provider_meta.icon_url` from the seed.
 * 3. Composio's CDN icon for `oauth_composio` connectors.
 * 4. Initials over the seed's brand colour.
 *
 * A remote image that fails to load falls to the next step instead of
 * leaving a blank square.
 */
export function ConnectorLogo({
  connector,
  size = "md",
  className,
}: {
  connector: Pick<Connector, "slug" | "display_name" | "auth_kind" | "provider_meta">;
  size?: BrandTileSize;
  className?: string;
}) {
  const meta = (connector.provider_meta ?? {}) as ProviderMeta;
  const mark = brandFor(connector.slug, meta.composio_toolkit_slug);
  const composioIcon =
    connector.auth_kind === "oauth_composio" && meta.composio_toolkit_slug
      ? `https://images.composio.dev/v2/icons/${meta.composio_toolkit_slug.toLowerCase()}.png`
      : null;
  const [src, setSrc] = useState<string | null>(meta.icon_url ?? composioIcon);
  const s = BRAND_TILE_SIZE[size];

  if (mark) return <BrandTile mark={mark} size={size} className={className} />;

  if (src === null) {
    const initials = connector.display_name
      .split(/\s+/)
      .map((w) => w[0]?.toUpperCase() ?? "")
      .join("")
      .slice(0, 2);
    return (
      <span
        aria-hidden="true"
        className={cn("grid shrink-0 place-items-center text-xs font-semibold text-white", s.tile, className)}
        style={{ backgroundColor: meta.brand_color ?? "var(--color-primary)" }}
      >
        {initials}
      </span>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt=""
      aria-hidden="true"
      className={cn("shrink-0 bg-white object-contain p-1 ring-1 ring-foreground/10", s.tile, className)}
      onError={() => setSrc(src === meta.icon_url && composioIcon ? composioIcon : null)}
    />
  );
}
