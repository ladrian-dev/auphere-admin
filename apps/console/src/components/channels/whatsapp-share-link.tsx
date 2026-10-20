"use client";

import { Copy, Link2, Mail, MessageCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  NativeSelect,
  formatDateTime,
} from "@nexus/ui";

import { whatsappSignupLinkAction } from "@/app/(console)/clients/[ref]/channels/actions";
import { useLocale, useT } from "@/i18n/client";
import { actionErrorText } from "@/lib/action-error";

/**
 * Spec 040: the partner sends the business owner a link, and Meta's signup
 * runs on the owner's phone or computer — where they are already logged in
 * to Meta — instead of on the partner's. Coexistence comes first: it is the
 * one that needs the owner's own WhatsApp Business app.
 */
export function WhatsAppShareLink({
  refId,
  modes,
  disabled,
  hasLive = false,
}: {
  refId: string;
  modes: Array<"coexistence" | "cloud_api">;
  disabled?: boolean;
  /** An unused link is out there: the new one replaces it. */
  hasLive?: boolean;
}) {
  const t = useT();
  const router = useRouter();
  const locale = useLocale();
  const [open, setOpen] = React.useState(false);
  const [mode, setMode] = React.useState(modes[0] ?? "coexistence");
  const [pending, start] = React.useTransition();
  const [link, setLink] = React.useState<{ url: string; expires_at: string } | null>(null);

  function create() {
    start(async () => {
      const res = await whatsappSignupLinkAction({ ref: refId, mode });
      if (!res.ok) return void toast.error(actionErrorText(res, t));
      setLink({ url: res.data.url, expires_at: res.data.expires_at });
      // The list of links under the button now shows this one.
      router.refresh();
    });
  }

  async function copy() {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link.url);
      toast.success(t("ch.link.copied"));
    } catch {
      toast.error(t("common.error.backend"));
    }
  }

  const message = link ? t("ch.link.message", { url: link.url }) : "";

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)} disabled={disabled || modes.length === 0}>
        <Link2 aria-hidden="true" />
        {t("ch.link.open")}
      </Button>
      <Dialog
        open={open}
        onOpenChange={(o) => {
          setOpen(o);
          if (!o) setLink(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("ch.link.title")}</DialogTitle>
            <DialogDescription>{t("ch.link.body")}</DialogDescription>
          </DialogHeader>
          {link ? (
            <div className="flex flex-col gap-3">
              <div className="flex gap-2">
                <Input readOnly value={link.url} aria-label={t("ch.link.copy")} onFocus={(e) => e.currentTarget.select()} />
                <Button onClick={copy}>
                  <Copy aria-hidden="true" />
                  {t("ch.link.copy")}
                </Button>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  nativeButton={false}
                  render={<a href={`https://wa.me/?text=${encodeURIComponent(message)}`} target="_blank" rel="noreferrer" />}
                >
                  <MessageCircle aria-hidden="true" />
                  {t("ch.link.whatsapp")}
                </Button>
                <Button
                  variant="outline"
                  nativeButton={false}
                  render={
                    <a href={`mailto:?subject=${encodeURIComponent(t("ch.link.subject"))}&body=${encodeURIComponent(message)}`} />
                  }
                >
                  <Mail aria-hidden="true" />
                  {t("ch.link.email")}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                {t("ch.link.expires", { date: formatDateTime(link.expires_at, locale) })}
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              {hasLive ? <p className="text-sm text-muted-foreground">{t("ch.link.replaces")}</p> : null}
              {modes.length > 1 ? (
                <div className="flex flex-col gap-2">
                  <Label htmlFor="link-mode">{t("ch.connect.mode")}</Label>
                  <NativeSelect id="link-mode" value={mode} onChange={(e) => setMode(e.target.value as typeof mode)}>
                    {modes.map((m) => (
                      <option key={m} value={m}>
                        {t(`ch.connect.mode.${m}`)}
                      </option>
                    ))}
                  </NativeSelect>
                </div>
              ) : null}
              <div>
                <Button onClick={create} disabled={pending} aria-busy={pending}>
                  {pending ? t("ch.link.creating") : t("ch.link.create")}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
