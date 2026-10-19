import { cookies } from "next/headers";

import { EmptyState } from "@nexus/ui";

import { getT } from "@/i18n/server";
import { consoleService, type ChannelSignupLinkInfo } from "@/lib/backend";

import { OWNER_LINK_COOKIE, TOKEN_SHAPE } from "./link-cookie";
import { OwnerConnect } from "./owner-connect";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: t("ch.connect"), robots: { index: false, follow: false } };
}

/**
 * Spec 040: the page the business owner opens from the link their partner
 * (or Auphere) sent. Meta's signup runs here, on the owner's device, with
 * the owner's own Meta login — never on the partner's computer.
 */
export default async function OwnerConnectPage() {
  // The token came in the link and was moved to a cookie by `[token]/route.ts`:
  // this page's address never carries it (Meta's SDK runs here).
  const token = (await cookies()).get(OWNER_LINK_COOKIE)?.value ?? "";
  const { t } = await getT();
  const dead = (state: ChannelSignupLinkInfo["state"]) => (
    <EmptyState title={t(`connect.dead.${state === "valid" ? "unknown" : state}`)} description={t("connect.dead.body")} readonly />
  );
  if (!TOKEN_SHAPE.test(token)) return dead("unknown");
  const info = await consoleService.channelSignupInfo(token).catch(() => null);
  if (!info) return <EmptyState title={t("connect.error.generic")} readonly />;
  if (info.state !== "valid" || !info.mode || !info.meta_app_id || !info.meta_config_id) return dead(info.state);
  return (
    <OwnerConnect
      name={info.business_name ?? ""}
      mode={info.mode}
      appId={info.meta_app_id}
      configId={info.meta_config_id}
      version={info.meta_graph_version ?? "v22.0"}
    />
  );
}
