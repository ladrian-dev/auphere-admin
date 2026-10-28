"use client";

import { CircleAlert, CircleCheck, Play, TriangleAlert, Wrench } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@nexus/ui";

import { qualityJobAction, runTestsAction, testsAction } from "@/app/(console)/clients/[ref]/agents/quality-actions";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { AgentTest, QualityJob, ReviewFinding, TestRunAccepted, TestRunScope, TestSuite } from "@/lib/backend/agent-quality-types";

import { findingsByCheck, testsState } from "./agent-proto-model";
import { integrationName, sleep, type Result } from "./builder-model";
import { isFailing, reviewFixLink, waitForJob } from "./quality-model";
import type { ReviewSource } from "./review-panel";

type Ids = { ref: string; agent: string };
export type TestRunActions = {
  load: (body: Ids) => Promise<Result<TestSuite>>;
  run: (body: Ids & { scope: TestRunScope; test?: string }) => Promise<Result<TestRunAccepted>>;
  poll: (body: { ref: string; job: string }) => Promise<Result<QualityJob>>;
};

const SERVER_ACTIONS: TestRunActions = {
  load: (body) => testsAction(body),
  run: (body) => runTestsAction(body),
  poll: (body) => qualityJobAction(body),
};

/** Las pruebas de la pantalla y su pasada, compartidas por la tarjeta y la barra flotante. */
export type TestRun = {
  suite: TestSuite | null;
  /** Cuántas se están ejecutando; `null` si no corre ninguna pasada. */
  running: { count: number } | null;
  error: string | null;
  canRun: boolean;
  run: (scope?: TestRunScope) => Promise<void>;
  reload: () => Promise<void>;
};

/**
 * Las pruebas del agente y «Ejecutar» (spec 047, requisito 21): ejecutar es un
 * trabajo, y al terminar se vuelven a leer. La API no dice cuántas van
 * mientras corre (`QualityJob.progress` solo trae el paso): se sabe cuántas se
 * lanzaron y que siguen en marcha. Se vuelve a leer cuando cambia el borrador.
 */
export function useTestRun({
  refId,
  agentId,
  initial,
  canWrite,
  refreshKey = 0,
  onChanged,
  actions = SERVER_ACTIONS,
  wait = sleep,
  enabled = true,
}: {
  refId: string;
  agentId: string;
  initial: TestSuite | null;
  canWrite: boolean;
  refreshKey?: number;
  onChanged?: () => void;
  actions?: TestRunActions;
  wait?: (ms: number) => Promise<void>;
  /** Sin pruebas en la pantalla, no se leen. */
  enabled?: boolean;
}): TestRun {
  const t = useT();
  const ids = React.useMemo(() => ({ ref: refId, agent: agentId }), [refId, agentId]);
  const [suite, setSuite] = React.useState(initial);
  const [running, setRunning] = React.useState<{ count: number } | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const alive = React.useRef(true);
  React.useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const reload = React.useCallback(async () => {
    const res = await actions.load(ids);
    if (alive.current && res.ok) setSuite(res.data);
  }, [actions, ids]);

  const seen = React.useRef(refreshKey);
  React.useEffect(() => {
    if (seen.current === refreshKey) return;
    seen.current = refreshKey;
    if (enabled) void reload();
  }, [refreshKey, reload, enabled]);

  async function run(scope: TestRunScope = "all") {
    if (running) return;
    setError(null);
    const res = await actions.run({ ...ids, scope });
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

  return { suite, running, error, canRun: canWrite && Boolean(suite?.allowed.includes("run")), run, reload };
}

/** Las tres comprobaciones del prototipo, en su orden; las demás salen solo si encuentran algo. */
const MAIN_CHECKS = ["skills_integrations", "contradictions", "services"] as const;

/**
 * La tarjeta de pruebas de la columna derecha, como el prototipo (§5.1):
 * «Pruebas · 19 de 20 pasan», «Ejecutar todas» o «Repetir», la barra de
 * avance, la prueba que falla con su arreglo, «Todas pasan.» y la revisión
 * automática con el arreglo de cada hallazgo. La lista completa (por tipo, «No
 * aplica», «Añadir una prueba») está en «Más ajustes».
 */
export function TestsBox({
  refId,
  tests,
  review,
  canWrite,
  onFix,
  onWhy,
  onEdit,
  onConnect,
  onAll,
}: {
  refId: string;
  tests: TestRun;
  /** La revisión que ya leyó la pantalla; `null` si no se pinta. */
  review: ReviewSource | null;
  canWrite: boolean;
  /** «Arreglar»: abrir el bloque del borrador donde se corrige. */
  onFix: (test: AgentTest) => void;
  /** «¿Por qué dijo esto?»: el copiloto lo explica. */
  onWhy?: (test: AgentTest) => void;
  /** Un arreglo «edit» de la revisión: abrir el bloque al que apunta. */
  onEdit: (pointer: string | null) => void;
  /** Un conector que falta: la pestaña Conectores, sin salir de la pantalla. */
  onConnect?: (integration: string) => void;
  /** «Ver las N pruebas»: la lista completa, en «Más ajustes». */
  onAll: () => void;
}) {
  const t = useT();
  const titleId = React.useId();
  const { suite, running, error, canRun } = tests;

  if (!suite) {
    return (
      <section aria-labelledby={titleId} className="grid min-w-0 gap-2 rounded-lg border border-border bg-card px-4 py-3" data-slot="tests-box">
        <h2 id={titleId} className="text-sm font-medium">
          {t("builder.screen.tests")}
        </h2>
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-2 text-sm">
          <p className="text-muted-foreground">{t("builder.suite.error.load")}</p>
          <Button size="sm" variant="outline" onClick={() => void tests.reload()}>
            {t("builder.suite.retry")}
          </Button>
        </div>
      </section>
    );
  }

  const state = testsState(suite.summary);
  const done = state.kind === "failing" || state.kind === "passing";
  const label = running
    ? t("agentProto.tests.state.running", { n: running.count })
    : state.kind === "none"
      ? t("agentProto.tests.state.none")
      : state.kind === "pending"
        ? t("agentProto.tests.state.pending", { n: state.pending })
        : t("agentProto.tests.state.done", { passed: state.passed, total: state.counted });
  // La que falla y tiene su resultado al día; las críticas primero.
  const failing = running ? [] : suite.tests.filter((x) => isFailing(x.status) && !x.stale).sort((a, b) => Number(b.critical) - Number(a.critical));
  const first = failing[0];

  return (
    <section id="agente-pruebas-resumen" aria-labelledby={titleId} className="grid min-w-0 scroll-mt-24 overflow-hidden rounded-lg border border-border bg-card" data-slot="tests-box">
      <div className="flex min-w-0 items-center justify-between gap-2 px-4 py-3">
        <div className="grid min-w-0 gap-1">
          <h2 id={titleId} className="text-sm font-medium text-pretty">
            {t("agentProto.tests.title", { state: label })}
          </h2>
          <p className="text-xs text-pretty text-muted-foreground">{t("agentProto.tests.note")}</p>
        </div>
        {canRun && state.kind !== "none" ? (
          <Button size="sm" variant={done ? "outline" : "default"} onClick={() => void tests.run("all")} disabled={running !== null} className="shrink-0">
            <Play aria-hidden="true" />
            {done ? t("agentProto.tests.again") : t("agentProto.tests.runAll")}
          </Button>
        ) : null}
      </div>

      {running || done ? <TestsProgress running={running !== null} /> : null}
      <p role="status" className="sr-only">
        {running ? t("builder.suite.running", { n: running.count }) : ""}
      </p>
      {error ? (
        <p role="alert" className="mx-4 mb-3 text-sm text-pretty text-destructive">
          {error}
        </p>
      ) : null}

      {first ? (
        <div role="alert" className="mx-4 mb-4 grid min-w-0 gap-2 rounded-md bg-status-danger-bg p-3 text-sm" data-slot="tests-fail">
          <p className="text-sm font-medium text-pretty break-words">{t("agentProto.tests.fail.title", { name: first.name })}</p>
          <p className="text-pretty break-words whitespace-pre-line text-muted-foreground">{first.why_failed || t("builder.suite.why.none")}</p>
          {failing.length > 1 ? (
            <p className="text-xs text-muted-foreground">
              {failing.length === 2 ? t("agentProto.tests.fail.more.one") : t("agentProto.tests.fail.more.other", { n: failing.length - 1 })}
            </p>
          ) : null}
          {canWrite ? (
            <div className="flex min-w-0 flex-wrap gap-2">
              <Button size="sm" onClick={() => onFix(first)} aria-label={t("builder.suite.fix.label", { name: first.name })}>
                <Wrench aria-hidden="true" />
                {t("builder.suite.fix")}
              </Button>
              {onWhy ? (
                <Button size="sm" variant="outline" onClick={() => onWhy(first)} aria-label={t("builder.copilot.why.test", { name: first.name })}>
                  {t("builder.copilot.why")}
                </Button>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : state.kind === "passing" && !running ? (
        <p className="mx-4 mb-4 flex min-w-0 items-center gap-2 rounded-md bg-status-positive-bg px-3 py-2 text-sm" data-slot="tests-ok">
          <CircleCheck aria-hidden="true" className="size-4 shrink-0 text-status-positive-text" />
          {t("agentProto.tests.allPass")}
        </p>
      ) : null}

      {review?.review && !running ? (
        <ReviewChecks refId={refId} source={review} canWrite={canWrite} onEdit={onEdit} onConnect={onConnect} />
      ) : null}

      {suite.tests.length ? (
        <div className="border-t border-border px-4 py-2">
          <button type="button" onClick={onAll} className="cursor-pointer text-sm font-medium text-primary-text underline underline-offset-4 hover:no-underline">
            {t("agentProto.tests.all", { n: suite.tests.length })}
          </button>
        </div>
      ) : null}
    </section>
  );
}

/**
 * La barra de avance: llena al terminar. Mientras corre, la API no dice
 * cuántas van, así que la barra late entera en vez de inventar un porcentaje.
 */
function TestsProgress({ running }: { running: boolean }) {
  const t = useT();
  return (
    <div
      role="progressbar"
      aria-label={t("agentProto.tests.progress")}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={running ? undefined : 100}
      aria-busy={running || undefined}
      className="mx-4 mb-3 h-2 overflow-hidden rounded-full bg-muted"
      data-slot="tests-progress"
    >
      <span className={`block h-full w-full rounded-full bg-status-positive ${running ? "animate-pulse motion-reduce:animate-none" : ""}`} />
    </div>
  );
}

/** «Revisión automática»: las tres del prototipo y cualquier otra que encuentre algo, cada hallazgo con su arreglo. */
function ReviewChecks({
  refId,
  source,
  canWrite,
  onEdit,
  onConnect,
}: {
  refId: string;
  source: ReviewSource;
  canWrite: boolean;
  onEdit: (pointer: string | null) => void;
  onConnect?: (integration: string) => void;
}) {
  const t = useT();
  const review = source.review!;
  const byCheck = findingsByCheck(review);
  const shown = review.checks.filter((c) => (MAIN_CHECKS as readonly string[]).includes(c.check) || !c.ok);
  const order = (check: string) => {
    const i = (MAIN_CHECKS as readonly string[]).indexOf(check);
    return i < 0 ? MAIN_CHECKS.length : i;
  };
  const rows = [...shown].sort((a, b) => order(a.check) - order(b.check));
  if (!rows.length) return null;
  return (
    <ul aria-label={t("agentProto.tests.checks")} className="grid min-w-0 gap-2 px-4 pb-4 text-sm" data-slot="tests-checks">
      {rows.flatMap((check) => {
        const findings = byCheck.get(check.check) ?? [];
        if (check.ok) {
          return [
            <li key={check.check} className="flex min-w-0 items-start gap-2" data-ok="true">
              <CircleCheck aria-hidden="true" className="mt-1 size-4 shrink-0 text-status-positive-text" />
              <span className="min-w-0 text-pretty">
                {(MAIN_CHECKS as readonly string[]).includes(check.check)
                  ? t(`agentProto.tests.check.${check.check}` as MessageKey)
                  : t(`builder.review.check.${check.check}` as MessageKey)}
              </span>
            </li>,
          ];
        }
        if (!findings.length) {
          return [
            <li key={check.check} className="flex min-w-0 items-start gap-2" data-ok="false">
              <TriangleAlert aria-hidden="true" className="mt-1 size-4 shrink-0 text-warning" />
              <span className="min-w-0 text-pretty">
                {t(`builder.review.check.${check.check}` as MessageKey)} ·{" "}
                {check.findings === 1 ? t("builder.review.found.one") : t("builder.review.found.other", { n: check.findings })}
              </span>
            </li>,
          ];
        }
        return findings.map((finding, i) => (
          <li key={`${check.check}-${i}`} className="flex min-w-0 items-start gap-2" data-ok="false" data-severity={finding.severity}>
            {finding.severity === "block" ? (
              <CircleAlert aria-hidden="true" className="mt-1 size-4 shrink-0 text-destructive" />
            ) : (
              <TriangleAlert aria-hidden="true" className="mt-1 size-4 shrink-0 text-warning" />
            )}
            <span className="min-w-0 text-pretty break-words">
              {finding.message}{" "}
              <FindingFix refId={refId} finding={finding} source={source} canWrite={canWrite} onEdit={onEdit} onConnect={onConnect} />
            </span>
          </li>
        ));
      })}
    </ul>
  );
}

const LINK = "cursor-pointer font-medium text-primary-text underline underline-offset-4 hover:no-underline disabled:cursor-default disabled:opacity-50";

/** El arreglo de un hallazgo, como enlace en línea: conectar, ir a la ficha, abrir el bloque o aplicar la propuesta. */
function FindingFix({
  refId,
  finding,
  source,
  canWrite,
  onEdit,
  onConnect,
}: {
  refId: string;
  finding: ReviewFinding;
  source: ReviewSource;
  canWrite: boolean;
  onEdit: (pointer: string | null) => void;
  onConnect?: (integration: string) => void;
}) {
  const t = useT();
  const fix = finding.fix;
  if (!fix) return null;
  if (fix.kind === "link") {
    if (fix.target === "integrations" && typeof fix.integration === "string" && onConnect) {
      const integration = fix.integration;
      return (
        <button type="button" className={LINK} onClick={() => onConnect(integration)}>
          {t("builder.connect", { name: integrationName(integration) })}
        </button>
      );
    }
    const link = reviewFixLink(refId, fix);
    return link ? (
      <Link href={link.href} className={LINK}>
        {t(link.label)}
      </Link>
    ) : null;
  }
  if (!canWrite) return null;
  if (fix.kind === "edit") {
    return (
      <button type="button" className={LINK} onClick={() => onEdit(fix.pointer ?? finding.pointer ?? null)}>
        {t("builder.review.fix.edit")}
      </button>
    );
  }
  return (
    <button
      type="button"
      className={LINK}
      disabled={source.applying !== null}
      aria-busy={source.applying === fix.proposal_id || undefined}
      onClick={() => void source.apply(fix.proposal_id)}
    >
      {t("builder.review.fix.apply")}
    </button>
  );
}
