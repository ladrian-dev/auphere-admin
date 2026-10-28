"use client";

import { Play, Plus, Wrench } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button, Callout, Field, Input, StatusBadge, StatusDot, Textarea, formatNumber } from "@nexus/ui";

import {
  addTestAction,
  qualityJobAction,
  runTestsAction,
  setNotApplicableAction,
  testsAction,
} from "@/app/(console)/clients/[ref]/agents/quality-actions";
import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { AgentTest, QualityJob, TestBody, TestRunAccepted, TestRunScope, TestSuite } from "@/lib/backend/agent-quality-types";

import { sleep, type Result } from "./builder-model";
import { STATUS_TONE, groupTests, isFailing, waitForJob } from "./quality-model";

type Ids = { ref: string; agent: string };
export type TestListActions = {
  load: (body: Ids) => Promise<Result<TestSuite>>;
  run: (body: Ids & { scope: TestRunScope; test?: string }) => Promise<Result<TestRunAccepted>>;
  poll: (body: { ref: string; job: string }) => Promise<Result<QualityJob>>;
  notApplicable: (body: Ids & { test: string; reason: string }) => Promise<Result<TestSuite>>;
  add: (body: Ids & { test: TestBody }) => Promise<Result<TestSuite>>;
};

const SERVER_ACTIONS: TestListActions = {
  load: (body) => testsAction(body),
  run: (body) => runTestsAction(body),
  poll: (body) => qualityJobAction(body),
  notApplicable: (body) => setNotApplicableAction(body),
  add: (body) => addTestAction(body),
};

/**
 * Las pruebas del agente (spec 047, historia 8; requisito 21): todas, por tipo
 * (del caso, del sector, añadidas), cada una con su estado —«Pasa»,
 * «Inestable», «Falla», «No sé», «Sin ejecutar», «No aplica»— y
 * «Desactualizada» cuando cambió algo desde la última pasada.
 *
 * La que no pasa trae «Por qué falló» con lo que se comprobó (el estado final,
 * no lo que dijo el agente) y «Arreglar», que abre las instrucciones del
 * borrador. Una del sector se puede marcar «No aplica» escribiendo la razón.
 * Ejecutar es un trabajo: la lista se vuelve a leer al terminar. Sin el juez
 * calibrado, se dice que solo cuenta el estado final (21.8).
 */
export function TestList({
  refId,
  agentId,
  suite: initial,
  canWrite,
  refreshKey = 0,
  onFix,
  onWhy,
  onChanged,
  actions = SERVER_ACTIONS,
  wait = sleep,
}: {
  refId: string;
  agentId: string;
  /** `null` si no se pudo leer. */
  suite: TestSuite | null;
  canWrite: boolean;
  /** Cambia cuando el borrador cambió: la lista se vuelve a leer. */
  refreshKey?: number;
  /** «Arreglar»: abrir el bloque del borrador donde se corrige. */
  onFix?: (test: AgentTest) => void;
  /** «¿Por qué dijo esto?»: el copiloto explica la última respuesta de la prueba. */
  onWhy?: (test: AgentTest) => void;
  /** Una pasada terminó o una prueba cambió: la cabecera cuenta otra cosa. */
  onChanged?: () => void;
  actions?: TestListActions;
  wait?: (ms: number) => Promise<void>;
}) {
  const t = useT();
  const locale = useLocale();
  const ids = React.useMemo(() => ({ ref: refId, agent: agentId }), [refId, agentId]);
  const [suite, setSuite] = React.useState(initial);
  const [running, setRunning] = React.useState<{ count: number } | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [adding, setAdding] = React.useState(false);
  const alive = React.useRef(true);
  React.useEffect(
    () => () => {
      alive.current = false;
    },
    [],
  );

  const reload = React.useCallback(async () => {
    const res = await actions.load(ids);
    if (!alive.current) return;
    if (res.ok) setSuite(res.data);
  }, [actions, ids]);

  const seen = React.useRef(refreshKey);
  React.useEffect(() => {
    if (seen.current === refreshKey) return;
    seen.current = refreshKey;
    void reload();
  }, [refreshKey, reload]);

  const can = (what: "add" | "edit" | "run") => canWrite && Boolean(suite?.allowed.includes(what));

  async function runTests(scope: TestRunScope, test?: string) {
    setError(null);
    const res = await actions.run({ ...ids, scope, ...(test ? { test } : {}) });
    if (!res.ok) {
      setError(
        res.code === "build_budget_exhausted" || res.status === 402
          ? t("money.build.blocked")
          : res.code === "nothing_to_run"
          ? t("builder.suite.error.nothing")
          : res.code === "no_version"
            ? t("builder.suite.error.noVersion")
            : res.status === 401 || res.status === 403
              ? t("common.forbidden")
              : t("builder.suite.error.run"),
      );
      return;
    }
    setRunning({ count: res.data.tests });
    const done = await waitForJob(() => actions.poll({ ref: refId, job: res.data.job_id }), { wait, cancelled: () => !alive.current });
    if (!alive.current) return;
    setRunning(null);
    if (!done || !done.ok || done.data.status === "failed") setError(t("builder.suite.error.run"));
    else toast.success(t("builder.suite.ran"));
    await reload();
    onChanged?.();
  }

  if (!suite) {
    return (
      <div className="flex min-w-0 flex-wrap items-center gap-3 text-sm" data-slot="test-list">
        <p className="text-muted-foreground">{t("builder.suite.error.load")}</p>
        <Button size="sm" variant="outline" onClick={() => void reload()}>
          {t("builder.suite.retry")}
        </Button>
      </div>
    );
  }

  const { summary } = suite;
  const counted = summary.total - summary.not_applicable;

  return (
    <div className="grid min-w-0 gap-4" data-slot="test-list">
      <p className="text-sm text-pretty text-muted-foreground">{t("builder.suite.intro")}</p>
      <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2 text-sm" data-slot="test-summary">
        <span className="font-medium">{t("builder.suite.summary", { passed: summary.passed, total: counted })}</span>
        {summary.rate !== null ? <span className="text-muted-foreground">{t("builder.suite.rate", { rate: formatNumber(summary.rate, locale, { maximumFractionDigits: 1 }) })}</span> : null}
        {summary.stale > 0 ? <StatusBadge tone="warn">{t("builder.suite.stale", { n: summary.stale })}</StatusBadge> : null}
      </div>
      {!suite.judge_calibrated ? <Callout tone="info">{t("builder.suite.judge")}</Callout> : null}

      {can("run") ? (
        <div className="flex min-w-0 flex-wrap gap-2">
          <Button onClick={() => void runTests("all")} loading={running !== null}>
            <Play aria-hidden="true" />
            {t("builder.suite.runAll")}
          </Button>
          {summary.stale > 0 ? (
            <Button variant="outline" onClick={() => void runTests("affected")} disabled={running !== null}>
              {t("builder.suite.runStale")}
            </Button>
          ) : null}
        </div>
      ) : null}
      <p role="status" className="inline-flex min-w-0 items-center gap-2 text-sm text-muted-foreground empty:hidden">
        {running ? (
          <>
            <StatusDot tone="info" pulse />
            {t("builder.suite.running", { n: running.count })}
          </>
        ) : null}
      </p>
      {error ? (
        <p role="alert" className="text-sm text-destructive text-pretty">
          {error}
        </p>
      ) : null}

      {!suite.tests.length ? <p className="text-sm text-muted-foreground">{t("builder.suite.empty")}</p> : null}
      {groupTests(suite.tests).map((group) => (
        <div key={group.kind} className="grid min-w-0 gap-2">
          <h4 className="text-sm font-semibold" id={`tests-${group.kind}`}>
            {t(`builder.suite.kind.${group.kind}` as MessageKey)} · {group.tests.length}
          </h4>
          <ul aria-labelledby={`tests-${group.kind}`} className="grid min-w-0 gap-2">
            {group.tests.map((test) => (
              <TestRow
                key={test.id}
                test={test}
                canEdit={can("edit")}
                canRun={can("run") && running === null}
                onRun={() => void runTests("one", test.id)}
                onFix={onFix && canWrite ? () => onFix(test) : undefined}
                onWhy={onWhy ? () => onWhy(test) : undefined}
                onNotApplicable={async (reason) => {
                  const res = await actions.notApplicable({ ...ids, test: test.id, reason });
                  if (res.ok) {
                    setSuite(res.data);
                    onChanged?.();
                  }
                  return res;
                }}
              />
            ))}
          </ul>
        </div>
      ))}

      {can("add") ? (
        adding ? (
          <AddTestForm
            onCancel={() => setAdding(false)}
            onAdd={async (body) => {
              const res = await actions.add({ ...ids, test: body });
              if (res.ok) {
                setSuite(res.data);
                setAdding(false);
                toast.success(t("builder.suite.saved"));
              }
              return res;
            }}
          />
        ) : (
          <div>
            <Button variant="outline" size="sm" onClick={() => setAdding(true)}>
              <Plus aria-hidden="true" />
              {t("builder.suite.add")}
            </Button>
          </div>
        )
      ) : null}
    </div>
  );
}

function TestRow({
  test,
  canEdit,
  canRun,
  onRun,
  onFix,
  onWhy,
  onNotApplicable,
}: {
  test: AgentTest;
  canEdit: boolean;
  canRun: boolean;
  onRun: () => void;
  onFix?: () => void;
  onWhy?: () => void;
  onNotApplicable: (reason: string) => Promise<Result<TestSuite>>;
}) {
  const t = useT();
  const nameId = React.useId();
  const [marking, setMarking] = React.useState(false);
  const failing = isFailing(test.status);
  const sector = test.kind === "sector";

  return (
    <li aria-labelledby={nameId} className="grid min-w-0 gap-2 rounded-md border border-border p-3" data-slot="test-row" data-status={test.status}>
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
        <div className="grid min-w-0 flex-1 basis-48 gap-1">
          <span id={nameId} className="text-sm font-medium text-pretty break-words">
            {test.name}
          </span>
          <span className="text-xs text-pretty break-words text-muted-foreground">{t("builder.suite.first", { text: test.first_message })}</span>
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {test.critical ? <StatusBadge tone="danger" dot={false}>{t("builder.suite.critical")}</StatusBadge> : null}
          <StatusBadge tone={STATUS_TONE[test.status]}>{t(`builder.suite.status.${test.status}` as MessageKey)}</StatusBadge>
          {test.stale && test.status !== "not_applicable" ? <StatusBadge tone="warn">{t("builder.suite.staleBadge")}</StatusBadge> : null}
        </div>
      </div>
      {test.decided > 0 && test.status !== "not_applicable" ? (
        <p className="text-xs text-muted-foreground tabular-nums">{t("builder.suite.passes", { passes: test.passes, decided: test.decided })}</p>
      ) : null}
      {test.not_applicable_reason ? (
        <p className="text-xs text-pretty text-muted-foreground">{t("builder.suite.na.shown", { reason: test.not_applicable_reason })}</p>
      ) : null}
      {failing ? (
        <details className="min-w-0 text-sm" data-slot="test-why">
          <summary className="w-fit cursor-pointer font-medium">{t("builder.suite.why")}</summary>
          <p className="mt-1 text-pretty break-words whitespace-pre-line text-muted-foreground">{test.why_failed || t("builder.suite.why.none")}</p>
        </details>
      ) : null}
      {marking ? (
        <NotApplicableForm name={test.name} onCancel={() => setMarking(false)} onSave={onNotApplicable} onDone={() => setMarking(false)} />
      ) : (
        <div className="flex min-w-0 flex-wrap gap-2 empty:hidden">
          {failing && onFix ? (
            <Button size="sm" variant="outline" onClick={onFix} aria-label={t("builder.suite.fix.label", { name: test.name })}>
              <Wrench aria-hidden="true" />
              {t("builder.suite.fix")}
            </Button>
          ) : null}
          {failing && onWhy ? (
            <Button size="sm" variant="ghost" onClick={onWhy} aria-label={t("builder.copilot.why.test", { name: test.name })}>
              {t("builder.copilot.why")}
            </Button>
          ) : null}
          {canRun && test.status !== "not_applicable" ? (
            <Button size="sm" variant="ghost" onClick={onRun} aria-label={t("builder.suite.runOne", { name: test.name })}>
              <Play aria-hidden="true" />
              {t("builder.suite.run")}
            </Button>
          ) : null}
          {canEdit && sector && !test.not_applicable_reason ? (
            <Button size="sm" variant="ghost" onClick={() => setMarking(true)} aria-label={t("builder.suite.na.label", { name: test.name })}>
              {t("builder.suite.na")}
            </Button>
          ) : null}
          {canEdit && sector && test.not_applicable_reason ? (
            <Button size="sm" variant="ghost" onClick={() => void onNotApplicable("")}>
              {t("builder.suite.na.undo")}
            </Button>
          ) : null}
        </div>
      )}
    </li>
  );
}

function NotApplicableForm({
  name,
  onSave,
  onCancel,
  onDone,
}: {
  name: string;
  onSave: (reason: string) => Promise<Result<TestSuite>>;
  onCancel: () => void;
  onDone: () => void;
}) {
  const t = useT();
  const [reason, setReason] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const fieldRef = React.useRef<HTMLTextAreaElement>(null);
  React.useEffect(() => {
    fieldRef.current?.focus();
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (reason.trim().length < 3) {
      setError(t("builder.suite.na.required"));
      return;
    }
    setBusy(true);
    const res = await onSave(reason.trim());
    setBusy(false);
    if (res.ok) return onDone();
    setError(res.code === "reason_required" ? t("builder.suite.na.required") : t("builder.suite.error.save"));
  }

  return (
    <form onSubmit={submit} noValidate className="grid min-w-0 gap-2" aria-label={t("builder.suite.na.label", { name })}>
      <Field label={t("builder.suite.na.reason")} error={error ?? undefined} required>
        {(a11y) => <Textarea {...a11y} ref={fieldRef} value={reason} rows={2} maxLength={500} onChange={(e) => setReason(e.target.value)} />}
      </Field>
      <div className="flex flex-wrap gap-2">
        <Button type="submit" size="sm" loading={busy}>
          {t("builder.suite.na.save")}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel} disabled={busy}>
          {t("builder.suite.na.cancel")}
        </Button>
      </div>
    </form>
  );
}

function AddTestForm({ onAdd, onCancel }: { onAdd: (body: TestBody) => Promise<Result<TestSuite>>; onCancel: () => void }) {
  const t = useT();
  const [name, setName] = React.useState("");
  const [first, setFirst] = React.useState("");
  const [critical, setCritical] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim() || !first.trim()) {
      setError(t("builder.suite.add.required"));
      return;
    }
    setBusy(true);
    setError(null);
    const res = await onAdd({ name: name.trim(), first_message: first.trim(), critical });
    setBusy(false);
    if (!res.ok) setError(t("builder.suite.error.save"));
  }

  return (
    <form onSubmit={submit} noValidate className="grid min-w-0 gap-3 rounded-md border border-border p-3" aria-label={t("builder.suite.add")}>
      <Field label={t("builder.suite.add.name")} required>
        {(a11y) => <Input {...a11y} value={name} maxLength={120} autoComplete="off" onChange={(e) => setName(e.target.value)} />}
      </Field>
      <Field label={t("builder.suite.add.first")} required>
        {(a11y) => <Textarea {...a11y} value={first} rows={2} maxLength={2000} onChange={(e) => setFirst(e.target.value)} />}
      </Field>
      <label className="flex min-h-6 items-center gap-2 text-sm">
        <input type="checkbox" className="size-4 accent-primary" checked={critical} onChange={(e) => setCritical(e.target.checked)} />
        {t("builder.suite.add.critical")}
      </label>
      {error ? (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" size="sm" loading={busy}>
          {t("builder.suite.add.save")}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel} disabled={busy}>
          {t("builder.suite.add.cancel")}
        </Button>
      </div>
    </form>
  );
}
