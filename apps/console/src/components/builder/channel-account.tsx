"use client";

import { DescriptionList, StatusBadge } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { WhatsAppAccount } from "@/lib/backend/channel-config-types";

type T = ReturnType<typeof useT>;

/** Meta's codes (`NAME_FORMAT_UNACCEPTABLE`) as words, when there is no copy of ours. */
export function humanCode(code: string): string {
  const words = code.replace(/_/g, " ").toLowerCase().trim();
  return words ? words[0]!.toUpperCase() + words.slice(1) : code;
}

/** `TIER_2K` → 2000, `TIER_UNLIMITED` → null (no limit), anything else → undefined. */
export function tierPeople(tier: string): number | null | undefined {
  if (tier === "TIER_UNLIMITED") return null;
  const m = /^TIER_(\d+)(K?)$/.exec(tier);
  if (!m) return undefined;
  return Number(m[1]) * (m[2] ? 1000 : 1);
}

function limitText(t: T, locale: string, tier: string): string {
  const people = tierPeople(tier);
  if (people === null) return t("builder.channel.account.limit.unlimited");
  if (people === undefined) return humanCode(tier);
  return t("builder.channel.account.limit.people", { n: people.toLocaleString(locale) });
}

const QUALITY: Record<string, { key: MessageKey; tone: "positive" | "warning" | "danger" }> = {
  GREEN: { key: "builder.channel.account.quality.GREEN", tone: "positive" },
  YELLOW: { key: "builder.channel.account.quality.YELLOW", tone: "warning" },
  RED: { key: "builder.channel.account.quality.RED", tone: "danger" },
};

const REVIEW: Record<string, MessageKey> = {
  APPROVED: "builder.channel.account.review.APPROVED",
  PENDING: "builder.channel.account.review.PENDING",
  REJECTED: "builder.channel.account.review.REJECTED",
  DEFERRED: "builder.channel.account.review.DEFERRED",
};

/** Pure: the rows the section shows, only the ones Meta has said something about. */
export function accountRows(t: T, locale: string, a: WhatsAppAccount) {
  const rows: { key: string; term: string; detail: React.ReactNode }[] = [];
  const name =
    a.name_decision === "REJECTED" && a.requested_name
      ? t("builder.channel.account.name.rejected", {
          name: a.requested_name,
          reason: humanCode(a.name_rejection_reason ?? ""),
        })
      : a.name_decision === "PENDING" && a.requested_name
        ? t("builder.channel.account.name.pending", { name: a.requested_name })
        : a.verified_name;
  if (name) rows.push({ key: "name", term: t("builder.channel.account.name"), detail: name });
  if (a.username) {
    const pending = a.username_status && a.username_status.toLowerCase() !== "approved";
    rows.push({
      key: "username",
      term: t("builder.channel.account.username"),
      detail: pending ? t("builder.channel.account.username.pending", { username: a.username }) : `@${a.username}`,
    });
  }
  const quality = a.quality_rating ? QUALITY[a.quality_rating.toUpperCase()] : undefined;
  if (quality) {
    rows.push({
      key: "quality",
      term: t("builder.channel.account.quality"),
      detail: <StatusBadge tone={quality.tone}>{t(quality.key)}</StatusBadge>,
    });
  }
  if (a.messaging_limit) {
    rows.push({ key: "limit", term: t("builder.channel.account.limit"), detail: limitText(t, locale, a.messaging_limit) });
  }
  const review = a.account_review ? REVIEW[a.account_review.toUpperCase()] : undefined;
  if (review) rows.push({ key: "review", term: t("builder.channel.account.review"), detail: t(review) });
  return rows;
}

/**
 * Spec 050 (4.1, 4.2, 4.4, 8.4): what Meta says about the WhatsApp number —
 * its display name and Meta's decision on it, its username, quality, limit,
 * the account review and the alerts still active. Read only: it is Meta's,
 * and it changes when Meta says so.
 */
export function ChannelAccount({ account }: { account: WhatsAppAccount }) {
  const t = useT();
  const locale = useLocale();
  const rows = accountRows(t, locale, account);
  return (
    <div className="grid min-w-0 gap-3" data-slot="channel-account">
      {rows.length > 0 ? <DescriptionList items={rows} /> : null}
      {account.alerts.length > 0 ? (
        <div className="grid min-w-0 gap-2">
          <h3 className="text-sm font-medium">{t("builder.channel.account.alerts")}</h3>
          <ul className="grid min-w-0 gap-1 text-sm" aria-label={t("builder.channel.account.alerts")}>
            {account.alerts.map((alert, i) => (
              <li key={`${alert.type}-${i}`} className="flex min-w-0 flex-wrap items-center gap-2">
                <StatusBadge tone={alert.severity === "CRITICAL" ? "danger" : "muted"}>
                  {alert.severity === "CRITICAL" ? t("builder.channel.account.alert.critical") : t("builder.channel.account.alert.info")}
                </StatusBadge>
                <span className="min-w-0 text-pretty break-words">{humanCode(alert.type ?? "")}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

/** Whether there is anything to show at all. */
export function hasAccountFacts(t: T, locale: string, account: WhatsAppAccount | null | undefined): account is WhatsAppAccount {
  return !!account && (accountRows(t, locale, account).length > 0 || account.alerts.length > 0);
}
