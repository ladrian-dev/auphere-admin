"use client";

import { useRouter } from "next/navigation";

import { ErrorState } from "@nexus/ui";

import { useT } from "@/i18n/client";

/** El Panel no se pudo leer: lo dice y ofrece reintentar (vuelve a pedirlo). */
export function PanelError() {
  const t = useT();
  const router = useRouter();
  return <ErrorState title={t("panel.error")} onRetry={() => router.refresh()} retryLabel={t("panel.retry")} />;
}
