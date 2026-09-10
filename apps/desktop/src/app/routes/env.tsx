/** El panel de entorno (R11): dónde trabaja el teammate. `navegador` es ausencia diseñada. */
import { Button } from "@nexus/ui";

import { type PresencePush, type Teammate, bridge } from "../bridge";
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
      <p className="text-sm text-muted-foreground">{t("env.browser.soon")}</p>
      <Button variant="outline" size="sm" onClick={() => void bridge.openConsole({ path: "/" })}>
        {t("env.openConsole")}
      </Button>
    </aside>
  );
}
