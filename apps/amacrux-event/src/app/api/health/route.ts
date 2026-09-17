import { NextResponse } from "next/server";

import { destinationsMode, leadDeliveryConfig, leadStorageConfig, leadWebhookConfig } from "@/lib/env.server";

export const dynamic = "force-dynamic";

export function GET(): NextResponse {
  const storage = leadStorageConfig();
  const delivery = leadDeliveryConfig();
  return NextResponse.json({ status: "ok", app: "amacrux-event", mode: destinationsMode(storage, delivery), storage: storage.enabled, email: delivery.mode === "live", sheet: leadWebhookConfig().enabled });
}
