"use client";

import { AlertTriangle, Ban, CheckCircle2, Plus, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, Callout, Field, Input, Label, NativeSelect, StatusBadge, Textarea, formatDateTime } from "@nexus/ui";

import {
  channelHistoryAction,
  channelPageAction,
  saveChannelConfigAction,
  undoChannelConfigAction,
} from "@/app/(console)/clients/[ref]/agents/channel-actions";
import { BalanceButton, type BalanceMode } from "@/components/money/balance-button";
import { CrumbName } from "@/components/shell/crumb-names";
import { agentHref } from "@/components/shell/routes-v2";
import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { EscalationTrigger } from "@/lib/backend/builder-types";
import type { AudienceMode, ChannelChange, ChannelConfigIn, ChannelPage, Recipient } from "@/lib/backend/channel-config-types";

import { triggerText } from "./block-view";
import type { Result } from "./builder-model";
import { ChannelMenu, UnlinkPending, type ChannelMenuActions } from "./channel-menu";
import {
  MAX_RECIPIENTS,
  WAIT_MESSAGE_MAX,
  addNumber,
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
import { undoOpen } from "./quality-model";

type Ids = { ref: string; channel: string };
export type ChannelPageActions = {
  save: (body: Ids & { revision: number; config: ChannelConfigIn }) => Promise<Result<ChannelPage>>;
  undo: (body: Ids) => Promise<Result<ChannelPage>>;
  reload: (body: Ids) => Promise<Result<ChannelPage>>;
  history: (body: Ids) => Promise<Result<ChannelChange[]>>;
  menu?: ChannelMenuActions;
};

export const CHANNEL_PAGE_ACTIONS: ChannelPageActions = {
  save: (body) => saveChannelConfigAction(body),
  undo: (body) => undoChannelConfigAction(body),
  reload: (body) => channelPageAction(body),
  history: (body) => channelHistoryAction(body),
};

const SECTIONS = [
  { id: "canal-audiencia", label: "builder.channel.audience.title" },
  { id: "canal-excepciones", label: "builder.channel.exceptions.title" },
  { id: "canal-escalado", label: "builder.channel.escalation.title" },
  { id: "canal-espera", label: "builder.channel.wait.title" },
  { id: "canal-comprobaciones", label: "builder.channel.checks.title" },
  { id: "canal-historial", label: "builder.channel.history.title" },
] as const satisfies readonly { id: string; label: MessageKey }[];

const MODES: readonly AudienceMode[] = ["team_only", "everyone", "unset"];

type Conflict = { current: number; changes: unknown };

/**
 * La página de configuración de un canal (spec 047, historia 11; requisitos 32
 * y 33; T115): a quién responde (con sus números de prueba), excepciones,
 * escalado a personas (hasta 10, con los disparadores del agente en solo
 * lectura y de qué número saldrán los avisos), mensaje de espera y
 * comprobaciones, con su barra de guardar y su historial.
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
  actions?: ChannelPageActions;
}) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const [page, setPage] = React.useState(initialPage);
  const [saved, setSaved] = React.useState(() => draftFromPage(initialPage));
  const [draft, setDraft] = React.useState(() => draftFromPage(initialPage));
  const [history, setHistory] = React.useState(initialHistory);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<SaveError | null>(null);
  const [conflict, setConflict] = React.useState<Conflict | null>(null);
  const [unlinkPending, setUnlinkPending] = React.useState(false);
  const ids = { ref: refId, channel: page.id };
  const owner = page.agent?.id ?? agentId;
  const writable = canWrite && page.allowed.includes("configure");
  const dirty = writable && isDirty(draft, saved);
  const canUndo = writable && undoOpen(page.undo_until);
  const targets: FixTargets = {
    agent: agentHref(refId, owner),
    tests: `${agentHref(refId, owner)}#agente-pruebas`,
    balance: balanceHref,
    recipients: "#canal-escalado",
  };

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

  async function save(revision: number = page.revision) {
    const problem = draftProblem(t, draft);
    if (problem) {
      setError({ section: problem.section, text: problem.text, fix: null });
      return;
    }
    setBusy(true);
    setError(null);
    const res = await actions.save({ ...ids, revision, config: toPayload(draft) });
    setBusy(false);
    if (res.ok) {
      adopt(res.data);
      toast.success(t("builder.channel.saved"));
      void refreshHistory();
      return;
    }
    if (res.status === 412 && res.code === "revision_conflict") {
      const current = Number(res.info?.current);
      setConflict({ current: Number.isFinite(current) ? current : page.revision, changes: res.info?.changes });
      return;
    }
    setError(saveErrorOf(t, res));
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

  return (
    <div className="grid min-w-0 gap-6" data-slot="channel-page">
      <CrumbName id={page.id} label={page.identifier} />
      {page.agent ? <CrumbName id={page.agent.id} label={page.agent.name} /> : null}
      <header className="grid min-w-0 gap-3">
        <div className="flex min-w-0 items-start justify-between gap-3">
          <div className="grid min-w-0 gap-1">
            <h2 className="min-w-0 text-xl font-semibold text-balance break-words tabular-nums">{t("builder.channel.page.title", { number: page.identifier })}</h2>
            <p className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
              <span>{page.type === "whatsapp" ? t("builder.channels.whatsapp") : page.type}</span>
              <span aria-hidden="true">·</span>
              {page.agent ? (
                <Link href={agentHref(refId, page.agent.id)} className="font-medium text-primary-text underline-offset-4 hover:underline">
                  {t("builder.channel.page.agent", { name: page.agent.name })}
                </Link>
              ) : (
                <span>{t("builder.channel.page.noAgent")}</span>
              )}
            </p>
          </div>
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
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <StatusBadge tone={visibleTone(page.visible_state)} data-slot="channel-state">
            {channelStateText(t, page.visible_state)}
          </StatusBadge>
        </div>
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
        <nav aria-label={t("builder.channel.page.sections")} className="min-w-0">
          <ul className="flex min-w-0 gap-2 overflow-x-auto pb-1" data-scroll-x>
            {SECTIONS.map((s) => (
              <li key={s.id} className="shrink-0">
                <a
                  href={`#${s.id}`}
                  className="inline-flex min-h-8 items-center rounded-full px-3 text-sm text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                >
                  {t(s.label)}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </header>

      <form
        noValidate
        className="grid min-w-0 gap-6"
        onSubmit={(e) => {
          e.preventDefault();
          if (dirty) void save();
        }}
        data-slot="channel-config"
      >
        <PageSection id="canal-audiencia" title={t("builder.channel.audience.title")} intro={t("builder.channel.audience.intro")}>
          <AudienceSection
            draft={draft}
            writable={writable}
            adminOnly={page.admin_only_template}
            onMode={(mode) => set((d) => ({ ...d, audience: { ...d.audience, mode } }))}
            onTests={(list) => set((d) => ({ ...d, audience: { ...d.audience, test_numbers: list } }))}
          />
          <InlineError error={errorIn("audience")} targets={targets} balance={balance} refId={refId} />
        </PageSection>

        <PageSection id="canal-excepciones" title={t("builder.channel.exceptions.title")} intro={t("builder.channel.exceptions.intro")}>
          <NumberList
            label={t("builder.channel.exceptions.title")}
            numbers={draft.audience.exceptions}
            writable={writable}
            empty={t("builder.channel.exceptions.empty")}
            onChange={(list) => set((d) => ({ ...d, audience: { ...d.audience, exceptions: list } }))}
          />
          {draft.audience.mode !== "everyone" ? <p className="text-xs text-muted-foreground">{t("builder.channel.exceptions.unused")}</p> : null}
        </PageSection>

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

        {writable ? (
          <div
            className="sticky bottom-0 z-10 grid min-w-0 gap-3 rounded-md border border-border bg-card/95 p-3 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-card/80"
            data-slot="channel-save-bar"
          >
            {conflict ? (
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
            {error && error.section === "general" ? (
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
            <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-muted-foreground" aria-live="polite">
                {dirty ? t("builder.channel.bar.dirty") : t("builder.channel.bar.clean")}
              </p>
              <div className="flex flex-wrap items-center gap-2">
                {canUndo && !dirty ? (
                  <>
                    <span className="text-xs text-muted-foreground">{t("builder.channel.undo.until", { time: formatClock(page.undo_until, locale) })}</span>
                    <Button type="button" size="sm" variant="outline" onClick={() => void undo()} disabled={busy}>
                      {t("builder.channel.undo")}
                    </Button>
                  </>
                ) : null}
                {dirty ? (
                  <>
                    <Button type="button" size="sm" variant="ghost" onClick={() => adopt(page)} disabled={busy}>
                      {t("builder.channel.bar.discard")}
                    </Button>
                    <Button type="submit" size="sm" loading={busy}>
                      {t("builder.channel.bar.save")}
                    </Button>
                  </>
                ) : null}
              </div>
            </div>
          </div>
        ) : null}
      </form>

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

      <PageSection id="canal-historial" title={t("builder.channel.history.title")}>
        <History history={history} />
      </PageSection>
    </div>
  );
}

function PageSection({ id, title, intro, children }: { id: string; title: string; intro?: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="grid min-w-0 scroll-mt-24 gap-3 rounded-md border border-border bg-card p-4 sm:p-6">
      <div className="grid min-w-0 gap-1">
        <h3 id={`${id}-title`} className="text-base font-semibold text-balance">
          {title}
        </h3>
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
  onMode,
  onTests,
}: {
  draft: ChannelConfigIn;
  writable: boolean;
  adminOnly: boolean;
  onMode: (mode: AudienceMode) => void;
  onTests: (list: string[]) => void;
}) {
  const t = useT();
  const base = React.useId();
  const mode = draft.audience.mode;
  // 32.5: con plantilla de solo administradores, «A todos» no se ofrece, y se dice por qué.
  const modes = MODES.filter((m) => !(adminOnly && m === "everyone" && mode !== "everyone"));
  return (
    <div className="grid min-w-0 gap-4">
      {writable ? (
        <fieldset className="grid min-w-0 gap-2">
          <legend className="sr-only">{t("builder.channel.audience.title")}</legend>
          {modes.map((m) => (
            <label key={m} className="flex min-h-6 min-w-0 items-start gap-2 text-sm">
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
        </fieldset>
      ) : (
        <p className="grid min-w-0 gap-1 text-sm">
          <span className="font-medium">{t(`builder.channel.mode.${mode}` as MessageKey)}</span>
          <span className="text-xs text-pretty text-muted-foreground">{t(`builder.channel.mode.${mode}.hint` as MessageKey)}</span>
        </p>
      )}
      {adminOnly ? (
        <Callout tone="info">{t("builder.channel.adminOnly")}</Callout>
      ) : null}
      <div className="grid min-w-0 gap-2">
        <h4 className="text-sm font-medium">{t("builder.channel.tests.title")}</h4>
        <NumberList
          label={t("builder.channel.tests.title")}
          numbers={draft.audience.test_numbers}
          writable={writable}
          empty={t("builder.channel.tests.empty")}
          onChange={onTests}
        />
      </div>
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
            {recipients.map((r, i) => (
              <li key={i} className="min-w-0">
                <fieldset className="grid min-w-0 gap-3 rounded-md border border-border p-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,10rem)]">
                  <legend className="px-1 text-xs font-medium text-muted-foreground">{t("builder.channel.recipient.legend", { n: i + 1 })}</legend>
                  <Field label={t("builder.channel.recipient.name")} required>
                    {(a11y) => <Input {...a11y} value={r.name} maxLength={80} autoComplete="off" onChange={(e) => update(i, { name: e.target.value })} />}
                  </Field>
                  <div className="grid min-w-0 gap-1">
                    <Label htmlFor={`${base}-via-${i}`}>{t("builder.channel.recipient.via")}</Label>
                    <NativeSelect
                      id={`${base}-via-${i}`}
                      value={r.via}
                      wrapperClassName="w-full"
                      onChange={(e) => update(i, { via: e.target.value })}
                    >
                      <option value="whatsapp">{t("builder.channel.via.whatsapp")}</option>
                      <option value="email">{t("builder.channel.via.email")}</option>
                      <option value="inbox">{t("builder.channel.via.inbox")}</option>
                    </NativeSelect>
                  </div>
                  <div className="min-w-0 sm:col-span-2">
                    {r.via === "whatsapp" ? (
                      <Field label={t("builder.channel.recipient.phone")} hint={t("builder.channel.number.hint")}>
                        {(a11y) => (
                          <Input
                            {...a11y}
                            type="tel"
                            inputMode="tel"
                            autoComplete="off"
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
                      <p className="text-sm text-pretty text-muted-foreground">{t("builder.channel.recipient.inbox")}</p>
                    )}
                  </div>
                  <div className="sm:col-span-2">
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => onRecipients(recipients.filter((_, j) => j !== i))}
                      aria-label={t("builder.channel.recipient.remove", { name: r.name.trim() || t("builder.channel.recipient.unnamed") })}
                    >
                      <X aria-hidden="true" />
                      {t("builder.channel.recipient.remove", { name: r.name.trim() || t("builder.channel.recipient.unnamed") })}
                    </Button>
                  </div>
                </fieldset>
              </li>
            ))}
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
      <h4 className="text-sm font-medium">{t("builder.channel.triggers.title")}</h4>
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
              <span className="break-all">{t("builder.channel.history.by", { actor: change.actor, date: formatDateTime(change.at, locale) })}</span>
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
