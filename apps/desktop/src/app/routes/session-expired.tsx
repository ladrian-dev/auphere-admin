/**
 * La sesión caducada — spec 010, Requisito 3.4.
 *
 * Antes, perder la sesión **cambiaba de superficie**: la ventana saltaba a la
 * consola en `/login` sin decir nada, y lo que la persona estuviera escribiendo
 * desaparecía con el hilo desmontado. Un cierre de sesión en la consola web es
 * un caso normal —caduca, se cierra en otra pestaña—, y aquí se vivía como si
 * la aplicación se hubiera roto.
 *
 * Ahora se dice **en la pantalla en la que está**, se conserva lo escrito y se
 * ofrece entrar. Quien entra vuelve a lo que estaba haciendo.
 */
import { Button } from "@nexus/ui";

import { useAppT } from "../i18n";

export function SessionExpired({
  reason,
  onSignIn,
}: {
  /** `no_membership` es otra cosa: no es que caducara, es que no perteneces. */
  reason: "anonymous" | "no_membership" | undefined;
  onSignIn: () => void;
}) {
  const t = useAppT();
  const sinPartner = reason === "no_membership";

  return (
    <div className="m-auto flex max-w-prose flex-col items-center gap-4 p-8 text-center" role="status">
      <h2 className="text-lg font-semibold">
        {t(sinPartner ? "session.stop.no_membership" : "session.expired.title")}
      </h2>
      {sinPartner ? null : <p className="text-ui text-pretty text-muted-foreground">{t("session.expired.body")}</p>}
      <Button onClick={onSignIn}>{t(sinPartner ? "session.open" : "session.expired.signIn")}</Button>
    </div>
  );
}
