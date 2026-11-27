import { cookies } from "next/headers";
import { notFound } from "next/navigation";

import { EmptyState } from "@nexus/ui";

import { getT } from "@/i18n/server";
import { consoleService, type ChannelSignupLinkInfo } from "@/lib/backend";
import type { MetaSocialOffer } from "@/lib/backend/channels";

import { TOKEN_SHAPE, isSocialLinkKind, ownerLinkCookie } from "../whatsapp/link-cookie";
import { OwnerConnectSocial } from "./owner-connect-social";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ kind: string }> }) {
  const { kind } = await params;
  const { t } = await getT();
  return {
    title: t(kind === "messenger" ? "ch.social.connect.messenger" : "ch.social.connect.instagram"),
    robots: { index: false, follow: false },
  };
}

/**
 * Spec 085: the page the business owner opens from an Instagram or Messenger
 * link — the WhatsApp page of spec 040, one per channel. `whatsapp` has its
 * own static route, which wins over this one; any other value does not exist.
 */
export default async function OwnerSocialConnectPage({ params }: { params: Promise<{ kind: string }> }) {
  const { kind } = await params;
  if (!isSocialLinkKind(kind)) notFound();
  // The token came in the link and was moved to the channel's cookie by
  // `[token]/route.ts`: this page's address never carries it (7.4).
  const token = (await cookies()).get(ownerLinkCookie(kind))?.value ?? "";
  const { t } = await getT();
  const dead = (state: ChannelSignupLinkInfo["state"]) => (
    <EmptyState title={t(`connect.dead.${state === "valid" ? "unknown" : state}`)} description={t("connect.dead.body")} readonly />
  );
  if (!TOKEN_SHAPE.test(token)) return dead("unknown");
  const info = await consoleService.channelSignupInfo(token).catch(() => null);
  if (!info) return <EmptyState title={t("connect.error.generic")} readonly />;
  // A link of another channel in this channel's cookie is a link that does not exist here.
  if (info.state !== "valid" || info.channel !== kind || !info.meta_app_id || !info.meta_config_id) return dead(info.state);
  const offer: MetaSocialOffer = {
    app_id: info.meta_app_id,
    graph_version: info.meta_graph_version ?? "v26.0",
    channels: [{ kind, config_id: info.meta_config_id, page_config_id: info.meta_page_config_id ?? null }],
  };
  return <OwnerConnectSocial kind={kind} name={info.business_name ?? ""} offer={offer} />;
}
