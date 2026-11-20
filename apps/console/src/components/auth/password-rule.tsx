import { Check, Circle } from "lucide-react";

/**
 * Una regla de contraseña que se marca mientras se escribe — specs 066 (R5.2)
 * y 067 (R4.3). Icono y texto, nunca solo color; el estado también se dice en
 * texto para los lectores de pantalla.
 */
export function PasswordRule({ ok, label, met, unmet }: { ok: boolean; label: string; met: string; unmet: string }) {
  return (
    <li
      data-ok={ok ? "" : undefined}
      className={ok ? "flex items-center gap-2 text-foreground" : "flex items-center gap-2 text-muted-foreground"}
    >
      {ok ? <Check className="size-4 shrink-0 text-primary" aria-hidden /> : <Circle className="size-4 shrink-0" aria-hidden />}
      <span>
        {label}
        <span className="sr-only">: {ok ? met : unmet}</span>
      </span>
    </li>
  );
}
