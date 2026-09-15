"use client";

import { useT } from "@/i18n/client";

/**
 * El código que lleva la sesión a la aplicación — spec 009, R3.1.
 *
 * **Lo importante no es el código: es la instrucción.** Quien llega aquí acaba
 * de entrar con Google en su navegador y no entiende por qué no está ya dentro
 * de la aplicación. Enseñar ocho caracteres sin decir qué hacer con ellos es un
 * callejón.
 *
 * Se parte en dos grupos porque así se dicta en voz alta y así se teclea sin
 * equivocarse — el mismo formato que el código de emparejamiento.
 *
 * `code: null` significa que no se pudo emitir. **No se finge uno** (§V: la
 * ausencia se diseña): se dice, y se ofrece volver a intentarlo.
 */
export function DesktopCode({ code }: { code: string | null }) {
  const t = useT();
  const grouped = code ? `${code.slice(0, 4)}-${code.slice(4)}` : null;

  return (
    <div className="flex flex-col items-center gap-6 py-10" role="status">
      {grouped ? (
        <>
          <p className="max-w-prose text-center text-sm text-pretty text-muted-foreground">
            {t("desktopCode.what")}
          </p>
          <p className="font-mono text-4xl tracking-[0.2em] tabular-nums" aria-label={t("desktopCode.aria")}>
            {grouped}
          </p>
          <p className="max-w-prose text-center text-sm text-pretty text-muted-foreground">
            {t("desktopCode.expiry")}
          </p>
        </>
      ) : (
        <p className="max-w-prose text-center text-sm text-pretty text-muted-foreground">
          {t("desktopCode.failed")}
        </p>
      )}
    </div>
  );
}
