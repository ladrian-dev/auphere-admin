import { Eye, EyeOff } from "lucide-react";

/**
 * Mostrar/ocultar la contraseña — specs 066 (R4.1) y 067 (R4.3). Va dentro de
 * un `relative` junto al campo, fuera de `FormControl`, para que el
 * `aria-describedby` del error siga en el campo.
 */
export function PasswordToggle({
  shown,
  onToggle,
  showLabel,
  hideLabel,
}: {
  shown: boolean;
  onToggle: () => void;
  showLabel: string;
  hideLabel: string;
}) {
  return (
    <button
      type="button"
      className="absolute inset-y-0 right-0 grid w-10 place-items-center rounded-r-md text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ring"
      aria-label={shown ? hideLabel : showLabel}
      aria-pressed={shown}
      onClick={onToggle}
    >
      {shown ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
    </button>
  );
}
