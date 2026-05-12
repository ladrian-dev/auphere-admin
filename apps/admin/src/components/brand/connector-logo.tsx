"use client";

import { useState } from "react";

import type { Connector } from "@/lib/backend";

type ProviderMeta = {
  icon_url?: string;
  brand_color?: string;
  composio_toolkit_slug?: string;
};

/**
 * Connector logo with robust fallback chain.
 *
 * Resolution order:
 * 1. ``provider_meta.icon_url`` from the seed (if loadable).
 * 2. Composio's CDN icon, derived from ``composio_toolkit_slug`` for
 *    ``oauth_composio`` connectors that don't ship an explicit icon_url.
 * 3. Initials over the brand color from the seed (or muted bg).
 *
 * The initials fallback also kicks in when the remote image fails to
 * load (404, CORS, network) — the previous version dropped to a blank
 * square so Calendly and AgendaPro looked broken in the catalog.
 */
export function ConnectorLogo({ connector }: { connector: Connector }) {
  const meta = connector.provider_meta as ProviderMeta;
  const seedIcon = meta?.icon_url;
  const composioSlug = meta?.composio_toolkit_slug;
  const composioIcon =
    connector.auth_kind === "oauth_composio" && composioSlug
      ? `https://images.composio.dev/v2/icons/${composioSlug.toLowerCase()}.png`
      : null;

  // Try seed icon first; if that 404s, fall through to Composio; if that
  // also 404s, render the initials block.
  const [src, setSrc] = useState<string | null>(seedIcon ?? composioIcon);

  if (src === null) {
    return <Initials connector={connector} />;
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt=""
      aria-hidden="true"
      className="size-8 rounded-sm object-contain bg-white border border-border p-1"
      onError={() => {
        if (src === seedIcon && composioIcon) {
          setSrc(composioIcon);
        } else {
          setSrc(null);
        }
      }}
    />
  );
}

function Initials({ connector }: { connector: Connector }) {
  const brand = (connector.provider_meta as ProviderMeta)?.brand_color;
  const initials = connector.display_name
    .split(/\s+/)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("")
    .slice(0, 2);
  return (
    <span
      aria-hidden="true"
      className="size-8 rounded-sm grid place-items-center text-xs font-mono font-semibold text-white"
      style={{ backgroundColor: brand ?? "var(--color-bangladesh-green)" }}
    >
      {initials}
    </span>
  );
}
