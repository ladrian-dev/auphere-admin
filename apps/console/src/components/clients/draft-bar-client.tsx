"use client";

import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, Callout, DraftBar } from "@nexus/ui";

import { rollbackAgentAction } from "@/app/(console)/clients/actions";
import { draftDiffAction, publishFromBarAction } from "@/app/(console)/clients/[ref]/agent/actions";
import { useT } from "@/i18n/client";
import { actionErrorText } from "@/lib/action-error";
import type { DraftDiff, DraftScreen } from "@/lib/backend";

import { DraftDiffSheet } from "./draft-diff-sheet";

/** Diez minutos, los que promete la hoja antes de publicar. */
const UNDO_SECONDS = 10 * 60;

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
  activeVersion,
  canPublish,
}: {
  refId: string;
  screens: DraftScreen[];
  version: number;
  activeVersion: number | null;
  canPublish: boolean;
}) {
  const t = useT();
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [diff, setDiff] = React.useState<DraftDiff | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [state, setState] = React.useState<"pending" | "publishing" | "failed">("pending");
  // R3: publicar es reversible durante diez minutos, y el aviso no se cierra
  // mientras dure. El contador corre de verdad: prometer un plazo sin
  // enseñarlo obliga a vigilarlo o a perderlo.
  const [published, setPublished] = React.useState<{ version: number; previous: number | null } | null>(null);
  const [secondsLeft, setSecondsLeft] = React.useState(UNDO_SECONDS);

  React.useEffect(() => {
    if (!published) return;
    const id = window.setInterval(() => {
      setSecondsLeft((s) => {
        const left = s - 1;
        // El aviso se cierra solo al terminar el plazo, como promete la hoja.
        if (left <= 0) setPublished(null);
        return Math.max(0, left);
      });
    }, 1000);
    return () => window.clearInterval(id);
  }, [published]);
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
      setPublished({ version, previous: activeVersion });
      setSecondsLeft(UNDO_SECONDS);
      // La barra vive en el layout: al publicar, el punto de «sin publicar»
      // desaparece de todas las pestañas. El aviso sobrevive al refresco
      // porque el layout sigue montando este componente.
      router.refresh();
    });
  }

  function undo() {
    const previous = published?.previous;
    if (previous == null) return;
    startTransition(async () => {
      const res = await rollbackAgentAction({ ref: refId, version: previous });
      if (!res.ok) {
        toast.error(actionErrorText(res, t));
        return;
      }
      setPublished(null);
      toast.success(t("draft.published.undone", { version: previous }));
      router.refresh();
    });
  }

  if (published) {
    const minutes = Math.ceil(secondsLeft / 60);
    return (
      <Callout
        tone="positive"
        title={t("draft.published.title", { version: published.version })}
        action={
          published.previous != null && canPublish ? (
            <span className="flex items-center gap-2">
              <Button size="sm" variant="outline" onClick={undo}>
                {t("draft.published.undo")}
              </Button>
              <span className="text-xs text-muted-foreground tabular-nums">{t("draft.published.left", { minutes })}</span>
            </span>
          ) : undefined
        }
      >
        <span className="block max-w-prose text-pretty">
          {published.previous == null
            ? t("draft.published.bodyFirst")
            : t("draft.published.body", { previous: published.previous })}
        </span>
      </Callout>
    );
  }

  // Sin borrador y sin nada recién publicado, la barra no existe.
  if (screens.length === 0) return null;

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
