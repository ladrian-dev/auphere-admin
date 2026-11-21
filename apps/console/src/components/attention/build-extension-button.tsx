"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@nexus/ui";

import { requestBuildExtensionAction } from "@/app/(console)/usage/money-actions";
import { useT } from "@/i18n/client";

/** Pide la ampliación del tope de construcción, con su aviso — spec 071 y 072 (3.4). */
export function useBuildExtension() {
  const t = useT();
  const [asking, setAsking] = React.useState(false);
  const ask = React.useCallback(async () => {
    setAsking(true);
    const res = await requestBuildExtensionAction();
    setAsking(false);
    if (res.ok) toast.success(t("att.build.requested"));
    else toast.error(res.status === 429 ? t("att.build.already") : t("common.error.backend"));
  }, [t]);
  return { ask, asking };
}

/** «Pedir ampliación» en la línea del Panel (spec 072, 3.4 y 4.4). */
export function BuildExtensionButton() {
  const t = useT();
  const { ask, asking } = useBuildExtension();
  return (
    <Button size="sm" variant="outline" onClick={ask} disabled={asking} className="justify-self-start">
      {t("panel.v2.fix.request_build_extension")}
    </Button>
  );
}
