/**
 * El aviso de conexión — spec 010, Requisitos 3.1 y 3.3.
 *
 * Un banner de vista, que es lo que la taxonomía pide para algo que afecta a
 * toda la pantalla y dura mientras dura: no un aviso efímero que se va antes de
 * que la persona entienda por qué la aplicación no responde, ni un diálogo que
 * la interrumpe por algo que se va a arreglar solo.
 *
 * Dice **desde cuándo**, porque no es lo mismo un parpadeo de wifi que media
 * hora sin línea, y ofrece reintentar aunque el sistema ya reintente por su
 * cuenta: mirar una pantalla que dice «sin conexión» sin poder hacer nada es
 * justo lo que hace que alguien reinicie la aplicación.
 */
import { Button } from "@nexus/ui";

import type { ConnectivityView } from "../bridge";
import { useAppT } from "../i18n";

export function ConnectionBanner({
  connectivity,
  onRetry,
}: {
  connectivity: ConnectivityView | null;
  onRetry: () => void;
}) {
  const t = useAppT();
  // Con conexión no se dice nada: la ausencia se diseña (§V).
  if (!connectivity || connectivity.state === "online") return null;

  return (
    <div
      role="status"
      className="flex items-center gap-3 border-b border-border bg-muted px-4 py-2"
      data-connectivity={connectivity.state}
    >
      <p className="min-w-0 flex-1 text-ui text-pretty text-muted-foreground">
        {t(connectivity.state === "offline" ? "conn.offline" : "conn.unconfirmed")}
      </p>
      <Button size="sm" variant="outline" onClick={onRetry}>
        {t("conn.retry")}
      </Button>
    </div>
  );
}
