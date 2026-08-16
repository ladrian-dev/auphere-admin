"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button, Checkbox, Input, Label, Textarea } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { UsageAlerts } from "@/lib/backend/home-usage";
import { parseAlertsForm } from "@/lib/usage-alerts-form";

import { saveUsageAlertsAction } from "./actions";

export function UsageAlertsForm({ initial, canManage }: { initial: UsageAlerts; canManage: boolean }) {
  const t = useT();
  const [cap, setCap] = React.useState(initial.cap_messages_month == null ? "" : String(initial.cap_messages_month));
  const [recipients, setRecipients] = React.useState(initial.recipients.join("\n"));
  const [enabled, setEnabled] = React.useState(initial.enabled);
  const [error, setError] = React.useState<string | null>(null);
  const [pending, start] = React.useTransition();

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const parsed = parseAlertsForm({ cap, recipients, enabled });
    if (!parsed.ok) {
      setError(parsed.error === "cap" ? t("hu.alerts.invalidCap") : t("hu.alerts.invalidEmail", { email: parsed.email ?? "" }));
      return;
    }
    setError(null);
    start(async () => {
      const res = await saveUsageAlertsAction(parsed.value);
      if (!res.ok) return void toast.error(res.status === 403 ? t("common.forbidden") : res.message);
      toast.success(t("hu.alerts.saved"));
    });
  }

  return (
    <form onSubmit={submit} className="flex max-w-lg flex-col gap-4" aria-describedby="alerts-help">
      <p id="alerts-help" className="text-sm text-muted-foreground">
        {t("hu.alerts.thresholds")}
      </p>
      <div className="flex flex-col gap-2">
        <Label htmlFor="cap">{t("hu.alerts.cap")}</Label>
        <Input id="cap" inputMode="numeric" value={cap} onChange={(e) => setCap(e.target.value)} disabled={!canManage || pending} aria-describedby="cap-help" className="w-48 tabular-nums" />
        <p id="cap-help" className="text-xs text-muted-foreground">
          {t("hu.alerts.cap.help")}
        </p>
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="recipients">{t("hu.alerts.recipients")}</Label>
        <Textarea id="recipients" rows={4} value={recipients} onChange={(e) => setRecipients(e.target.value)} disabled={!canManage || pending} aria-describedby="rec-help" className="font-mono text-sm" />
        <p id="rec-help" className="text-xs text-muted-foreground">
          {t("hu.alerts.recipients.help")}
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Checkbox id="enabled" checked={enabled} onCheckedChange={(v) => setEnabled(v === true)} disabled={!canManage || pending} />
        <Label htmlFor="enabled">{t("hu.alerts.enabled")}</Label>
      </div>
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      {canManage ? (
        <div>
          <Button type="submit" disabled={pending}>
            {t("common.save")}
          </Button>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">{t("hu.alerts.readonly")}</p>
      )}
    </form>
  );
}
