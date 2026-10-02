import { CreditCard, MessageSquareWarning, PhoneOff } from "lucide-react";
import Link from "next/link";

import type { MessageKey } from "@/i18n/messages";
import type { HomeToReview } from "@/lib/backend/home-usage";

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

/**
 * «Por revisar ahora» (spec 026, Historia 2): what the agent handed to a
 * person, across the portfolio. Each figure opens the client where it is.
 */
export function ReviewBlock({ review, t, n }: { review: HomeToReview; t: T; n: (v: number) => string }) {
  const rows = [
    { key: "escalated", icon: MessageSquareWarning, label: t("hu.home.review.escalated"), value: review.escalated },
    { key: "payments", icon: CreditCard, label: t("hu.home.review.payments"), value: review.payments },
    { key: "unanswered", icon: PhoneOff, label: t("hu.home.review.unanswered"), value: review.unanswered },
  ] as const;
  const first = (key: "escalated" | "payments" | "unanswered") => review.clients.find((c) => c[key] > 0)?.href;
  const nothing = review.escalated + review.payments + review.unanswered === 0;
  return (
    <section aria-labelledby="home-review-h" className="flex flex-col gap-3 rounded-md bg-card p-4 ring-1 ring-foreground/10" data-slot="home-review">
      <div className="flex items-baseline justify-between gap-2">
        <h2 id="home-review-h" className="text-base font-semibold">
          {t("hu.home.review.title")}
        </h2>
        <span className="text-xs text-muted-foreground">{t("hu.home.review.window")}</span>
      </div>
      {nothing ? (
        <p className="text-sm text-muted-foreground">{t("hu.home.review.none")}</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {rows.map(({ key, icon: Icon, label, value }) => {
            const href = value > 0 ? first(key) : undefined;
            const body = (
              <>
                <Icon aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1 truncate text-sm">{label}</span>
                <span className="text-lg font-semibold tabular-nums">{n(value)}</span>
              </>
            );
            return (
              <li key={key}>
                {href ? (
                  <Link href={href} className="flex items-center gap-3 rounded-md px-2 py-2 hover:bg-muted">
                    {body}
                  </Link>
                ) : (
                  <div className="flex items-center gap-3 px-2 py-2 opacity-70">{body}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {review.clients.length > 0 ? (
        <ul className="flex flex-col gap-1 border-t border-border pt-2">
          {review.clients.slice(0, 4).map((c) => (
            <li key={c.external_client_ref}>
              <Link href={c.href} className="flex items-center justify-between gap-2 text-xs text-muted-foreground hover:text-foreground">
                <span className="truncate">{c.client_name ?? c.external_client_ref}</span>
                <span className="tabular-nums">{n(c.escalated + c.payments + c.unanswered)}</span>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
