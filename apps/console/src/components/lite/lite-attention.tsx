import { CircleCheck, TriangleAlert } from "lucide-react";
import Link from "next/link";

import { Button, cn } from "@nexus/ui";

import type { MessageKey } from "@/i18n/messages";
import type { LiteHome, LiteMe } from "@/lib/backend/lite";

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

/**
 * «Necesita tu atención» of one client (spec 030, R4.5–R4.7). What waits for
 * a person goes first, with its way in; a short balance says for how long it
 * lasts and whom to ask — there is no buy button (the balance is read-only,
 * C2). Nothing pending is one calm line, never an empty block.
 */
export function LiteAttention({
  home,
  contact,
  modules,
  t,
  n,
}: {
  home: LiteHome;
  contact: LiteMe["balance_contact"] | null;
  modules: readonly string[];
  t: T;
  n: (v: number) => string;
}) {
  const hasInbox = modules.includes("inbox");
  const ask = contact
    ? contact.kind === "auphere"
      ? t("lite.attention.ask.auphere")
      : t("lite.attention.ask.partner", { name: contact.name })
    : null;
  if (home.attention.length === 0) {
    if (home.errors.length > 0) return null;
    // Only say the balance lasts when there is a balance to speak of.
    const balanceKnown = home.balance?.assigned === true;
    const line = balanceKnown
      ? hasInbox
        ? t("lite.ok.withInbox")
        : t("lite.ok")
      : hasInbox
        ? t("lite.ok.noBalance.withInbox")
        : null;
    if (!line) return null;
    return (
      <div className="flex items-center gap-3 rounded-md px-4 py-3 ring-1 ring-foreground/10" role="status">
        <CircleCheck className="size-5 shrink-0 text-status-positive" aria-hidden="true" />
        <p className="text-sm text-pretty">{line}</p>
      </div>
    );
  }
  return (
    <section aria-labelledby="lite-attention-h" className="flex flex-col gap-2 rounded-md p-4 ring-1 ring-status-danger/30">
      <h2 id="lite-attention-h" className="flex items-center gap-2 text-base font-semibold tracking-tight text-balance">
        <TriangleAlert className="size-4 text-status-danger" aria-hidden="true" />
        {t("lite.attention.title")}
        <span className="rounded-full bg-status-danger/15 px-2 text-xs tabular-nums">{n(home.attention.length)}</span>
      </h2>
      <ul className="flex flex-col">
        {home.attention.map((item, i) => {
          const last = i === home.attention.length - 1;
          if (item.kind === "waiting") {
            const count = item.count ?? 0;
            const href = home.waiting?.first_conversation_id ? `/inbox?c=${encodeURIComponent(home.waiting.first_conversation_id)}` : "/inbox";
            return (
              <Row key="waiting" last={last} tone="danger" title={t("lite.attention.inbox")} body={count === 1 ? t("lite.attention.waiting.one") : t("lite.attention.waiting", { count: n(count) })}>
                {hasInbox ? (
                  <Button size="sm" nativeButton={false} render={<Link href={href} />}>
                    {t("lite.attention.attend")}
                  </Button>
                ) : null}
              </Row>
            );
          }
          const body =
            item.kind === "balance_out" ? t("lite.attention.balance_out") : t("lite.attention.balance_low", { days: n(Math.floor(item.days_left ?? 0)) });
          return (
            <Row key={item.kind} last={last} tone={item.kind === "balance_out" ? "danger" : "warning"} title={t("lite.attention.balance")} body={ask ? `${body}. ${ask}` : body}>
              {modules.includes("usage") ? (
                <Button size="sm" variant="outline" nativeButton={false} render={<Link href="/usage" />}>
                  {t("lite.spend.see")}
                </Button>
              ) : null}
            </Row>
          );
        })}
      </ul>
    </section>
  );
}

function Row({
  title,
  body,
  tone,
  last,
  children,
}: {
  title: string;
  body: string;
  tone: "danger" | "warning";
  last: boolean;
  children?: React.ReactNode;
}) {
  return (
    <li className={cn("flex items-center gap-4 py-2", !last && "border-b border-border")}>
      <span aria-hidden="true" className={cn("mt-2 size-2 shrink-0 self-start rounded-full", tone === "danger" ? "bg-status-danger" : "bg-status-warning")} />
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="text-sm font-medium">{title}</span>
        <span className="text-sm text-muted-foreground text-pretty">{body}</span>
      </div>
      {children}
    </li>
  );
}
