"use client";

import { AlertTriangle, BookOpenCheck, Globe } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Button, Card, CardContent, Skeleton } from "@nexus/ui";

import { getClientReadAction, startClientReadAction } from "@/app/(console)/clients/new-client-actions";
import { clientHref } from "@/components/shell/routes-v2";
import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { ClientRead, Network } from "@/lib/backend/clients-v2";

import { foundSummary, isLive, languageName, pollDelay, readView, type NetworkLine, type ReadView } from "./client-read-model";

type Failed = { ok: false; status: number; message: string; code?: string | null };
type Result<T> = { ok: true; data: T } | Failed;

export type ClientReadActions = {
  load: (body: { ref: string }) => Promise<Result<ClientRead>>;
  retry: (body: { ref: string }) => Promise<Result<{ job_id: string }>>;
};

const DEFAULT_ACTIONS: ClientReadActions = {
  load: (b) => getClientReadAction(b),
  retry: (b) => startClientReadAction(b),
};

/**
 * La tarjeta de lectura del Panel del cliente (spec 047, requisitos 5.5, 5.7 y
 * 14.7; enmienda del 2026-10-29, 59.4 y 59.7). La usa el Panel; mientras dura
 * la lectura dice qué se está leyendo, al terminar dice qué se leyó, qué se
 * encontró y cuánto falta revisar con «Revisar», y por red, cuál no deja leer
 * perfiles sin cuenta (sin contarla como fallo) y cuál falló y por qué. Si
 * falla entera, dice por qué con «Reintentar». El cliente se puede seguir
 * usando en todo momento: la tarjeta no bloquea nada.
 *
 * Consulta `GET /console/clients/{ref}/business/read` con la espera creciente
 * del contrato (1, 2, 4… hasta 10 s) mientras el trabajo sigue vivo, y deja de
 * hacerlo al terminar o al desmontarse. Sin web ni redes no pinta nada.
 */
export function ClientReadCard({
  refId,
  initial,
  canWrite = true,
  actions,
}: {
  refId: string;
  /** Lo que el Panel ya leyó del servidor; sin ello, la tarjeta lo pide. */
  initial?: ClientRead | null;
  canWrite?: boolean;
  actions?: Partial<ClientReadActions>;
}) {
  const t = useT();
  const locale = useLocale();
  const act = React.useMemo(() => ({ ...DEFAULT_ACTIONS, ...actions }), [actions]);
  const [data, setData] = React.useState<ClientRead | null | undefined>(initial);
  const [failed, setFailed] = React.useState(false);
  const [retrying, setRetrying] = React.useState(false);
  const [round, setRound] = React.useState(0);
  const view: ReadView = readView(data ?? null);
  const live = data === undefined || isLive(view);

  React.useEffect(() => {
    if (!live && round === 0) return;
    let alive = true;
    let attempt = 0;
    let timer: number | undefined;
    const tick = async () => {
      const res = await act.load({ ref: refId }).catch(() => null);
      if (!alive) return;
      if (!res || !res.ok) {
        // Un tropiezo al consultar no es el fallo de la lectura: se dice y se
        // vuelve a mirar con la misma espera.
        setFailed(true);
        timer = window.setTimeout(tick, pollDelay(attempt++));
        return;
      }
      setFailed(false);
      setData(res.data);
      if (isLive(readView(res.data))) {
        timer = window.setTimeout(tick, pollDelay(attempt++));
      }
    };
    // Con lo del servidor ya pintado, la primera consulta espera su turno.
    timer = window.setTimeout(tick, data === undefined ? 0 : pollDelay(attempt++));
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
    // Una consulta por ronda: la vuelve a lanzar «Reintentar».
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refId, round, act]);

  async function retry() {
    setRetrying(true);
    const res = await act.retry({ ref: refId }).catch(() => null);
    setRetrying(false);
    if (!res || !res.ok) {
      setFailed(true);
      return;
    }
    // La tarjeta pasa a «leyendo» al momento; la consulta confirma.
    setData((prev) =>
      prev?.job
        ? { ...prev, job: { ...prev.job, job_id: res.data.job_id, status: "queued", error_code: null, result: null, finished_at: null } }
        : undefined,
    );
    setRound((r) => r + 1);
  }

  if (failed && (data === undefined || data === null)) {
    return (
      <ReadFrame tone="warning" icon={<AlertTriangle aria-hidden="true" className="text-warning" />}>
        <p className="text-pretty">{t("business.read.statusError")}</p>
        <Button type="button" variant="outline" size="sm" onClick={() => setRound((r) => r + 1)}>
          {t("business.read.retry")}
        </Button>
      </ReadFrame>
    );
  }
  if (data === undefined) {
    return (
      <Card data-slot="client-read-card" role="status" aria-busy="true" aria-label={t("business.read.loading")}>
        <CardContent className="grid gap-2 py-4">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-1/2" />
        </CardContent>
      </Card>
    );
  }
  if (view.kind === "none") return null;

  const site = view.site ?? t("business.read.socials");
  const networkLabel = (n: Network) => t(`business.links.network.${n}` as MessageKey);

  if (view.kind === "reading") {
    return (
      <ReadFrame icon={<Globe aria-hidden="true" className="text-status-info-text" />} live>
        <p className="text-pretty">{view.site ? t("business.read.reading", { site: view.site }) : t("business.read.readingSocial")}</p>
        {view.pages > 0 ? <p className="text-xs text-muted-foreground tabular-nums">{t("business.read.pages", { n: view.pages })}</p> : null}
        {/* Una consulta que falla no es el fallo de la lectura: se dice y se sigue mirando. */}
        {failed ? <p className="text-xs text-pretty text-muted-foreground">{t("business.read.statusError")}</p> : null}
      </ReadFrame>
    );
  }

  if (view.kind === "failed") {
    const reason = t(`business.read.reason.${view.reason}` as MessageKey);
    return (
      <ReadFrame tone="warning" icon={<AlertTriangle aria-hidden="true" className="text-warning" />} title={t("business.read.title.done")} live>
        <p className="text-pretty">{t("business.read.failed", { site, reason })}</p>
        <NetworkNotes lines={view.networks} only={["blocked_by_network"]} />
        {failed ? <p className="text-xs text-muted-foreground">{t("business.read.statusError")}</p> : null}
        {canWrite && view.reason !== "nothing_to_read" ? (
          <Button type="button" variant="outline" size="sm" onClick={retry} disabled={retrying}>
            {retrying ? t("business.read.retrying") : t("business.read.retry")}
          </Button>
        ) : null}
      </ReadFrame>
    );
  }

  const summary = foundSummary(view.result.found, t);
  const alsoRead = view.networks.filter((n) => n.status === "read" && n.network !== "web").map((n) => networkLabel(n.network));
  return (
    <ReadFrame icon={<BookOpenCheck aria-hidden="true" className="text-status-positive-text" />} title={t("business.read.title.done")} live>
      <p className="text-pretty">{summary ? t("business.read.done", { site, found: summary }) : t("business.read.doneNothing", { site })}</p>
      {alsoRead.length ? <p className="text-xs text-pretty text-muted-foreground">{t("business.read.network.read", { networks: alsoRead.join(", ") })}</p> : null}
      {view.structured ? <p className="text-xs text-pretty text-muted-foreground">{t("business.read.structured")}</p> : null}
      {view.result.translated_from ? (
        <p className="text-xs text-muted-foreground">{t("business.read.translated", { language: languageName(locale, view.result.translated_from) })}</p>
      ) : null}
      <NetworkNotes lines={view.networks} only={["blocked_by_network", "failed"]} />
      {view.toReview > 0 ? (
        <p className="text-sm text-pretty" data-slot="client-read-review">
          {view.toReview === 1 ? t("business.read.toReview.one") : t("business.read.toReview.other", { n: view.toReview })}
        </p>
      ) : null}
      {summary || view.toReview > 0 ? (
        <Button variant="outline" size="sm" nativeButton={false} render={<Link href={clientHref(refId, "business")} />}>
          {t("business.read.review")}
        </Button>
      ) : null}
    </ReadFrame>
  );
}

/**
 * Las redes que no se leyeron, una frase por red (59.4): la que no deja leer
 * perfiles sin cuenta lo dice sin tono de aviso (no es un fallo de la lectura);
 * la que falló dice por qué.
 */
function NetworkNotes({ lines, only }: { lines: NetworkLine[]; only: NetworkLine["status"][] }) {
  const t = useT();
  const shown = lines.filter((n) => only.includes(n.status));
  if (!shown.length) return null;
  const label = (n: NetworkLine) => t(`business.links.network.${n.network}` as MessageKey);
  return (
    <ul className="grid min-w-0 gap-1 text-xs text-muted-foreground" data-slot="client-read-networks">
      {shown.map((n) => (
        <li key={`${n.network}-${n.status}`} className="min-w-0 text-pretty break-words" data-status={n.status}>
          {n.status === "blocked_by_network"
            ? t("business.read.network.blocked", { network: label(n) })
            : t("business.read.network.failed", { network: label(n), reason: t(`business.read.reason.${n.reason ?? "other"}` as MessageKey) })}
        </li>
      ))}
    </ul>
  );
}

function ReadFrame({
  icon,
  tone,
  live,
  title,
  children,
}: {
  icon: React.ReactNode;
  tone?: "warning";
  live?: boolean;
  /** Mientras se lee, «Completando la ficha»; al terminar, «Lo que leímos». */
  title?: string;
  children: React.ReactNode;
}) {
  const t = useT();
  return (
    <Card data-slot="client-read-card" data-tone={tone ?? "info"}>
      <CardContent className="flex min-w-0 items-start gap-3 py-4">
        <span className="mt-1 shrink-0">{icon}</span>
        <div className="grid min-w-0 flex-1 gap-2" role={live ? "status" : undefined}>
          <h2 className="text-sm font-medium text-balance">{title ?? t("business.read.title")}</h2>
          {children}
        </div>
      </CardContent>
    </Card>
  );
}
