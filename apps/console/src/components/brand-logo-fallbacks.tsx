import { Link2 } from "lucide-react";

/** LinkedIn salió de Simple Icons por sus normas de marca: un enlace sobre su azul. */
export function Linkedin({ size }: { size: number }) {
  return <Link2 width={size} height={size} aria-hidden="true" />;
}
