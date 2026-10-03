"use client";

import Link from "next/link";

import { ErrorState } from "@nexus/ui";

import { useT } from "@/i18n/client";

/**
 * El límite de error de las pantallas PRE-SESIÓN.
 *
 * **Faltaba, y el sitio donde más se nota es el que la spec 011 acaba de
 * añadir**: quien abre `/forgot` ya está en apuros, y hasta ahora un fallo del
 * servidor ahí le dejaba en la página de error por defecto de Next —sin
 * reintentar, sin volver, sin nada—. Una pantalla cuyo trabajo entero es
 * recuperar el acceso no puede ser un callejón sin salida.
 *
 * **No enseña `error.message`, a diferencia de `(console)/error.tsx`.** Allí
 * quien mira ya ha demostrado ser alguien; aquí no ha demostrado ser nadie, y
 * `BackendError.message` lleva la URL de la API y un trozo del cuerpo de su
 * respuesta. Lo que se ve es una frase y dos salidas; el `digest` queda en los
 * registros del servidor, que es donde sirve.
 */
export default function AuthError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const t = useT();
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <ErrorState
        title={t("common.error.title")}
        description={t("common.error.backend")}
        onRetry={reset}
        retryLabel={t("common.retry")}
      />
      <Link href="/login" className="text-sm text-muted-foreground underline underline-offset-4">
        {t("forgot.backToLogin")}
      </Link>
    </div>
  );
}
