/**
 * Los directorios de cada cliente — spec 010, Requisito 8.4.
 *
 * El silencio que esto cierra (anexo 04, `bar.ts:219`): elegir un directorio
 * que no valía **se ignoraba**. El selector se cerraba, la lista seguía igual,
 * y la persona se quedaba sin saber si había pulsado mal, si el directorio no
 * valía o si la aplicación estaba rota. Lo irónico es que la validación ya
 * existía, con su motivo — y el motivo se tiraba.
 *
 * Cada uno de los cuatro motivos tiene su frase, porque son cuatro problemas
 * distintos con cuatro arreglos distintos: no existe, no es un directorio,
 * apunta a otro sitio, o no se puede leer.
 */
import { useState } from "react";

import { Button } from "@nexus/ui";

import { bridge } from "../bridge";
import { type AppKey, useAppT } from "../i18n";

export type ClientDirectory = { client_ref: string; name: string | null; workdir: string | null };

export function Directories({
  clients,
  onChanged,
}: {
  clients: readonly ClientDirectory[];
  onChanged: () => void;
}) {
  const t = useAppT();
  const [failed, setFailed] = useState<{ ref: string; reason: string } | null>(null);

  const pick = (clientRef: string) => {
    setFailed(null);
    void bridge.workstationPickDirectory({ client_ref: clientRef }).then((res) => {
      if (res.ok) {
        onChanged();
        return;
      }
      // Cancelar el selector **no es un error**: la persona decidió no elegir,
      // y decirle algo por eso es ruido.
      if (res.code === "cancelled") return;
      setFailed({ ref: clientRef, reason: (res as { reason?: string }).reason ?? "unknown" });
    });
  };

  return (
    <section className="flex min-w-0 flex-col gap-2" aria-label={t("dirs.title")}>
      <h2 className="text-base font-semibold text-balance">{t("dirs.title")}</h2>
      <p className="max-w-prose text-ui text-pretty text-muted-foreground">{t("dirs.body")}</p>
      <ul className="flex flex-col gap-2">
        {clients.map((client) => (
          <li key={client.client_ref} className="flex min-w-0 flex-col gap-1">
            <div className="flex min-w-0 items-center gap-3">
              <span className="min-w-0 flex-1 truncate text-ui">{client.name ?? client.client_ref}</span>
              <span className="min-w-0 shrink truncate font-mono text-xs text-muted-foreground">
                {client.workdir ?? t("dirs.none")}
              </span>
              <Button size="sm" variant="outline" onClick={() => pick(client.client_ref)}>
                {client.workdir ? t("dirs.change") : t("dirs.choose")}
              </Button>
            </div>
            {failed?.ref === client.client_ref ? (
              <p role="alert" className="text-xs text-pretty text-status-danger-text">
                {t(`dirs.invalid.${failed.reason}` as AppKey)}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
