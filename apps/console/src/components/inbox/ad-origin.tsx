import { useT } from "@/i18n/client";
import type { InboxAdOrigin } from "@/lib/backend/inbox";

/**
 * Spec 076 (R2.1–2.3): which ad or post the person came from, under the name in
 * the thread header. With a link when Meta gave one (it opens in a new tab);
 * without a headline it still says «Desde un anuncio». The headline is the
 * advertiser's text: it is shown, never interpreted.
 */
export function AdOriginLine({ origin }: { origin: InboxAdOrigin }) {
  const t = useT();
  const text = adOriginText(t, origin, "line");
  if (!origin.url) {
    return <span className="truncate text-xs text-muted-foreground" title={text}>{text}</span>;
  }
  return (
    <a
      href={origin.url}
      target="_blank"
      rel="noopener noreferrer"
      title={`${text} · ${t("inbox.ad.opens")}`}
      className="truncate text-xs font-medium text-primary-text underline-offset-4 hover:underline"
    >
      {text}
      <span className="sr-only"> ({t("inbox.ad.opens")})</span>
    </a>
  );
}

type T = ReturnType<typeof useT>;

/** «Desde un anuncio: …» in the header; «Un anuncio: …» in the contact panel. */
export function adOriginText(t: T, origin: InboxAdOrigin, where: "line" | "panel"): string {
  const post = origin.kind === "post";
  if (where === "panel") {
    const kind = post ? t("inbox.panel.post") : t("inbox.panel.ad");
    return origin.headline ? `${kind}: ${origin.headline}` : kind;
  }
  if (origin.headline) {
    return post
      ? t("inbox.ad.from_post", { headline: origin.headline })
      : t("inbox.ad.from_ad", { headline: origin.headline });
  }
  return post ? t("inbox.ad.from_post.plain") : t("inbox.ad.from_ad.plain");
}
