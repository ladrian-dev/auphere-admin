/**
 * Entrar — spec 010, Requisitos 7.1, 7.2 y 7.4. Cierra `009-T029`.
 *
 * El flujo por navegador estaba **entero** —PKCE, oyente efímero en
 * `127.0.0.1`, canje contra la consola— y no lo llamaba nadie. En su lugar la
 * ventana decía «Sin sesión. Entra en la consola para ver tu equipo» con un
 * botón a la consola, que llevaba a `/login`, que devolvía a la aplicación sin
 * sesión: un bucle, anotado como tal en el anexo 04.
 *
 * Tres decisiones:
 *
 * * **la entrada ocurre en el navegador y se dice antes**, no después de que la
 *   ventana se quede quieta y la persona se pregunte qué pasó;
 * * **volver a abrir reabre la misma dirección**, no arranca otra entrada:
 *   arrancar otra generaría otro `state` y otro par PKCE, y la pestaña que la
 *   persona tiene delante dejaría de valer sin que nadie se lo dijera;
 * * **ningún formulario de credenciales propio** (R8.7). Aquí hay botones.
 */
import { useState } from "react";

import { Button } from "@nexus/ui";

import { bridge, type SignInView } from "../bridge";
import { type AppKey, useAppT } from "../i18n";

export function SignIn({ state }: { state: SignInView | null }) {
  const t = useAppT();
  const [copiado, setCopiado] = useState(false);
  const fase = state?.state ?? "idle";
  const esperando = fase === "esperando";
  const fallo = fase === "cancelada" || fase === "caducada" || fase === "error";

  return (
    <div className="m-auto flex max-w-prose flex-col items-center gap-4 p-8 text-center">
      <h2 className="text-lg font-semibold text-balance">{t("signin.title")}</h2>
      <p className="text-ui text-pretty text-muted-foreground">
        {esperando ? t("signin.esperando") : fallo ? t(`signin.${fase}` as AppKey) : t("signin.idle")}
      </p>

      {esperando ? (
        <div className="flex flex-wrap items-center justify-center gap-2">
          <Button size="sm" onClick={() => void bridge.signInStart()}>
            {t("signin.reopen")}
          </Button>
          {/* Para pegarla en otro navegador: el del sistema puede no ser donde
              la persona tiene su sesión de Google. */}
          <Button
            size="sm"
            variant="outline"
            disabled={!state?.url}
            onClick={() => {
              if (!state?.url) return;
              void navigator.clipboard?.writeText(state.url);
              setCopiado(true);
            }}
          >
            {copiado ? t("signin.copied") : t("signin.copy")}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => void bridge.signInCancel()}>
            {t("signin.cancel")}
          </Button>
        </div>
      ) : (
        <Button onClick={() => void bridge.signInStart()}>{t(fallo ? "signin.retry" : "signin.start")}</Button>
      )}
    </div>
  );
}
