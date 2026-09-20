/**
 * El panel de entorno — spec 003, Requisito 11.
 *
 * Dice **dónde** trabaja el teammate: en qué máquina, en qué directorio del
 * cliente, y qué nombraron los comandos de la tarea abierta. Tres decisiones
 * que se ven en el código:
 *
 * * `archivos` se llama «lo que los comandos nombraron» y no «Archivos». No es
 *   un listado del directorio: la plataforma nunca sabe qué ficheros se
 *   escribieron (§III) y la aplicación no mira el disco para adivinarlo.
 *   Titularlo «Archivos» prometería algo que nadie puede cumplir.
 * * `navegador` es una ausencia diseñada: una frase. Ni botón apagado ni error.
 * * Sin máquina o sin directorio, se **lleva** a la puesta en marcha de la 002
 *   en vez de repetirla aquí. Dos sitios donde emparejar es uno que miente.
 */
import { Button } from "@nexus/ui";
import { useEffect, useState } from "react";

import { type ExecMode, type LocalExecPolicy, type Teammate, bridge } from "../bridge";
import { InlineNotice, useFeedback } from "../feedback/provider";
import { useAppT } from "../i18n";

export type ThreadEnv = {
  machine: { displayName: string; hostname: string } | null;
  presence: "presente" | "ausente";
  links: Array<{ clientRef: string; clientName: string | null; workdir: string | null }>;
  task_id: string | null;
  files: string[];
};

export type EnvPanelProps = {
  teammate: Teammate | null;
  /** `null` mientras no se ha preguntado a la máquina. No se inventa nada. */
  env: ThreadEnv | null;
  policy: LocalExecPolicy | null;
  onOpenConsole: (path: string) => void;
};

/** Donde vive la puesta en marcha de la máquina (spec 002). */
const WORKSTATION = "/workstation";

export function EnvPanel({ teammate, env, policy, onOpenConsole }: EnvPanelProps) {
  const t = useAppT();
  const link = env?.links[0] ?? null;
  const missingMachine = env !== null && env.machine === null;
  const missingWorkdir = env !== null && env.machine !== null && (link === null || link.workdir === null);

  return (
    /*
     * **Ancho fijo, y se retira cuando no cabe.** Sin ancho declarado este
     * panel se dimensionaba a su contenido —y su contenido son rutas como
     * `/Users/adrian/Trabajo/clientes/clinica-boreal-2026/analitica`—, así que
     * se quedaba con lo que quisiera y el hilo con lo que sobrara: **311 px de
     * 1280, y 32 px en la ventana mínima**. El chat, que es el producto,
     * cabía letra a letra.
     *
     * Por debajo de `xl` desaparece en vez de encogerse. Es una pérdida real
     * —el directorio y la máquina dejan de verse— y aun así es estrictamente
     * mejor que un chat de 32 px. El panel plegable con su control vive en la
     * 013, que es donde se decide la conversación como producto.
     */
    <aside
      className="hidden w-80 shrink-0 flex-col gap-4 overflow-y-auto border-l border-border p-4 xl:flex"
      aria-label={t("env.title")}
    >
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
          {env ? (
            <>
              <dt className="text-muted-foreground">{t("env.machine")}</dt>
              <dd className="min-w-0 text-pretty">
                {env.machine ? (
                  <>
                    <span className="break-all">{env.machine.displayName}</span>
                    {env.presence === "ausente" ? (
                      <span className="text-muted-foreground"> · {t("env.machine.absent")}</span>
                    ) : null}
                  </>
                ) : (
                  <span className="text-muted-foreground">{t("env.machine.none")}</span>
                )}
              </dd>
              {link ? (
                <>
                  <dt className="text-muted-foreground">{t("env.client")}</dt>
                  <dd className="min-w-0 truncate" title={link.clientName ?? link.clientRef}>
                    {link.clientName ?? link.clientRef}
                  </dd>
                  <dt className="text-muted-foreground">{t("env.workdir")}</dt>
                  <dd className="min-w-0 text-pretty">
                    {link.workdir ? (
                      <span className="font-mono text-xs break-all">{link.workdir}</span>
                    ) : (
                      <span className="text-muted-foreground">{t("env.workdir.none")}</span>
                    )}
                  </dd>
                </>
              ) : null}
            </>
          ) : null}
        </dl>
      ) : null}

      {missingMachine || missingWorkdir ? (
        <section className="flex min-w-0 flex-col items-start gap-2" aria-label={t("env.setup.title")}>
          <p className="text-sm text-pretty text-muted-foreground">
            {t(missingMachine ? "env.setup.noMachine" : "env.setup.noWorkdir")}
          </p>
          <Button variant="outline" size="sm" onClick={() => onOpenConsole(WORKSTATION)}>
            {t("env.setup.open")}
          </Button>
        </section>
      ) : null}

      {env && env.files.length > 0 ? (
        <section className="flex min-w-0 flex-col gap-1" aria-label={t("env.files.title")}>
          <h3 className="text-sm font-semibold text-balance">{t("env.files.title")}</h3>
          <ul className="flex min-w-0 flex-col gap-1">
            {env.files.map((file) => (
              <li key={file} className="min-w-0 truncate font-mono text-xs text-muted-foreground" title={file}>
                {file}
              </li>
            ))}
          </ul>
          <p className="text-xs text-pretty text-muted-foreground">{t("env.files.hint")}</p>
        </section>
      ) : null}

      {teammate?.local_exec ? <LocalExecPolicySection initial={policy} /> : null}

      <p className="text-sm text-pretty text-muted-foreground">{t("env.browser.soon")}</p>
      <Button variant="outline" size="sm" onClick={() => onOpenConsole("/")}>
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
const POLICY_SLOT = "env.policy";

/** Exportada para poder comprobar que guardar **no falla en silencio** (R5.3). */
export function LocalExecPolicySection({ initial }: { initial: LocalExecPolicy | null }) {
  const t = useAppT();
  const { notify, clear } = useFeedback();
  const [policy, setPolicy] = useState<LocalExecPolicy | null>(initial);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (initial) {
      setPolicy(initial);
      return;
    }
    void bridge.policyPrefs().then((res) => {
      if (res.ok) setPolicy(res.data);
    });
  }, [initial]);

  if (policy === null) return null;

  /*
   * R5.3. Guardar fallaba en silencio: el botón se quedaba donde estaba y la
   * persona se iba creyendo que había cambiado su política de ejecución — que
   * es de las pocas preferencias que deciden si algo toca tu máquina.
   */
  const save = async (mode: ExecMode) => {
    setSaving(true);
    clear(POLICY_SLOT);
    const saved = await bridge.policySetPref({ executable: null, mode });
    setSaving(false);
    if (saved.ok) {
      setPolicy(saved.data);
      return;
    }
    notify({
      severidad: "error",
      alcance: "elemento",
      urgencia: "diferible",
      slot: POLICY_SLOT,
      clave: "feedback.policy.failed",
    });
  };

  return (
    <section className="flex min-w-0 flex-col gap-2" aria-label={t("policy.title")}>
      <h3 className="text-sm font-semibold text-balance">{t("policy.title")}</h3>
      {/*
        Spec 010 R11 — esto es **una elección entre tres**, no tres
        interruptores. Como `aria-pressed` suelto, un lector de pantalla decía
        «botón, no presionado» tres veces y nunca que elegir uno apaga los
        otros. Con `radiogroup` se anuncia «1 de 3» y las flechas funcionan,
        que es lo que espera quien no usa ratón.
      */}
      <div role="radiogroup" aria-label={t("policy.title")} className="flex flex-wrap gap-1">
        {(["ask", "always", "never"] as const).map((mode, index, todos) => (
          <button
            key={mode}
            type="button"
            role="radio"
            aria-checked={policy.global_mode === mode}
            // Tabulación itinerante: el grupo entra y sale con **una** parada,
            // y dentro se recorre con las flechas (patrón ARIA de radios).
            tabIndex={policy.global_mode === mode ? 0 : -1}
            disabled={saving}
            onClick={() => void save(mode)}
            onKeyDown={(event) => {
              const paso = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 0;
              if (paso === 0) return;
              event.preventDefault();
              void save(todos[(index + paso + todos.length) % todos.length]!);
            }}
            className="min-h-6 rounded-md border border-border px-3 py-1 text-xs transition-colors hover:bg-muted aria-[checked=true]:bg-foreground aria-[checked=true]:text-background"
          >
            {t(`policy.${mode}`)}
          </button>
        ))}
      </div>
      <InlineNotice slot={POLICY_SLOT} />
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
