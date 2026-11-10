"use client";

import { CheckCheck } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button, formatRelative, StatusBadge } from "@nexus/ui";

import { confirmSectionAction } from "@/app/(console)/clients/[ref]/client-v2-actions";
import { useLocale, useT } from "@/i18n/client";
import type { Provenance, Section } from "@/lib/backend/client-records";

import { needsReview, provenanceText } from "./provenance-model";

type Failed = { ok: false; status: number; message: string; code?: string | null };
type Result<T> = { ok: true; data: T } | Failed;

/**
 * La procedencia de una sección o de un dato (spec 047, requisito 13.1), con
 * su autor y cuándo. Lo leído pendiente de revisar sale en ámbar y, si quien
 * mira puede editar, con «Es correcto» (13.2): pasa a escrito por esa persona.
 */
export function ProvenanceLabel({
  provenance,
  meId,
  refId,
  section,
  canConfirm = false,
  confirm,
  onConfirmed,
}: {
  provenance: Provenance | null;
  meId: string | null;
  refId?: string;
  section?: Section;
  canConfirm?: boolean;
  /** Por defecto, la acción de servidor; las pruebas ponen la suya. */
  confirm?: (body: { ref: string; section: Section }) => Promise<Result<{ confirmed: number }>>;
  onConfirmed?: () => void;
}) {
  const t = useT();
  const locale = useLocale();
  const [pending, startTransition] = React.useTransition();
  if (!provenance) return null;
  const label = t("business.prov.when", {
    label: provenanceText(t, provenance, meId),
    when: formatRelative(provenance.at, locale),
  });
  const review = needsReview(provenance);
  const act = confirm ?? ((b: { ref: string; section: Section }) => confirmSectionAction(b));
  return (
    <span className="inline-flex min-w-0 flex-wrap items-center gap-2" data-slot="provenance">
      <StatusBadge tone={review ? "warn" : "muted"} className="max-w-full min-w-0">
        <span className="truncate" title={label}>
          {label}
        </span>
      </StatusBadge>
      {review && canConfirm && refId && section ? (
        <Button
          type="button"
          size="xs"
          variant="outline"
          disabled={pending}
          onClick={() =>
            startTransition(async () => {
              const res = await act({ ref: refId, section });
              if (!res.ok) {
                toast.error(t("business.sources.error.generic"));
                return;
              }
              toast.success(t("business.prov.confirmed"));
              onConfirmed?.();
            })
          }
        >
          <CheckCheck aria-hidden="true" />
          {t("business.prov.confirm")}
        </Button>
      ) : null}
    </span>
  );
}
