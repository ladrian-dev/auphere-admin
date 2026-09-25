"use client";

import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { DraftBar } from "@nexus/ui";

import { draftDiffAction, publishFromBarAction } from "@/app/(console)/clients/[ref]/agent/actions";
import { useT } from "@/i18n/client";
import { actionErrorText } from "@/lib/action-error";
import type { DraftDiff, DraftScreen } from "@/lib/backend";

import { DraftDiffSheet } from "./draft-diff-sheet";

/**
 * La barra del borrador, montada en el layout de la ficha (spec 017, R3):
 * un cambio hecho en Ajustes se publicaba solo desde «Agente», así que se
 * quedaba ahí sin que nadie lo supiera. Ahora se ve y se publica desde
 * cualquier pestaña, y siempre pasando por la hoja de revisión: publicar
 * sin mirar qué recorta el servicio no es una decisión, es un accidente.
 */
export function DraftBarClient({
  refId,
  screens,
  version,
  canPublish,
}: {
  refId: string;
  screens: DraftScreen[];
  version: number;
  canPublish: boolean;
}) {
  const t = useT();
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [diff, setDiff] = React.useState<DraftDiff | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [state, setState] = React.useState<"pending" | "publishing" | "failed">("pending");
  const [, startTransition] = React.useTransition();

  // El diff se pide al abrir, no al montar: la mayoría de las visitas a la
  // ficha no terminan en publicar.
  function openSheet() {
    setOpen(true);
    if (diff || loading) return;
    setLoading(true);
    startTransition(async () => {
      const res = await draftDiffAction({ ref: refId });
      setLoading(false);
      if (!res.ok) {
        toast.error(actionErrorText(res, t));
        return;
      }
      setDiff(res.data);
    });
  }

  function publish() {
    setState("publishing");
    startTransition(async () => {
      const res = await publishFromBarAction({ ref: refId, version });
      if (!res.ok) {
        setState("failed");
        toast.error(actionErrorText(res, t));
        return;
      }
      setOpen(false);
      setState("pending");
      toast.success(t("draft.bar.published"));
      // La barra vive en el layout: al publicar desaparece de todas las
      // pestañas, no solo de la que estaba abierta.
      router.refresh();
    });
  }

  return (
    <>
      <DraftBar
        screens={screens.map((s) => t(`draft.screen.${s}`))}
        canPublish={canPublish}
        state={state}
        onDiff={openSheet}
        onPublish={state === "failed" ? publish : openSheet}
        failure={state === "failed" ? t("draft.bar.failure") : undefined}
        labels={{
          unpublishedIn: t("draft.bar.unpublishedIn"),
          and: t("draft.bar.and"),
          diff: t("draft.bar.diff"),
          publish: t("draft.bar.publish"),
          publishing: t("draft.bar.publishing"),
          retry: t("draft.bar.retry"),
          whoCanPublish: t("draft.bar.who"),
          announce: t("draft.bar.announce"),
          failureAnnounce: t("draft.bar.failureAnnounce"),
        }}
      />
      <DraftDiffSheet
        open={open}
        onOpenChange={setOpen}
        diff={diff}
        loading={loading}
        canPublish={canPublish}
        publishing={state === "publishing"}
        onPublish={publish}
      />
    </>
  );
}
