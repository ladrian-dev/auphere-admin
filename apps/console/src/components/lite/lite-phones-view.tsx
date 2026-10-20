"use client";

import { Smartphone } from "lucide-react";
import { useRouter } from "next/navigation";
import { startTransition, useOptimistic, useState } from "react";
import { toast } from "sonner";

import { Alert, AlertDescription, Button, ConfirmDialog, EmptyState, ErrorState, formatDate, formatRelative } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import type { ActionResult } from "@/lib/actions";
import type { LitePhone } from "@/lib/backend/lite";

const PLATFORM: Record<LitePhone["platform"], string> = { ios: "iPhone", android: "Android" };

/**
 * «Tus teléfonos» (spec 031, R7.3, R7.5), in its five states:
 *
 * - loading — `account/phones/loading.tsx`, same rows and heights;
 * - error — `phones === null`: the read failed, retry; never painted as empty;
 * - empty — no phone signed in yet, and how to get one in;
 * - partial — a sign-out that failed: the phone comes back with the reason;
 * - ideal — the list, each one closable after a confirmation.
 *
 * Closing is optimistic: the row goes as soon as the person confirms, and
 * comes back if the API says no. Revoking is the safe direction, so a slow
 * network never leaves someone staring at a phone they just closed.
 */
export function LitePhonesView({
  phones,
  now,
  closePhone,
}: {
  phones: LitePhone[] | null;
  /** The server's clock, so «hace 2 h» does not drift between server and browser. */
  now: string;
  closePhone: (raw: { id: string }) => Promise<ActionResult<null>>;
}) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const [asking, setAsking] = useState<LitePhone | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [shown, hide] = useOptimistic(phones ?? [], (list, id: string) => list.filter((p) => p.id !== id));

  if (phones === null) {
    return (
      <ErrorState
        title={t("lite.phones.error.title")}
        description={t("lite.phones.error.body")}
        onRetry={() => router.refresh()}
      />
    );
  }

  if (shown.length === 0 && !failed) {
    return (
      <EmptyState
        icon={Smartphone}
        title={t("lite.phones.empty.title")}
        description={t("lite.phones.empty.body")}
        readonly
      />
    );
  }

  function confirmClose(phone: LitePhone) {
    setAsking(null);
    setFailed(null);
    startTransition(async () => {
      hide(phone.id);
      const res = await closePhone({ id: phone.id });
      if (res.ok) {
        toast.success(t("lite.phones.closed", { name: phone.display_name }));
      } else {
        setFailed(phone.display_name);
      }
    });
  }

  const at = new Date(now);
  return (
    <div className="flex min-w-0 flex-col gap-4">
      {failed ? (
        <Alert variant="destructive">
          <AlertDescription>{t("lite.phones.closeFailed", { name: failed })}</AlertDescription>
        </Alert>
      ) : null}
      <ul
        aria-label={t("lite.phones.list")}
        className="flex min-w-0 flex-col divide-y divide-border rounded-md border border-border bg-card"
      >
        {shown.map((phone) => (
          <li key={phone.id} className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-3 px-4 py-4">
            <span
              aria-hidden="true"
              className="grid size-10 shrink-0 place-items-center rounded-md bg-muted text-muted-foreground"
            >
              <Smartphone className="size-5" />
            </span>
            <div className="flex min-w-0 flex-1 basis-48 flex-col gap-1">
              <p className="truncate text-sm font-medium" title={phone.display_name}>
                {phone.display_name}
              </p>
              <p className="text-xs text-pretty text-muted-foreground">
                {t("lite.phones.meta", { platform: PLATFORM[phone.platform], version: phone.app_version })}
                {" · "}
                {t("lite.phones.lastSeen", { when: formatRelative(phone.last_seen_at, locale, at) })}
              </p>
              <p className="text-xs text-muted-foreground">
                {t("lite.phones.enrolled", { date: formatDate(phone.enrolled_at, locale) })}
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="shrink-0"
              aria-label={t("lite.phones.close.aria", { name: phone.display_name })}
              onClick={() => setAsking(phone)}
            >
              {t("lite.phones.close")}
            </Button>
          </li>
        ))}
      </ul>
      <ConfirmDialog
        open={asking !== null}
        onOpenChange={(open) => {
          if (!open) setAsking(null);
        }}
        title={asking ? t("lite.phones.confirm.title", { name: asking.display_name }) : ""}
        description={t("lite.phones.confirm.body")}
        confirmLabel={t("lite.phones.close")}
        destructive
        onConfirm={() => {
          if (asking) confirmClose(asking);
        }}
      />
    </div>
  );
}
