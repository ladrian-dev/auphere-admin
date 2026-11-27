import Link from "next/link";

import { EmptyState } from "@nexus/ui";

/**
 * El cliente existe pero no tiene agente (spec 082, requisito 1.1).
 *
 * Una rutina cuelga de un agente. Sin ninguno no hay a quién vincularla, y
 * enseñar la lista vacía dejaría que alguien abriera el alta para encontrarse
 * un desplegable sin opciones. La salida es la ficha del cliente, que es donde
 * se crea el agente.
 */
export function NoAgentState({
  title,
  body,
  action,
  href,
}: {
  title: string;
  body: string;
  action: string;
  href: string;
}) {
  return (
    <EmptyState
      title={title}
      description={body}
      action={
        <Link href={href} className="rounded-md border px-3 py-2 text-sm font-medium">
          {action}
        </Link>
      }
    />
  );
}
