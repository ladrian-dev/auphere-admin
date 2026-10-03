"use client";

import Link from "next/link";

import { RouteError } from "@/components/error-boundary";
import { useT } from "@/i18n/client";

/**
 * El límite de error de las pantallas PRE-SESIÓN.
 *
 * Faltaba, y donde más se nota es en la pantalla que la spec 011 añade: quien
 * abre `/forgot` ya está en apuros, y un fallo del servidor ahí le dejaba en la
 * página de error por defecto de Next —sin reintentar, sin volver, sin nada—.
 * Una pantalla cuyo trabajo entero es recuperar el acceso no puede ser un
 * callejón sin salida, así que lleva la vuelta a la entrada además del
 * reintento.
 *
 * Es el único límite que pasa `showMessage={false}`: aquí quien mira todavía no
 * ha demostrado ser nadie, y el mensaje del fallo lleva la URL de la API.
 */
export default function AuthError(props: { error: Error & { digest?: string }; reset: () => void }) {
  const t = useT();
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <RouteError {...props} showMessage={false} />
      <Link href="/login" className="text-sm text-muted-foreground underline underline-offset-4">
        {t("forgot.backToLogin")}
      </Link>
    </div>
  );
}
