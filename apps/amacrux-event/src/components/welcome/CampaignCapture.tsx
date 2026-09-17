"use client";

import { useSearchParams } from "next/navigation";
import { useEffect } from "react";

import { track } from "@/lib/analytics";
import { parseCampaign, rememberCampaign } from "@/lib/campaign";

/** Sin UI: guarda la campaña/UTM en la sesión y emite landing_viewed. */
export function CampaignCapture({ slug }: { slug?: string }) {
  const params = useSearchParams();
  useEffect(() => {
    const info = parseCampaign(slug, params);
    rememberCampaign(info);
    track("landing_viewed", { campaign: info.campaign });
  }, [slug, params]);
  return null;
}
