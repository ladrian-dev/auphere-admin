"use client";

import { useRouter } from "next/navigation";

import { useT } from "@/i18n/client";

import { WhatsAppConnect, type MetaSignupConfig } from "../whatsapp-connect";
import { WhatsAppContinueInBrowser } from "../whatsapp-continue-in-browser";
import { WhatsAppShareLink } from "../whatsapp-share-link";
import { wizardPaths } from "./steps";

/**
 * Spec 046, step 2: the two ways a partner connects a WhatsApp number, as
 * two choices side by side. The link to the owner comes first and marked
 * as the usual one (spec 040). Connecting from here moves straight on to
 * the agent step.
 */
export function ConnectWhatsAppStep({
  refId,
  meta,
  linkModes,
  canConnect,
  used,
  max,
  hasLiveLink,
  desktop,
}: {
  refId: string;
  meta: MetaSignupConfig;
  linkModes: Array<"coexistence" | "cloud_api">;
  canConnect: boolean;
  used: number;
  max: number;
  hasLiveLink: boolean;
  /** Inside the desktop app Meta's window does not come back (spec 002, R12.7). */
  desktop: boolean;
}) {
  const t = useT();
  const router = useRouter();
  const paths = wizardPaths(refId);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section className="flex flex-col gap-3 rounded-md p-5 ring-1 ring-primary/40" aria-labelledby="chw-link-title">
        <div className="flex flex-wrap items-center gap-2">
          <h3 id="chw-link-title" className="text-base font-medium">
            {t("chw.connect.link.title")}
          </h3>
          <span className="rounded-sm bg-primary/15 px-2 py-1 text-xs leading-none font-medium text-primary-text">
            {t("chw.connect.link.badge")}
          </span>
        </div>
        <p className="text-sm text-pretty text-muted-foreground">{t("chw.connect.link.body")}</p>
        <p className="text-sm text-pretty text-muted-foreground">{t("chw.connect.link.after")}</p>
        <div className="mt-auto pt-1">
          <WhatsAppShareLink refId={refId} modes={linkModes} disabled={!canConnect} hasLive={hasLiveLink} variant="default" />
        </div>
      </section>
      <section className="flex flex-col gap-3 rounded-md p-5 ring-1 ring-foreground/10" aria-labelledby="chw-here-title">
        <h3 id="chw-here-title" className="text-base font-medium">
          {t("chw.connect.here.title")}
        </h3>
        <p className="text-sm text-pretty text-muted-foreground">{desktop ? t("chw.connect.desktop.body") : t("chw.connect.here.body")}</p>
        <div className="mt-auto pt-1">
          {desktop ? (
            <WhatsAppContinueInBrowser href={paths.connect("whatsapp")} />
          ) : (
            <WhatsAppConnect
              refId={refId}
              meta={meta}
              canConnect={canConnect}
              used={used}
              max={max}
              variant="outline"
              onConnected={(channelId) => router.push(paths.agent("whatsapp", channelId))}
            />
          )}
        </div>
      </section>
    </div>
  );
}
