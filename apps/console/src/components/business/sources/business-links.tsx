"use client";

import { Plus, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button, Field, Input, NativeSelect } from "@nexus/ui";

import { putLinksAction } from "@/app/(console)/clients/[ref]/client-v2-actions";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { LinkItem } from "@/lib/backend/client-records";
import type { Network } from "@/lib/backend/clients-v2";

type Failed = { ok: false; status: number; message: string; code?: string | null };
type Result<T> = { ok: true; data: T } | Failed;

/** Las que están siempre (requisito 12.4); las demás se añaden. */
export const ALWAYS: readonly Network[] = ["instagram", "facebook"];
export const OPTIONAL: readonly Network[] = ["web", "tiktok", "linkedin", "youtube", "x", "threads"];

export type LinkRow = { key: string; network: Network; value: string };

/** De lo guardado a las filas del formulario: Instagram y Facebook siempre, primero. */
export function rowsFrom(links: readonly LinkItem[]): LinkRow[] {
  const rows: LinkRow[] = links.map((l) => ({
    key: l.id,
    network: l.network,
    value: (l.network === "web" || l.network === "linkedin" ? l.url : l.handle) ?? l.url ?? "",
  }));
  for (const n of [...ALWAYS].reverse()) {
    if (!rows.some((r) => r.network === n)) rows.unshift({ key: `new-${n}`, network: n, value: "" });
  }
  return rows;
}

/** De las filas a lo que guarda la API: las vacías no se mandan. */
export function linksFrom(rows: readonly LinkRow[]): { network: Network; url?: string; handle?: string }[] {
  return rows
    .filter((r) => r.value.trim())
    .map((r) => {
      const value = r.value.trim();
      return /^https?:\/\//i.test(value) || r.network === "web" ? { network: r.network, url: value } : { network: r.network, handle: value };
    });
}

/**
 * «Redes» de la ficha (spec 047, T071, requisito 12.4): la web y las redes con
 * su enlace o su usuario. Instagram y Facebook están siempre; TikTok, LinkedIn,
 * YouTube, X y Threads se añaden. Se guarda con la revisión de la sección: si
 * otra persona guardó antes, la API responde 412 y no se pisa nada.
 */
export function BusinessLinks({
  refId,
  links,
  revision,
  canWrite,
  save,
  onSaved,
}: {
  refId: string;
  links: readonly LinkItem[];
  revision: number;
  canWrite: boolean;
  save?: (body: { ref: string; revision: number; links: ReturnType<typeof linksFrom> }) => Promise<Result<{ links: LinkItem[]; revision: number }>>;
  onSaved?: (revision: number) => void;
}) {
  const t = useT();
  const [rows, setRows] = React.useState<LinkRow[]>(() => rowsFrom(links));
  const [rev, setRev] = React.useState(revision);
  const [adding, setAdding] = React.useState<Network>("tiktok");
  const [pending, startTransition] = React.useTransition();
  const base = React.useId();
  const doSave = save ?? ((b) => putLinksAction(b));
  const networkName = (n: Network) => t(`business.links.network.${n}` as MessageKey);
  const free = OPTIONAL.filter((n) => !rows.some((r) => r.network === n));

  function submit(event: React.FormEvent) {
    event.preventDefault();
    startTransition(async () => {
      const res = await doSave({ ref: refId, revision: rev, links: linksFrom(rows) });
      if (!res.ok) {
        toast.error(
          res.status === 412
            ? t("business.socials.error.revision_conflict")
            : res.code === "invalid_link"
              ? t("business.socials.error.invalid_link")
              : t("business.sources.error.generic"),
        );
        return;
      }
      setRows(rowsFrom(res.data.links));
      setRev(res.data.revision);
      toast.success(t("business.socials.saved"));
      onSaved?.(res.data.revision);
    });
  }

  return (
    <section className="grid min-w-0 gap-4" aria-labelledby={`${base}-title`} data-slot="business-links">
      <div className="grid min-w-0 gap-1">
        <h2 id={`${base}-title`} className="text-base font-semibold text-balance">
          {t("business.socials.title")}
        </h2>
        <p className="text-sm text-muted-foreground text-pretty">{t("business.socials.intro")}</p>
      </div>
      <form onSubmit={submit} className="grid min-w-0 gap-3" noValidate>
        {rows.map((row, i) => {
          const id = `${base}-${row.key}`;
          const isUrl = row.network === "web" || row.network === "linkedin";
          return (
            <div key={row.key} className="flex min-w-0 items-end gap-2">
              <Field
                label={isUrl ? t("business.socials.url", { network: networkName(row.network) }) : t("business.socials.handle", { network: networkName(row.network) })}
                htmlFor={id}
                className="min-w-0 flex-1"
              >
                {(a11y) => (
                  <Input
                    {...a11y}
                    value={row.value}
                    maxLength={300}
                    disabled={!canWrite}
                    inputMode={isUrl ? "url" : "text"}
                    placeholder={isUrl ? "https://" : "@usuario"}
                    onChange={(e) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, value: e.target.value } : r)))}
                  />
                )}
              </Field>
              {canWrite && !ALWAYS.includes(row.network) ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={t("business.socials.removeOne", { network: networkName(row.network) })}
                  onClick={() => setRows((rs) => rs.filter((_r, j) => j !== i))}
                >
                  <X aria-hidden="true" />
                </Button>
              ) : null}
            </div>
          );
        })}
        {canWrite ? (
          <div className="flex min-w-0 flex-wrap items-end gap-2">
            {free.length ? (
              <>
                <Field label={t("business.socials.addNetwork")} htmlFor={`${base}-add`}>
                  {(a11y) => (
                    <NativeSelect {...a11y} value={free.includes(adding) ? adding : free[0]} onChange={(e) => setAdding(e.target.value as Network)}>
                      {free.map((n) => (
                        <option key={n} value={n}>
                          {networkName(n)}
                        </option>
                      ))}
                    </NativeSelect>
                  )}
                </Field>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    const n: Network | undefined = free.includes(adding) ? adding : free[0];
                    if (!n) return;
                    setRows((rs) => [...rs, { key: `new-${n}-${rs.length}`, network: n, value: "" }]);
                  }}
                >
                  <Plus aria-hidden="true" />
                  {t("business.socials.add")}
                </Button>
              </>
            ) : null}
            <Button type="submit" disabled={pending} className="sm:ml-auto">
              {pending ? t("business.socials.saving") : t("business.socials.save")}
            </Button>
          </div>
        ) : null}
      </form>
    </section>
  );
}
