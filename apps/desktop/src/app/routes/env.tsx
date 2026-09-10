/** El panel de entorno (R11): dónde trabaja el teammate. `navegador` es ausencia diseñada. */
import { Button } from "@nexus/ui";
import { useEffect, useState } from "react";

import { type ExecMode, type LocalExecPolicy, type PresencePush, type Teammate, bridge } from "../bridge";
import { useAppT } from "../i18n";

export function EnvPanel({ teammate, presence }: { teammate: Teammate | null; presence: PresencePush | null }) {
  const t = useAppT();
  return (
    <aside className="flex min-w-0 flex-col gap-4 p-4" aria-label={t("env.title")}>
      <h2 className="text-sm font-semibold text-balance">{t("env.title")}</h2>
      {teammate ? (
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-2 text-sm">
          <dt className="text-muted-foreground">{t("env.job")}</dt>
          <dd className="min-w-0 truncate" title={teammate.job}>
            {teammate.job}
          </dd>
          <dt className="text-muted-foreground">{t("env.model")}</dt>
          <dd className="min-w-0 truncate font-mono text-xs" title={teammate.model}>
            {teammate.model}
          </dd>
          <dt className="text-muted-foreground">{t("env.machine")}</dt>
          <dd className="min-w-0 text-pretty">
            {presence?.machine ? (
              <>
                <span className="break-all">{presence.machine.displayName}</span>
                {presence.presence === "ausente" ? <span className="text-muted-foreground"> · {t("env.machine.absent")}</span> : null}
              </>
            ) : (
              <span className="text-muted-foreground">{t("env.machine.none")}</span>
            )}
          </dd>
        </dl>
      ) : null}
      {teammate?.local_exec ? <LocalExecPolicySection /> : null}

      <p className="text-sm text-muted-foreground">{t("env.browser.soon")}</p>
      <Button variant="outline" size="sm" onClick={() => void bridge.openConsole({ path: "/" })}>
        {t("env.openConsole")}
      </Button>
    </aside>
  );
}


/**
 * La política de ejecución local de **esta persona** — Requisitos 8.4 y 10.3.
 *
 * Se enseña donde importa: al lado del teammate que puede ejecutar. Y se
 * enseña entera: lo que elegiste, lo que de verdad se aplica, y quién lo bajó
 * si no coinciden. Enseñar solo lo segundo haría que cambiar la preferencia
 * pareciera que no hace nada.
 */
function LocalExecPolicySection() {
  const t = useAppT();
  const [policy, setPolicy] = useState<LocalExecPolicy | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    void bridge.policyPrefs().then((res) => {
      if (res.ok) setPolicy(res.data);
    });
  }, []);

  if (policy === null) return null;

  const save = async (mode: ExecMode) => {
    setSaving(true);
    const saved = await bridge.policySetPref({ executable: null, mode });
    setSaving(false);
    if (saved.ok) setPolicy(saved.data);
  };

  return (
    <section className="flex min-w-0 flex-col gap-2" aria-label={t("policy.title")}>
      <h3 className="text-sm font-semibold text-balance">{t("policy.title")}</h3>
      <div role="group" aria-label={t("policy.title")} className="flex flex-wrap gap-1">
        {(["ask", "always", "never"] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            aria-pressed={policy.global_mode === mode}
            disabled={saving}
            onClick={() => void save(mode)}
            className="min-h-8 rounded-md border border-border px-2 text-xs transition-colors hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none aria-[pressed=true]:bg-foreground aria-[pressed=true]:text-background"
          >
            {t(`policy.${mode}`)}
          </button>
        ))}
      </div>
      {policy.capped ? (
        <p className="text-xs text-pretty text-muted-foreground" role="note">
          {t("policy.capped", { effective: t(`policy.${policy.effective}`) })}
        </p>
      ) : null}
      {policy.per_executable.length > 0 ? (
        <ul className="flex flex-col gap-1 text-xs text-muted-foreground">
          {policy.per_executable.map((pref) => (
            <li key={pref.executable} className="flex min-w-0 items-center justify-between gap-2">
              <code className="min-w-0 truncate font-mono">{pref.executable}</code>
              <span className="shrink-0">{t(`policy.${pref.effective}`)}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
