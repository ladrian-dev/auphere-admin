"use client";

import { AlertTriangle, Ban, CheckCircle2, ChevronDown, MessageCircle, Plus, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, Callout, Field, Input, Label, NativeSelect, StatusBadge, Textarea, formatDateTime } from "@nexus/ui";

import {
  channelHistoryAction,
  channelPageAction,
  instagramCommentsAction,
  saveChannelConfigAction,
  undoChannelConfigAction,
} from "@/app/(console)/clients/[ref]/agents/channel-actions";
import { BrandLogo, hasBrandLogo } from "@/components/brand-logo";
import { BalanceButton, type BalanceMode } from "@/components/money/balance-button";
import { CrumbName, openChannelCrumb } from "@/components/shell/crumb-names";
import { agentHref } from "@/components/shell/routes-v2";
import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { EscalationTrigger } from "@/lib/backend/builder-types";
import type { AudienceMode, ChannelChange, ChannelConfigIn, ChannelPage, InstagramComments, Recipient } from "@/lib/backend/channel-config-types";

import { triggerText } from "./block-view";
import type { Result } from "./builder-model";
import { ChannelAccount, hasAccountFacts } from "./channel-account";
import { ChannelCatalogSection } from "./channel-catalog";
import { ChannelTemplates } from "./channel-templates";
import { InstagramCommentsSection } from "./channel-comments";
import { ChannelMenu, UnlinkPending, type ChannelMenuActions } from "./channel-menu";
import {
  MAX_RECIPIENTS,
  WAIT_MESSAGE_MAX,
  addNumber,
  agentChannelsTabHref,
  channelHref,
  channelStateText,
  checkText,
  conflictSections,
  draftFromPage,
  draftProblem,
  emptyRecipient,
  fixLink,
  historyLines,
  isDirty,
  saveErrorOf,
  toPayload,
  type FixTargets,
  type SaveError,
} from "./channel-model";
import { formatClock } from "./knowledge-model";
import { visibleTone } from "./life-model";
import { cleanActor, undoOpen } from "./quality-model";

type Ids = { ref: string; channel: string };
export type ChannelPageActions = {
  save: (body: Ids & { revision: number; config: ChannelConfigIn }) => Promise<Result<ChannelPage>>;
  undo: (body: Ids) => Promise<Result<ChannelPage>>;
  reload: (body: Ids) => Promise<Result<ChannelPage>>;
  history: (body: Ids) => Promise<Result<ChannelChange[]>>;
  /** Spec 049: los comentarios de una cuenta de Instagram (guarda al pulsar). */
  comments?: (body: Ids & InstagramComments) => Promise<Result<ChannelPage>>;
  menu?: ChannelMenuActions;
};

export const CHANNEL_PAGE_ACTIONS: ChannelPageActions = {
  save: (body) => saveChannelConfigAction(body),
  undo: (body) => undoChannelConfigAction(body),
  reload: (body) => channelPageAction(body),
  history: (body) => channelHistoryAction(body),
  comments: (body) => instagramCommentsAction(body),
};

/** El nombre de cada canal en la cabecera («Instagram · canal de Ava»). */
const CHANNEL_NAMES: Record<string, MessageKey> = {
  whatsapp: "builder.channels.whatsapp",
  instagram: "builder.channels.instagram",
  messenger: "builder.channels.messenger",
};

/** El índice de la configuración (prototipo §8.1): «Excepciones» solo con «A todos». */
const NAV = [
  { id: "canal-audiencia", label: "builder.channel.audience.title" },
  { id: "canal-excepciones", label: "builder.channel.exceptions.title" },
  { id: "canal-escalado", label: "builder.channel.escalation.title" },
] as const satisfies readonly { id: string; label: MessageKey }[];

/** Dos modos, como el prototipo: «Sin configurar» no se elige, es de dónde se parte (32.9). */
const MODES: readonly AudienceMode[] = ["team_only", "everyone"];

type Conflict = { current: number; changes: unknown };

/**
 * La configuración de un canal (spec 047, historia 11; requisitos 32 y 33;
 * T115): a quién responde (con sus números de prueba), excepciones, escalado
 * a personas (hasta 10, con los disparadores del agente en solo lectura y de
 * qué número saldrán los avisos), mensaje de espera y comprobaciones, con su
 * barra de guardar y su historial.
 *
 * Como el prototipo aprobado (`agente.md` §8, hueco H5; requisito 63.1), se
 * pinta dentro del agente, en su pestaña Canales (`?canal=`), con la cabecera
 * y las pestañas del agente arriba: el índice a la izquierda (200 px; una fila
 * por debajo de 860 px), la cabecera del canal con su logo y «WhatsApp ·
 * {método} · canal de {agente}», dos modos, «Excepciones» solo con «A todos»,
 * el escalado en filas de una línea, y «Mensaje de espera» e «Historial» en
 * «Más ajustes». La barra de vidrio ofrece, con el canal sin configurar,
 * «Activar solo para mi equipo», «Activar para todos» y «Decidir luego»; y,
 * configurado, «Guardar» y «Descartar» cuando hay cambios.
 *
 * Guardar manda la configuración entera con la revisión que leyó la pantalla
 * (`If-Match`). Si otra persona guardó antes, se dice qué cambió y se elige:
 * guardar lo mío encima o ver lo de ahora. Lo guardado vale desde el siguiente
 * mensaje y se puede deshacer durante 10 minutos. Cuando «A todos» no se puede,
 * se dice por qué con su arreglo («Guardar el agente», «Asignar saldo»).
 *
 * Quien solo lee lo ve todo como texto, sin campos ni botones (§V).
 */
export function ChannelConfigPage({
  refId,
  agentId,
  page: initialPage,
  history: initialHistory,
  canWrite,
  balanceHref = null,
  balance = null,
  onClose,
  onChanged,
  actions = CHANNEL_PAGE_ACTIONS,
}: {
  refId: string;
  /** El agente de la URL; si el canal tiene otro, manda el del canal. */
  agentId: string;
  page: ChannelPage;
  history: ChannelChange[] | null;
  canWrite: boolean;
  /** Dónde se asigna saldo a este cliente, si esta persona puede; si no, solo se dice. */
  balanceHref?: string | null;
  /** Spec 047 (45.1): «Asignar saldo» —o «Pedir saldo»— se abre aquí mismo, sin cambiar de pantalla. Manda sobre `balanceHref`. */
  balance?: ChannelBalance | null;
  /** «Decidir luego»: vuelve a la lista de canales del agente. Sin él, se navega a ella. */
  onClose?: () => void;
  /** El canal cambió (guardado, deshecho, en pausa): la lista del agente lo refleja. */
  onChanged?: (page: ChannelPage) => void;
  actions?: ChannelPageActions;
}) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const [page, setPageState] = React.useState(initialPage);
  const [saved, setSaved] = React.useState(() => draftFromPage(initialPage));
  const [draft, setDraft] = React.useState(() => draftFromPage(initialPage));
  const [history, setHistory] = React.useState(initialHistory);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<SaveError | null>(null);
  const [conflict, setConflict] = React.useState<Conflict | null>(null);
  const [unlinkPending, setUnlinkPending] = React.useState(false);
  const [more, setMore] = React.useState(false);
  const moreId = React.useId();
  const ids = { ref: refId, channel: page.id };
  const owner = page.agent?.id ?? agentId;
  const writable = canWrite && page.allowed.includes("configure");
  // 32.9: un canal sin configurar no responde todavía; la barra ofrece activarlo.
  const unconfigured = saved.audience.mode === "unset";
  const dirty = writable && isDirty(draft, saved);
  const canUndo = writable && undoOpen(page.undo_until);
  const everyone = draft.audience.mode === "everyone";
  // «Solo mi equipo» y «Excepciones» son teléfonos: solo casan en WhatsApp.
  const phones = page.type === "whatsapp";
  const targets: FixTargets = {
    agent: agentHref(refId, owner),
    tests: `${agentHref(refId, owner)}#agente-pruebas`,
    balance: balanceHref,
    recipients: "#canal-escalado",
  };

  function setPage(next: ChannelPage) {
    setPageState(next);
    onChanged?.(next);
  }

  function adopt(next: ChannelPage) {
    setPage(next);
    const fresh = draftFromPage(next);
    setSaved(fresh);
    setDraft(fresh);
    setError(null);
    setConflict(null);
  }

  async function refreshHistory() {
    const res = await actions.history(ids);
    if (res.ok) setHistory(res.data);
  }

  function close() {
    if (onClose) onClose();
    else router.push(agentChannelsTabHref(refId, owner));
  }

  /** Guarda lo escrito; `mode` lo cambia antes («Activar solo para mi equipo», «Activar para todos»). */
  async function save(revision: number = page.revision, mode?: AudienceMode) {
    const next = mode ? { ...draft, audience: { ...draft.audience, mode } } : draft;
    if (mode) setDraft(next);
    const problem = draftProblem(t, next);
    if (problem) {
      if (problem.section === "wait") setMore(true);
      setError({ section: problem.section, text: problem.text, fix: null });
      return;
    }
    setBusy(true);
    setError(null);
    const res = await actions.save({ ...ids, revision, config: toPayload(next) });
    setBusy(false);
    if (res.ok) {
      adopt(res.data);
      toast.success(savedText(t, res.data, page.agent?.name ?? null));
      void refreshHistory();
      return;
    }
    if (res.status === 412 && res.code === "revision_conflict") {
      const current = Number(res.info?.current);
      setConflict({ current: Number.isFinite(current) ? current : page.revision, changes: res.info?.changes });
      return;
    }
    const failure = saveErrorOf(t, res);
    if (failure.section === "wait") setMore(true);
    setError(failure);
  }

  async function theirs() {
    setBusy(true);
    const res = await actions.reload(ids);
    setBusy(false);
    if (!res.ok) return void toast.error(t("builder.channel.error"));
    adopt(res.data);
    void refreshHistory();
  }

  async function undo() {
    setBusy(true);
    const res = await actions.undo(ids);
    setBusy(false);
    if (res.ok) {
      adopt(res.data);
      toast.success(t("builder.channel.undone"));
      void refreshHistory();
      return;
    }
    toast.error(res.code === "undo_window_closed" ? t("builder.channel.undo.closed") : t("builder.channel.error"));
    if (res.code === "undo_window_closed") {
      const fresh = await actions.reload(ids);
      if (fresh.ok) setPage(fresh.data);
    }
  }

  const set = (fn: (d: ChannelConfigIn) => ChannelConfigIn) => {
    setDraft((d) => fn(d));
    setError(null);
  };
  const errorIn = (section: SaveError["section"]) => (error && error.section === section ? error : null);
  const fix = error ? fixLink(error.fix, targets) : null;
  const disconnected = page.status === "disconnected";
  const account = hasAccountFacts(t, locale, page.whatsapp) ? page.whatsapp : null;
  const method = page.method === "coexistence" || page.method === "cloud_api" ? t(`channels.proto.connect.${page.method}` as MessageKey) : null;
  const headLine = [
    page.type in CHANNEL_NAMES ? t(CHANNEL_NAMES[page.type]!) : page.type,
    method,
    page.agent ? t("builder.channel.head.of", { name: page.agent.name }) : t("builder.channel.page.noAgent"),
  ].filter(Boolean);

  return (
    <div className="grid min-w-0 gap-4" data-slot="channel-page">
      {/* La miga «Canal {número}» mientras la configuración está abierta (63.1). */}
      <CrumbName id={openChannelCrumb(owner)} label={page.identifier} transient />
      <div className="grid min-w-0 gap-6 min-[860px]:grid-cols-[calc(var(--spacing)*50)_minmax(0,1fr)]">
        <nav aria-label={t("builder.channel.page.sections")} className="grid min-w-0 content-start gap-3 min-[860px]:sticky min-[860px]:top-24 min-[860px]:self-start">
          <ul className="flex min-w-0 flex-wrap gap-1 min-[860px]:grid">
            {[
              ...NAV.filter((s) => s.id !== "canal-excepciones" || (everyone && phones)),
              // Spec 050 (4.1): la cuenta en Meta, cuando Meta dice algo de ella.
              ...(account ? [{ id: "canal-cuenta", label: "builder.channel.account.title" as MessageKey }] : []),
              ...(page.instagram_comments ? [{ id: "canal-comentarios", label: "builder.channel.comments.title" as MessageKey }] : []),
              ...(page.catalog_state ? [{ id: "canal-catalogo", label: "ch.catalog" as MessageKey }] : []),
              ...(page.type === "whatsapp" && !disconnected ? [{ id: "canal-plantillas", label: "tpl.title" as MessageKey }] : []),
            ].map((s) => (
              <li key={s.id} className="min-w-0">
                <a
                  href={`#${s.id}`}
                  className="inline-flex min-h-9 w-full items-center rounded-md px-3 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring motion-reduce:transition-none"
                >
                  {t(s.label)}
                </a>
              </li>
            ))}
          </ul>
          <p className="text-xs text-pretty text-muted-foreground">{t("builder.channel.page.note")}</p>
        </nav>

        <div className="grid min-w-0 gap-4">
          <header className="flex min-w-0 flex-wrap items-center gap-4" data-slot="channel-head">
            {hasBrandLogo(page.type) ? <BrandLogo brand={page.type} size="lg" /> : <MessageCircle aria-hidden="true" className="size-10 shrink-0 text-muted-foreground" />}
            <div className="grid min-w-0 flex-1 basis-48 gap-1">
              <h2 className="min-w-0 text-xl font-semibold tracking-tight text-balance break-words tabular-nums">{page.identifier}</h2>
              <p className="min-w-0 text-sm text-pretty text-muted-foreground">{headLine.join(" · ")}</p>
            </div>
            <StatusBadge tone={visibleTone(page.visible_state)} data-slot="channel-state">
              {channelStateText(t, page.visible_state)}
            </StatusBadge>
            <ChannelMenu
              refId={refId}
              agentId={owner}
              channel={page}
              here
              onChanged={setPage}
              onMoved={(_next, to) => router.replace(channelHref(refId, to.id, page.id))}
              onDisconnected={(pending) => {
                setUnlinkPending(pending.length > 0);
                void actions.reload(ids).then((res) => {
                  if (res.ok) adopt(res.data);
                });
              }}
              actions={actions.menu}
            />
          </header>
          {unlinkPending ? (
            <UnlinkPending
              refId={refId}
              channelId={page.id}
              number={page.identifier}
              canWrite={canWrite}
              onDone={() => setUnlinkPending(false)}
              disconnect={actions.menu?.disconnect}
            />
          ) : null}
          {disconnected ? <Callout tone="info">{t("builder.channel.page.disconnected")}</Callout> : null}
          {!canWrite ? <p className="text-sm text-muted-foreground">{t("builder.channel.page.readonly")}</p> : null}

          <form
            noValidate
            className="grid min-w-0 gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (dirty && !unconfigured) void save();
            }}
            data-slot="channel-config"
          >
            <PageSection id="canal-audiencia" title={t("builder.channel.audience.title")} intro={t("builder.channel.audience.intro")}>
              <AudienceSection
                draft={draft}
                writable={writable}
                adminOnly={page.admin_only_template}
                phones={phones}
                onMode={(mode) => set((d) => ({ ...d, audience: { ...d.audience, mode } }))}
                onTests={(list) => set((d) => ({ ...d, audience: { ...d.audience, test_numbers: list } }))}
              />
              <InlineError error={errorIn("audience")} targets={targets} balance={balance} refId={refId} />
            </PageSection>

            {everyone && phones ? (
              <PageSection id="canal-excepciones" title={t("builder.channel.exceptions.title")} intro={t("builder.channel.exceptions.intro")}>
                <NumberList
                  label={t("builder.channel.exceptions.title")}
                  numbers={draft.audience.exceptions}
                  writable={writable}
                  empty={t("builder.channel.exceptions.empty")}
                  onChange={(list) => set((d) => ({ ...d, audience: { ...d.audience, exceptions: list } }))}
                />
              </PageSection>
            ) : null}

            <PageSection id="canal-escalado" title={t("builder.channel.escalation.title")} intro={t("builder.channel.escalation.intro")}>
              <EscalationSection
                draft={draft}
                writable={writable}
                notifyFrom={page.config.notify_from}
                onRecipients={(recipients) => set((d) => ({ ...d, escalation: { ...d.escalation, recipients } }))}
                onSummary={(summary) => set((d) => ({ ...d, escalation: { ...d.escalation, summary } }))}
              />
              <InlineError error={errorIn("escalation")} targets={targets} balance={balance} refId={refId} />
              <Triggers triggers={page.triggers} editHref={`${agentHref(refId, owner)}#bloque-escalation`} />
            </PageSection>

            <PageSection id="canal-comprobaciones" title={t("builder.channel.checks.title")} intro={t("builder.channel.checks.intro")}>
              <ul className="grid min-w-0 gap-2" aria-label={t("builder.channel.checks.title")}>
                {page.checks.map((check) => {
                  const inPlace = !check.ok && check.fix === "assign_balance" && balance;
                  const link = check.ok || inPlace ? null : fixLink(check.fix, targets);
                  const Icon = check.ok ? CheckCircle2 : check.level === "block" ? Ban : AlertTriangle;
                  const tone = check.ok ? "text-status-positive-text" : check.level === "block" ? "text-destructive" : "text-status-warning-text";
                  const level = check.ok ? "builder.channel.check.ok" : check.level === "block" ? "builder.channel.check.block" : "builder.channel.check.warn";
                  return (
                    <li key={check.code} className="flex min-w-0 items-start gap-2 text-sm" data-check={check.code} data-ok={check.ok}>
                      <Icon aria-hidden="true" className={`mt-1 size-4 shrink-0 ${tone}`} />
                      <span className="grid min-w-0 gap-1">
                        <span className="text-pretty">
                          <span className="sr-only">{t(level as MessageKey)}: </span>
                          {checkText(t, check)}
                        </span>
                        {inPlace ? (
                          <BalanceFix refId={refId} balance={balance} />
                        ) : link ? (
                          <Link href={link.href} className="w-fit font-medium text-primary-text underline-offset-4 hover:underline">
                            {t(link.label)}
                          </Link>
                        ) : !check.ok && check.fix === "assign_balance" ? (
                          <span className="text-xs text-pretty text-muted-foreground">{t("builder.channel.check.bag_empty.ask")}</span>
                        ) : null}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </PageSection>

            {account ? (
              <PageSection id="canal-cuenta" title={t("builder.channel.account.title")} intro={t("builder.channel.account.intro")}>
                <ChannelAccount account={account} />
              </PageSection>
            ) : null}

            {page.catalog_state ? (
              <PageSection id="canal-catalogo" title={t("ch.catalog")} intro={t("builder.channel.catalog.intro")}>
                <ChannelCatalogSection
                  refId={refId}
                  page={page}
                  canWrite={canWrite && !disconnected}
                  onChanged={() =>
                    void actions.reload(ids).then((res) => {
                      if (res.ok) setPage(res.data);
                    })
                  }
                />
              </PageSection>
            ) : null}

            {page.type === "whatsapp" && !disconnected ? <ChannelTemplates refId={refId} manage={canWrite} /> : null}

            {page.instagram_comments ? (
              <PageSection id="canal-comentarios" title={t("builder.channel.comments.title")} intro={t("builder.channel.comments.intro")}>
                <InstagramCommentsSection
                  comments={page.instagram_comments}
                  canWrite={canWrite && !disconnected && Boolean(actions.comments)}
                  onSave={(next) => actions.comments!({ ...ids, ...next })}
                  onSaved={setPage}
                />
              </PageSection>
            ) : null}

            {/* «Más ajustes» (H5): lo que el prototipo no enseña, plegado. */}
            <div className="grid min-w-0 gap-4" data-slot="channel-more">
              <button
                type="button"
                aria-expanded={more}
                aria-controls={moreId}
                onClick={() => setMore((v) => !v)}
                className="flex w-full min-w-0 scroll-mb-48 cursor-pointer items-center justify-between gap-3 rounded-lg border border-border bg-card px-4 py-3 text-left text-sm font-medium transition-colors hover:bg-muted/60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring motion-reduce:transition-none sm:px-5"
              >
                <span className="grid min-w-0 gap-1">
                  {t("builder.channel.more")}
                  <span className="text-xs font-normal text-pretty text-muted-foreground">{t("builder.channel.more.hint")}</span>
                </span>
                <ChevronDown aria-hidden="true" className={`size-4 shrink-0 text-muted-foreground transition-transform motion-reduce:transition-none ${more ? "rotate-180" : ""}`} />
              </button>
              <div id={moreId} hidden={!more} className="grid min-w-0 gap-4">
                <PageSection id="canal-espera" title={t("builder.channel.wait.title")} intro={t("builder.channel.wait.intro")}>
                  {writable ? (
                    <Field label={t("builder.channel.wait.field")} hint={t("builder.channel.wait.hint")} error={errorIn("wait")?.text}>
                      {(a11y) => (
                        <Textarea
                          {...a11y}
                          value={draft.wait_message ?? ""}
                          rows={3}
                          maxLength={WAIT_MESSAGE_MAX}
                          onChange={(e) => set((d) => ({ ...d, wait_message: e.target.value }))}
                        />
                      )}
                    </Field>
                  ) : (
                    <p className="text-sm text-pretty break-words whitespace-pre-line">{draft.wait_message?.trim() ? draft.wait_message : t("builder.channel.wait.none")}</p>
                  )}
                </PageSection>
                <PageSection id="canal-historial" title={t("builder.channel.history.title")}>
                  <History history={history} />
                </PageSection>
              </div>
            </div>

            {writable && conflict ? (
              <Callout
                tone="warning"
                title={t("builder.channel.conflict.title")}
                action={
                  <span className="flex flex-wrap gap-2">
                    <Button type="button" size="sm" onClick={() => void save(conflict.current)} loading={busy}>
                      {t("builder.channel.conflict.mine")}
                    </Button>
                    <Button type="button" size="sm" variant="outline" onClick={() => void theirs()} disabled={busy}>
                      {t("builder.channel.conflict.theirs")}
                    </Button>
                  </span>
                }
              >
                {t("builder.channel.conflict.body", { sections: conflictSections(t, conflict.changes) })}
              </Callout>
            ) : null}
            {writable && error && error.section === "general" ? (
              <p role="alert" className="text-sm text-pretty text-destructive">
                {error.text}
                {error.fix === "assign_balance" && balance ? (
                  <>
                    {" "}
                    <BalanceFix refId={refId} balance={balance} />
                  </>
                ) : fix ? (
                  <>
                    {" "}
                    <Link href={fix.href} className="font-medium underline underline-offset-4">
                      {t(fix.label)}
                    </Link>
                  </>
                ) : null}
              </p>
            ) : null}

            {writable ? (
              // La barra de vidrio (prototipo §8, la misma de §4.5): el estado a la izquierda, los botones píldora a la derecha.
              <div
                role="region"
                aria-label={t("builder.channel.bar.label")}
                className="glass sticky bottom-4 z-(--z-sticky) flex min-w-0 flex-wrap items-center justify-between gap-2 rounded-xl p-3 ring-1 ring-foreground/10 min-[560px]:rounded-full min-[560px]:py-2 min-[560px]:pr-2 min-[560px]:pl-4"
                data-slot="channel-save-bar"
              >
                <p className="min-w-0 text-sm text-pretty text-muted-foreground" aria-live="polite">
                  {unconfigured ? t("builder.channel.bar.unset") : dirty ? t("builder.channel.bar.dirty") : t("builder.channel.bar.clean")}
                </p>
                <div className="flex min-w-0 flex-wrap items-center justify-end gap-2 max-[559px]:w-full">
                  {unconfigured ? (
                    <>
                      <Button type="button" size="sm" variant="ghost" className="rounded-full" onClick={close} disabled={busy}>
                        {t("builder.channel.bar.later")}
                      </Button>
                      {phones ? (
                        <Button
                          type="button"
                          size="sm"
                          variant={everyone ? "outline" : "default"}
                          className="rounded-full"
                          loading={busy && !everyone}
                          disabled={busy}
                          onClick={() => void save(page.revision, "team_only")}
                        >
                          {t("builder.channel.bar.activateTeam")}
                        </Button>
                      ) : null}
                      {page.admin_only_template ? null : (
                        <Button
                          type="button"
                          size="sm"
                          variant={everyone || !phones ? "default" : "outline"}
                          className="rounded-full"
                          loading={busy && everyone}
                          disabled={busy}
                          onClick={() => void save(page.revision, "everyone")}
                        >
                          {t("builder.channel.bar.activateAll")}
                        </Button>
                      )}
                    </>
                  ) : (
                    <>
                      {canUndo && !dirty ? (
                        <>
                          <span className="text-xs text-muted-foreground">{t("builder.channel.undo.until", { time: formatClock(page.undo_until, locale) })}</span>
                          <Button type="button" size="sm" variant="outline" className="rounded-full" onClick={() => void undo()} disabled={busy}>
                            {t("builder.channel.undo")}
                          </Button>
                        </>
                      ) : null}
                      {dirty ? (
                        <>
                          <Button type="button" size="sm" variant="ghost" className="rounded-full" onClick={() => adopt(page)} disabled={busy}>
                            {t("builder.channel.bar.discard")}
                          </Button>
                          <Button type="submit" size="sm" className="rounded-full" loading={busy}>
                            {t("builder.channel.bar.save")}
                          </Button>
                        </>
                      ) : null}
                    </>
                  )}
                </div>
              </div>
            ) : null}
          </form>
        </div>
      </div>
    </div>
  );
}

/** «Recepción responde por +34 … solo a tu equipo.» (prototipo §8), según lo guardado. */
function savedText(t: ReturnType<typeof useT>, page: ChannelPage, agent: string | null): string {
  const mode = page.config.audience.mode;
  if (mode === "unset") return t("builder.channel.saved");
  const name = agent ?? t("builder.channel.saved.agent");
  return t(mode === "everyone" ? "builder.channel.saved.everyone" : "builder.channel.saved.team", { agent: name, number: page.identifier });
}

/**
 * Lo que recibe el foco deja sitio debajo para la barra de vidrio, que flota
 * pegada abajo: el teclado nunca deja un campo tapado por ella (WCAG 2.4.11).
 * En el móvil la barra ocupa dos o tres filas; 192 px la cubren con margen.
 */
const CLEAR_OF_BAR = "[&_:is(a,button,input,select,textarea,summary)]:scroll-mb-48";

function PageSection({ id, title, intro, children }: { id: string; title: string; intro?: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className={`grid min-w-0 scroll-mt-24 gap-3 rounded-md border border-border bg-card p-4 sm:p-6 ${CLEAR_OF_BAR}`}>
      <div className="grid min-w-0 gap-1">
        <h2 id={`${id}-title`} className="text-base font-semibold text-balance">
          {title}
        </h2>
        {intro ? <p className="max-w-prose text-sm text-pretty text-muted-foreground">{intro}</p> : null}
      </div>
      {children}
    </section>
  );
}

/** Un error de la API en su sección, con su arreglo si la persona puede hacerlo aquí. */
/** Lo que el canal sabe para abrir «Asignar saldo» o «Pedir saldo» en el sitio. */
export type ChannelBalance = { name: string; mode: BalanceMode };

function BalanceFix({ refId, balance }: { refId: string; balance: ChannelBalance }) {
  return <BalanceButton refId={refId} name={balance.name} mode={balance.mode} variant="link" size="xs" className="h-auto w-fit p-0" />;
}

function InlineError({ error, targets, balance, refId }: { error: SaveError | null; targets: FixTargets; balance: ChannelBalance | null; refId: string }) {
  const t = useT();
  if (!error) return null;
  if (error.fix === "assign_balance" && balance) {
    return (
      <div role="alert" className="grid gap-1 text-sm text-pretty text-destructive" data-slot="channel-error">
        <span>{error.text}</span>
        <BalanceFix refId={refId} balance={balance} />
      </div>
    );
  }
  const link = fixLink(error.fix, targets);
  return (
    <p role="alert" className="text-sm text-pretty text-destructive" data-slot="channel-error">
      {error.text}
      {link ? (
        <>
          {" "}
          <Link href={link.href} className="font-medium underline underline-offset-4">
            {t(link.label)}
          </Link>
        </>
      ) : error.fix === "assign_balance" ? (
        <> {t("builder.channel.check.bag_empty.ask")}</>
      ) : null}
    </p>
  );
}

function AudienceSection({
  draft,
  writable,
  adminOnly,
  phones,
  onMode,
  onTests,
}: {
  draft: ChannelConfigIn;
  writable: boolean;
  adminOnly: boolean;
  /** WhatsApp: «Solo mi equipo» con sus números de prueba. Instagram y Messenger no tienen teléfono. */
  phones: boolean;
  onMode: (mode: AudienceMode) => void;
  onTests: (list: string[]) => void;
}) {
  const t = useT();
  const base = React.useId();
  const mode = draft.audience.mode;
  // 32.5: con plantilla de solo administradores, «A todos» no se ofrece, y se dice por qué.
  const modes = MODES.filter((m) => !(adminOnly && m === "everyone" && mode !== "everyone") && !(m === "team_only" && !phones && mode !== "team_only"));
  return (
    <div className="grid min-w-0 gap-4">
      {writable ? (
        // «¿A quién responde?» (prototipo §8): dos opciones como tarjetas; la elegida, con borde y anillo.
        <div role="radiogroup" aria-label={t("builder.channel.audience.title")} className="grid min-w-0 gap-2 sm:grid-cols-2">
          {modes.map((m) => (
            <label
              key={m}
              className="flex min-w-0 cursor-pointer items-start gap-3 rounded-md border border-input p-3 text-sm transition-colors has-[:checked]:border-primary has-[:checked]:ring-1 has-[:checked]:ring-primary has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ring motion-reduce:transition-none"
            >
              <input
                type="radio"
                name={`${base}-mode`}
                value={m}
                className="mt-1 size-4 shrink-0 accent-primary"
                checked={mode === m}
                onChange={() => onMode(m)}
              />
              <span className="grid min-w-0 gap-1">
                <span className="font-medium">{t(`builder.channel.mode.${m}` as MessageKey)}</span>
                <span className="text-xs text-pretty text-muted-foreground">{t(`builder.channel.mode.${m}.hint` as MessageKey)}</span>
              </span>
            </label>
          ))}
        </div>
      ) : (
        <p className="grid min-w-0 gap-1 text-sm">
          <span className="font-medium">{t(`builder.channel.mode.${mode}` as MessageKey)}</span>
          <span className="text-xs text-pretty text-muted-foreground">{t(`builder.channel.mode.${mode}.hint` as MessageKey)}</span>
        </p>
      )}
      {adminOnly ? (
        <Callout tone="info">{t("builder.channel.adminOnly")}</Callout>
      ) : null}
      {/* Los números de prueba, con «Solo mi equipo» (y mientras no se ha elegido). */}
      {mode !== "everyone" ? (
        <div className="grid min-w-0 gap-2">
          <h3 className="text-sm font-medium">{t("builder.channel.tests.title")}</h3>
          <NumberList
            label={t("builder.channel.tests.title")}
            numbers={draft.audience.test_numbers}
            writable={writable}
            empty={t("builder.channel.tests.empty")}
            onChange={onTests}
          />
        </div>
      ) : null}
    </div>
  );
}

/** Una lista de números en formato internacional, sin duplicados (32.4). */
function NumberList({
  label,
  numbers,
  writable,
  empty,
  onChange,
}: {
  label: string;
  numbers: string[];
  writable: boolean;
  empty: string;
  onChange: (list: string[]) => void;
}) {
  const t = useT();
  const [value, setValue] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  function add() {
    if (!value.trim()) return;
    const res = addNumber(numbers, value);
    if (!res.ok) {
      setError(res.error === "duplicate" ? t("builder.channel.number.duplicate") : t("builder.channel.number.invalid", { value: value.trim() }));
      return;
    }
    setError(null);
    setValue("");
    onChange(res.list);
  }

  return (
    <div className="grid min-w-0 gap-2">
      {numbers.length ? (
        <ul aria-label={label} className="flex min-w-0 flex-wrap gap-2">
          {numbers.map((n) => (
            <li key={n} className="inline-flex max-w-full min-w-0 items-center gap-1 rounded-full border border-border bg-muted/50 py-1 pr-1 pl-3 text-sm tabular-nums">
              <span className="min-w-0 truncate">{n}</span>
              {writable ? (
                <Button
                  type="button"
                  size="icon-xs"
                  variant="ghost"
                  aria-label={t("builder.channel.number.remove", { number: n })}
                  onClick={() => onChange(numbers.filter((x) => x !== n))}
                >
                  <X aria-hidden="true" />
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">{empty}</p>
      )}
      {writable ? (
        <div className="flex min-w-0 flex-wrap items-start gap-2">
          <div className="min-w-0 flex-1 basis-48">
            <Field label={t("builder.channel.number.field")} hint={t("builder.channel.number.hint")} error={error ?? undefined}>
              {(a11y) => (
                <Input
                  {...a11y}
                  type="tel"
                  inputMode="tel"
                  autoComplete="off"
                  value={value}
                  maxLength={40}
                  onChange={(e) => {
                    setValue(e.target.value);
                    setError(null);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      add();
                    }
                  }}
                />
              )}
            </Field>
          </div>
          <Button type="button" variant="outline" className="mt-6" onClick={add} aria-label={t("builder.channel.number.addTo", { list: label })}>
            <Plus aria-hidden="true" />
            {t("builder.channel.number.add")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function EscalationSection({
  draft,
  writable,
  notifyFrom,
  onRecipients,
  onSummary,
}: {
  draft: ChannelConfigIn;
  writable: boolean;
  notifyFrom: string;
  onRecipients: (list: Recipient[]) => void;
  onSummary: (summary: boolean) => void;
}) {
  const t = useT();
  const base = React.useId();
  const recipients = draft.escalation.recipients;
  const update = (i: number, patch: Partial<Recipient>) => onRecipients(recipients.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  return (
    <div className="grid min-w-0 gap-4">
      <p className="text-sm text-pretty" data-slot="notify-from">
        {notifyFrom === "channel" ? t("builder.channel.notify.channel") : t("builder.channel.notify.auphere")}
      </p>
      {recipients.length ? (
        writable ? (
          <ol aria-label={t("builder.channel.recipients")} className="grid min-w-0 gap-3">
            {recipients.map((r, i) => {
              const who = r.name.trim() || t("builder.channel.recipient.unnamed");
              return (
                <li key={i} className="min-w-0">
                  {/* Una fila por persona (prototipo §8): nombre, por dónde, su dato y la papelera; una columna por debajo de 700 px. */}
                  <div
                    role="group"
                    aria-label={t("builder.channel.recipient.legend", { n: i + 1 })}
                    className="grid min-w-0 items-end gap-2 border-b border-dashed border-border pb-3 min-[700px]:grid-cols-[minmax(0,1.2fr)_minmax(0,0.9fr)_minmax(0,1.2fr)_auto]"
                  >
                    <Field label={t("builder.channel.recipient.name")} required>
                      {(a11y) => <Input {...a11y} value={r.name} maxLength={80} autoComplete="off" onChange={(e) => update(i, { name: e.target.value })} />}
                    </Field>
                    <div className="grid min-w-0 gap-1">
                      <Label htmlFor={`${base}-via-${i}`}>{t("builder.channel.recipient.via")}</Label>
                      <NativeSelect id={`${base}-via-${i}`} value={r.via} wrapperClassName="w-full" onChange={(e) => update(i, { via: e.target.value })}>
                        <option value="whatsapp">{t("builder.channel.via.whatsapp")}</option>
                        <option value="email">{t("builder.channel.via.email")}</option>
                        <option value="inbox">{t("builder.channel.via.inbox")}</option>
                      </NativeSelect>
                    </div>
                    <div className="min-w-0">
                      {r.via === "whatsapp" ? (
                        <Field label={t("builder.channel.recipient.phone")}>
                          {(a11y) => (
                            <Input
                              {...a11y}
                              type="tel"
                              inputMode="tel"
                              autoComplete="off"
                              placeholder="+34 600 00 00 00"
                              value={r.phone_e164 ?? ""}
                              maxLength={40}
                              onChange={(e) => update(i, { phone_e164: e.target.value })}
                            />
                          )}
                        </Field>
                      ) : r.via === "email" ? (
                        <Field label={t("builder.channel.recipient.email")}>
                          {(a11y) => (
                            <Input
                              {...a11y}
                              type="email"
                              inputMode="email"
                              autoComplete="off"
                              value={r.email ?? ""}
                              maxLength={320}
                              onChange={(e) => update(i, { email: e.target.value })}
                            />
                          )}
                        </Field>
                      ) : (
                        <p className="text-xs text-pretty text-muted-foreground min-[700px]:pb-2">{t("builder.channel.recipient.inbox")}</p>
                      )}
                    </div>
                    <Button
                      type="button"
                      size="icon-sm"
                      variant="ghost"
                      className="justify-self-start "
                      onClick={() => onRecipients(recipients.filter((_, j) => j !== i))}
                      aria-label={t("builder.channel.recipient.remove", { name: who })}
                    >
                      <Trash2 aria-hidden="true" />
                    </Button>
                  </div>
                </li>
              );
            })}
          </ol>
        ) : (
          <ul aria-label={t("builder.channel.recipients")} className="grid min-w-0 gap-1 text-sm">
            {recipients.map((r, i) => (
              <li key={i} className="min-w-0 break-words">
                <span className="font-medium">{r.name}</span>
                {" · "}
                {t(`builder.channel.via.${r.via === "email" || r.via === "inbox" ? r.via : "whatsapp"}` as MessageKey)}
                {r.via === "whatsapp" && r.phone_e164 ? ` · ${r.phone_e164}` : r.via === "email" && r.email ? ` · ${r.email}` : ""}
              </li>
            ))}
          </ul>
        )
      ) : (
        <p className="text-sm text-pretty text-muted-foreground">{t("builder.channel.recipients.empty")}</p>
      )}
      {writable && recipients.length < MAX_RECIPIENTS ? (
        <div>
          <Button type="button" size="sm" variant="outline" onClick={() => onRecipients([...recipients, emptyRecipient()])}>
            <Plus aria-hidden="true" />
            {t("builder.channel.recipient.add")}
          </Button>
        </div>
      ) : writable ? (
        <p className="text-xs text-muted-foreground">{t("builder.channel.recipients.max")}</p>
      ) : null}
      {writable ? (
        <label className="flex min-w-0 items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-1 size-4 shrink-0 accent-primary"
            checked={draft.escalation.summary}
            onChange={(e) => onSummary(e.target.checked)}
            aria-describedby={`${base}-summary-hint`}
          />
          <span className="grid min-w-0 gap-1">
            <span className="font-medium">{t("builder.channel.summary")}</span>
            <span id={`${base}-summary-hint`} className="text-xs text-pretty text-muted-foreground">
              {t("builder.channel.summary.hint")}
            </span>
          </span>
        </label>
      ) : (
        <p className="text-sm">
          {t("builder.channel.summary")}: {draft.escalation.summary ? t("builder.channel.yes") : t("builder.channel.no")}
        </p>
      )}
    </div>
  );
}

/** Los disparadores viven en el agente: aquí se ven, sin tocarlos (33.5). */
function Triggers({ triggers, editHref }: { triggers: ChannelPage["triggers"]; editHref: string }) {
  const t = useT();
  return (
    <div className="grid min-w-0 gap-2 rounded-md bg-muted/40 p-3" data-slot="channel-triggers">
      <h3 className="text-sm font-medium">{t("builder.channel.triggers.title")}</h3>
      <p className="text-xs text-muted-foreground">{t("builder.channel.triggers.intro")}</p>
      {triggers.length ? (
        <ul className="grid list-disc gap-1 pl-5 text-sm">
          {triggers.map((tr, i) => (
            // El número de intentos no viene con los disparadores: el del AgentSpec por defecto.
            <li key={i} className="break-words">
              {triggerText(tr as EscalationTrigger, 2, t)}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">{t("builder.channel.triggers.none")}</p>
      )}
      <Link href={editHref} className="w-fit text-sm font-medium text-primary-text underline-offset-4 hover:underline">
        {t("builder.channel.triggers.edit")}
      </Link>
    </div>
  );
}

function History({ history }: { history: ChannelChange[] | null }) {
  const t = useT();
  const locale = useLocale();
  if (history === null) return <p className="text-sm text-muted-foreground">{t("builder.channel.history.error")}</p>;
  if (!history.length) return <p className="text-sm text-muted-foreground">{t("builder.channel.history.empty")}</p>;
  return (
    <ol className="grid min-w-0 gap-3" aria-label={t("builder.channel.history.title")}>
      {history.map((change) => {
        const lines = historyLines(t, change);
        return (
          <li key={change.id} className="grid min-w-0 gap-1 border-l-2 border-border pl-3 text-sm" data-slot="channel-change">
            <span className="flex min-w-0 flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span className="break-all">{t("builder.channel.history.by", { actor: cleanActor(change.actor), date: formatDateTime(change.at, locale) })}</span>
              {change.origin === "undo" || change.origin === "connect" ? (
                <StatusBadge tone="muted" dot={false}>
                  {t(`builder.channel.history.origin.${change.origin}` as MessageKey)}
                </StatusBadge>
              ) : null}
              {change.undone_at ? (
                <StatusBadge tone="muted" dot={false}>
                  {t("builder.channel.history.undone")}
                </StatusBadge>
              ) : null}
            </span>
            {lines.length ? (
              <ul className="grid gap-1">
                {lines.map((line) => (
                  <li key={line} className="text-pretty break-words">
                    {line}
                  </li>
                ))}
              </ul>
            ) : (
              <span className="text-muted-foreground">{t("builder.channel.history.nothing")}</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
