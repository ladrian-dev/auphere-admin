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

import { signupLinkAction } from "@/app/(console)/clients/[ref]/channels/actions";
import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import { actionErrorText } from "@/lib/action-error";
import type { MetaSocialKind, MetaSocialOffer } from "@/lib/backend/channels";

type WhatsAppMode = "coexistence" | "cloud_api";

/**
 * Spec 040: the partner sends the business owner a link, and Meta's signup
 * runs on the owner's phone or computer — where they are already logged in
 * to Meta — instead of on the partner's. Coexistence comes first: it is the
 * one that needs the owner's own WhatsApp Business app.
 *
 * Spec 085 (R10): the same panel for Instagram and Messenger. Only WhatsApp
 * asks for a mode; the owner picks how to sign in to Meta on their page.
 * Copy, send by WhatsApp, send by e-mail with its channel's subject, and the
 * expiry are the same. Without the channel for the partner, nothing renders (§V).
 */
export function ShareLink({
  refId,
  channel,
  modes = [],
  offer = null,
  disabled,
  hasLive = false,
  fromPhone = false,
}: {
  refId: string;
  channel: "whatsapp" | MetaSocialKind;
  /** WhatsApp: the modes this environment can open. */
  modes?: WhatsAppMode[];
  /** Instagram / Messenger: the partner's offer (`overview.meta_social`). */
  offer?: MetaSocialOffer | null;
  disabled?: boolean;
  /** An unused link is out there: the new one replaces it. */
  hasLive?: boolean;
  /** Spec 047 (31.3): «desde su teléfono» only once it was tested on iOS and Android. */
  fromPhone?: boolean;
}) {
  const t = useT();
  const router = useRouter();
  const locale = useLocale();
  const [open, setOpen] = React.useState(false);
  const [mode, setMode] = React.useState<WhatsAppMode>(modes[0] ?? "coexistence");
  const [pending, start] = React.useTransition();
  const [link, setLink] = React.useState<{ url: string; expires_at: string } | null>(null);
  const whatsapp = channel === "whatsapp";
  if (!whatsapp && !offer?.channels.some((c) => c.kind === channel)) return null;

  function create() {
    start(async () => {
      const res = await signupLinkAction(whatsapp ? { ref: refId, channel, mode } : { ref: refId, channel });
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

  const messageKey: MessageKey = whatsapp ? (fromPhone ? "ch.link.message.phone" : "ch.link.message") : (`ch.link.message.${channel}` as MessageKey);
  const message = link ? t(messageKey, { url: link.url }) : "";
  const subject = t(whatsapp ? "ch.link.subject" : (`ch.link.subject.${channel}` as MessageKey));

  return (
    <>
      {/* Spec 085: «Enviar enlace de Messenger al cliente» is wider than an
          empty Channels page on a 360 px phone. The label wraps instead of
          overflowing; on one line the button keeps its 36 px. */}
      <Button
        variant="outline"
        className="h-auto min-h-9 max-w-full py-1 text-balance whitespace-normal"
        onClick={() => setOpen(true)}
        disabled={disabled || (whatsapp && modes.length === 0)}
      >
        <Link2 aria-hidden="true" />
        {t(whatsapp ? "ch.link.open" : (`ch.link.open.${channel}` as MessageKey))}
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
            <DialogTitle>{t(fromPhone ? "ch.link.title.phone" : "ch.link.title")}</DialogTitle>
            <DialogDescription>{t(whatsapp ? "ch.link.body" : (`ch.link.body.${channel}` as MessageKey))}</DialogDescription>
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
                    <a href={`mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(message)}`} />
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
              {whatsapp && modes.length > 1 ? (
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
