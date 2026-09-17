import type { Utm } from "@/domain/types";
import { CampaignSchema, UtmSchema } from "@/domain/validation";

export const CAMPAIGN_KEY = "amacrux-campaign:v1";

export interface CampaignInfo {
  campaign?: string;
  utm?: Utm;
}

/** Extrae campaña y UTM de un slug y/o parámetros. Rechaza lo que no cumpla el patrón. */
export function parseCampaign(slug: string | undefined, params: URLSearchParams | Record<string, string | undefined>): CampaignInfo {
  const get = (k: string) => (params instanceof URLSearchParams ? params.get(k) ?? undefined : params[k]);
  const out: CampaignInfo = {};
  const candidate = slug ?? get("evento") ?? get("utm_campaign");
  if (candidate) {
    const c = CampaignSchema.safeParse(candidate.toLowerCase());
    if (c.success) out.campaign = c.data;
  }
  const utm = UtmSchema.safeParse({
    source: get("utm_source") || undefined,
    medium: get("utm_medium") || undefined,
    campaign: get("utm_campaign") || undefined,
    content: get("utm_content") || undefined,
  });
  if (utm.success && Object.values(utm.data).some(Boolean)) out.utm = utm.data;
  return out;
}

export function rememberCampaign(info: CampaignInfo): void {
  try {
    if (!info.campaign && !info.utm) return;
    window.sessionStorage.setItem(CAMPAIGN_KEY, JSON.stringify(info));
  } catch {
    // sin storage no pasa nada
  }
}

export function readCampaignInfo(): CampaignInfo {
  try {
    const raw = window.sessionStorage.getItem(CAMPAIGN_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as CampaignInfo;
    const campaign = parsed.campaign ? CampaignSchema.safeParse(parsed.campaign) : undefined;
    const utm = parsed.utm ? UtmSchema.safeParse(parsed.utm) : undefined;
    return { campaign: campaign?.success ? campaign.data : undefined, utm: utm?.success ? utm.data : undefined };
  } catch {
    return {};
  }
}

export function readCampaign(): string | undefined {
  if (typeof window === "undefined") return undefined;
  return readCampaignInfo().campaign;
}
