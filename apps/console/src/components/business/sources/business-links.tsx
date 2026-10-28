"use client";

import { Globe, Plus, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button, Field, NativeSelect } from "@nexus/ui";

import { putLinksAction } from "@/app/(console)/clients/[ref]/client-v2-actions";
import { BrandLogo, hasBrandLogo } from "@/components/brand-logo";
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

/**
 * El enlace del perfil de un usuario en cada red (Andrés, 2026-10-28: «Mi
 * Instagram es @Jhondoe» → https://www.instagram.com/jhondoe). Las mismas
 * plantillas que la API (`services/business/links.py`, `_PROFILE_URL`); LinkedIn
 * no tiene `@usuario` en la API, así que su enlace se arma aquí.
 */
const PROFILE: Record<Exclude<Network, "web">, (h: string) => string> = {
  instagram: (h) => `https://www.instagram.com/${h}`,
  facebook: (h) => `https://www.facebook.com/${h}`,
  tiktok: (h) => `https://www.tiktok.com/@${h}`,
  youtube: (h) => `https://www.youtube.com/@${h}`,
  x: (h) => `https://x.com/${h}`,
  threads: (h) => `https://www.threads.net/@${h}`,
  linkedin: (h) => `https://www.linkedin.com/company/${h}`,
};

export function profileUrl(network: Exclude<Network, "web">, handle: string): string {
  return PROFILE[network](handle);
}

/** Lo escrito → el usuario: sin espacios, sin «@», en minúsculas; un enlace pegado, su último tramo. */
export function handleOf(raw: string): string {
  let value = raw.trim();
  if (/^https?:\/\//i.test(value) || /^(www\.)?[a-z0-9-]+\.[a-z]{2,}\//i.test(value)) {
    const parts = value.replace(/[?#].*$/, "").replace(/\/+$/, "").split("/");
    value = parts[parts.length - 1] ?? "";
  }
  return value.replace(/^@+/, "").toLowerCase();
}

/** La API admite letras, números, puntos y guiones bajos (hasta 30); LinkedIn, también guiones. */
export function validHandle(network: Network, handle: string): boolean {
  return network === "linkedin" ? /^[a-z0-9._-]{1,100}$/.test(handle) : /^[a-z0-9._]{1,30}$/.test(handle);
}

/** De lo guardado a las filas: Instagram y Facebook siempre, primero; cada red, con su usuario. */
export function rowsFrom(links: readonly LinkItem[]): LinkRow[] {
  const rows: LinkRow[] = links.map((l) => ({
    key: l.id,
    network: l.network,
    value: l.network === "web" ? (l.url ?? "") : handleOf(l.handle ?? l.url ?? ""),
  }));
  const first = ALWAYS.map((n) => rows.find((r) => r.network === n) ?? { key: `new-${n}`, network: n, value: "" });
  return [...first, ...rows.filter((r) => !ALWAYS.includes(r.network))];
}

/** De las filas a lo que guarda la API: la web, su enlace; LinkedIn, el enlace armado; las demás, el usuario. */
export function linksFrom(rows: readonly LinkRow[]): { network: Network; url?: string; handle?: string }[] {
  return rows
    .filter((r) => r.value.trim())
    .map((r) => {
      if (r.network === "web") return { network: r.network, url: r.value.trim() };
      const handle = handleOf(r.value);
      return r.network === "linkedin" ? { network: r.network, url: profileUrl("linkedin", handle) } : { network: r.network, handle };
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
  bare = false,
}: {
  refId: string;
  links: readonly LinkItem[];
  revision: number;
  canWrite: boolean;
  /** Dentro de la tarjeta de Negocio, que ya pone el título. */
  bare?: boolean;
  save?: (body: { ref: string; revision: number; links: ReturnType<typeof linksFrom> }) => Promise<Result<{ links: LinkItem[]; revision: number }>>;
  onSaved?: (revision: number) => void;
}) {
  const t = useT();
  const [rows, setRows] = React.useState<LinkRow[]>(() => rowsFrom(links));
  const [rev, setRev] = React.useState(revision);
  const [adding, setAdding] = React.useState<Network>("tiktok");
  const [pending, startTransition] = React.useTransition();
  const [tried, setTried] = React.useState(false);
  const base = React.useId();
  const doSave = save ?? ((b) => putLinksAction(b));
  const networkName = (n: Network) => t(`business.links.network.${n}` as MessageKey);
  const free = OPTIONAL.filter((n) => !rows.some((r) => r.network === n));

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setTried(true);
    if (rows.some((r) => r.network !== "web" && r.value.trim() && !validHandle(r.network, handleOf(r.value)))) return;
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

  const Wrap = bare ? "div" : "section";
  return (
    <Wrap className="grid min-w-0 gap-4" aria-labelledby={bare ? undefined : `${base}-title`} data-slot="business-links">
      <div className="grid min-w-0 gap-1">
        {bare ? null : (
          <h2 id={`${base}-title`} className="text-base font-semibold text-balance">
            {t("business.socials.title")}
          </h2>
        )}
        <p className="text-sm text-muted-foreground text-pretty">{t("business.socials.intro")}</p>
      </div>
      <form onSubmit={submit} className="grid min-w-0 gap-3" noValidate>
        {rows.map((row, i) => {
          const id = `${base}-${row.key}`;
          const isWeb = row.network === "web";
          const handle = isWeb ? "" : handleOf(row.value);
          const bad = !isWeb && handle !== "" && !validHandle(row.network, handle);
          const shownBad = bad && tried;
          const url = !isWeb && handle && !bad ? profileUrl(row.network as Exclude<Network, "web">, handle) : null;
          return (
            <div key={row.key} className="grid min-w-0 gap-1">
              <div className="flex min-w-0 items-center gap-2">
                {/* Como el prototipo: el logo y el nombre de la red pegados al campo. */}
                <label
                  htmlFor={id}
                  className="flex h-9 min-w-0 flex-1 items-stretch overflow-hidden rounded-md border border-input bg-background focus-within:ring-2 focus-within:ring-ring"
                >
                  <span className="flex shrink-0 items-center gap-2 border-r border-border px-3 text-[13px] text-muted-foreground">
                    {hasBrandLogo(row.network) ? <BrandLogo brand={row.network} size="sm" /> : <Globe aria-hidden="true" className="size-4" />}
                    <span aria-hidden="true">{networkName(row.network)}</span>
                  </span>
                  <input
                    id={id}
                    aria-label={isWeb ? t("business.socials.url", { network: networkName(row.network) }) : t("business.socials.handle", { network: networkName(row.network) })}
                    value={row.value}
                    maxLength={300}
                    disabled={!canWrite}
                    inputMode={isWeb ? "url" : "text"}
                    autoCapitalize="none"
                    autoCorrect="off"
                    spellCheck={false}
                    aria-invalid={shownBad || undefined}
                    aria-describedby={shownBad ? `${id}-error` : url ? `${id}-url` : undefined}
                    placeholder={isWeb ? "https://negocio.com" : "@usuario"}
                    className="min-w-0 flex-1 bg-transparent px-3 text-sm outline-none placeholder:text-muted-foreground disabled:opacity-50"
                    onChange={(e) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, value: e.target.value } : r)))}
                  />
                </label>
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
              {shownBad ? (
                <p id={`${id}-error`} className="text-xs text-destructive">
                  {t("business.socials.error.handle")}
                </p>
              ) : url ? (
                <a id={`${id}-url`} href={url} target="_blank" rel="noreferrer" className="w-fit max-w-full truncate text-xs text-muted-foreground underline-offset-4 hover:underline">
                  {url}
                </a>
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
    </Wrap>
  );
}
