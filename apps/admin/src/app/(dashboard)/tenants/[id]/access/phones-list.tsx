// Imported only by `members-list.tsx`, a client component: no "use client" of
// its own, so its callback props need not be serializable.
import { Smartphone } from "lucide-react";
import { useCallback, useEffect, useState, useTransition } from "react";
import { toast } from "sonner";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import type { ClientMemberOut, ClientPhoneOut } from "@/lib/backend";
import { relativeTime } from "@/lib/format";

import { closePhoneAction, listPhonesAction } from "./actions";
import { PHONE_REASONS } from "./messages";

const PLATFORM: Record<ClientPhoneOut["platform"], string> = { ios: "iPhone", android: "Android" };

type Load = { state: "loading" } | { state: "error"; error: string } | { state: "ready"; phones: ClientPhoneOut[] };

/**
 * Spec 031 (R7.4): the phones of one client person, inside the access tab.
 * The operator sees the signed-in ones and the last closed ones (with why),
 * and can close one — a lost phone, say — after a confirmation in the row
 * itself. Closing is audited with this operator by the API.
 */
export function PhonesDialog({
  tenantId,
  member,
  onClose,
}: {
  tenantId: string;
  /** Mounted per person (`key={member.id}`): its state starts fresh for each one. */
  member: ClientMemberOut;
  onClose: () => void;
}) {
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [confirming, setConfirming] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const memberId = member.id;

  const fetchPhones = useCallback(
    () =>
      listPhonesAction(tenantId, memberId).then((res) =>
        setLoad(res.ok ? { state: "ready", phones: res.data } : { state: "error", error: res.error }),
      ),
    [tenantId, memberId],
  );

  useEffect(() => {
    void fetchPhones();
  }, [fetchPhones]);

  function retry() {
    setLoad({ state: "loading" });
    void fetchPhones();
  }

  function close(phone: ClientPhoneOut) {
    setFailed(null);
    startTransition(async () => {
      const res = await closePhoneAction(tenantId, memberId, phone.id);
      setConfirming(null);
      if (!res.ok) {
        setFailed(`No se pudo cerrar «${phone.display_name}»: ${res.error}`);
        return;
      }
      toast.success(`«${phone.display_name}» ya no tiene sesión`);
      await fetchPhones();
    });
  }

  return (
    <Dialog open onOpenChange={(open) => (open ? undefined : onClose())}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Teléfonos</DialogTitle>
          <DialogDescription className="break-words">
            Dónde tiene {member.email} la sesión abierta en Auphere Customers.
          </DialogDescription>
        </DialogHeader>

        {failed ? (
          <Alert variant="destructive">
            <AlertDescription>{failed}</AlertDescription>
          </Alert>
        ) : null}

        {load.state === "loading" ? (
          <div aria-busy="true" aria-label="Cargando teléfonos" className="grid gap-2">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : load.state === "error" ? (
          <Alert variant="destructive">
            <AlertDescription className="grid gap-2">
              <span>No se pudieron leer los teléfonos: {load.error}</span>
              <Button size="sm" variant="outline" className="justify-self-start" onClick={retry}>
                Reintentar
              </Button>
            </AlertDescription>
          </Alert>
        ) : load.phones.length === 0 ? (
          <div role="status" className="grid place-items-center gap-2 rounded-md border border-dashed border-border px-4 py-8 text-center">
            <Smartphone className="size-5 text-muted-foreground" aria-hidden="true" />
            <p className="text-sm font-medium">No ha entrado desde ningún teléfono</p>
            <p className="text-xs text-pretty text-muted-foreground">
              Aparecerá aquí en cuanto entre en Auphere Customers con este correo.
            </p>
          </div>
        ) : (
          <ul aria-label={`Teléfonos de ${member.email}`} className="grid divide-y divide-border rounded-md border border-border">
            {load.phones.map((phone) => {
              const open = phone.revoked_at === null;
              const reason = phone.revoked_reason ? (PHONE_REASONS[phone.revoked_reason] ?? phone.revoked_reason) : null;
              const byOperator = phone.revoked_by?.startsWith("operator:") ? phone.revoked_by.slice("operator:".length) : null;
              return (
                <li key={phone.id} className="grid gap-2 px-3 py-3">
                  <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0 flex-1 basis-40">
                      <p className="truncate text-sm font-medium" title={phone.display_name}>
                        {phone.display_name}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {PLATFORM[phone.platform]} · {phone.app_version} · último uso {relativeTime(phone.last_seen_at)}
                      </p>
                      {!open ? (
                        <p className="text-xs text-pretty text-muted-foreground">
                          Cerrado {relativeTime(phone.revoked_at)}
                          {reason ? ` · ${reason}` : ""}
                          {byOperator ? ` · ${byOperator}` : ""}
                        </p>
                      ) : null}
                    </div>
                    {open ? (
                      <Badge variant="default">Con sesión</Badge>
                    ) : (
                      <Badge variant="outline">Cerrado</Badge>
                    )}
                  </div>
                  {open && confirming !== phone.id ? (
                    <Button
                      size="sm"
                      variant="outline"
                      className="justify-self-start"
                      disabled={pending}
                      onClick={() => setConfirming(phone.id)}
                      aria-label={`Cerrar el teléfono «${phone.display_name}»`}
                    >
                      Cerrar teléfono
                    </Button>
                  ) : null}
                  {open && confirming === phone.id ? (
                    <div role="group" aria-label="Confirmar" className="grid gap-2 rounded-md bg-muted/50 p-3">
                      <p className="text-xs text-pretty">
                        Deja de ver el negocio y de recibir avisos ahora mismo. Para volver, la persona tiene que entrar otra vez.
                      </p>
                      <div className="flex flex-wrap gap-2">
                        <Button size="sm" variant="outline" disabled={pending} onClick={() => setConfirming(null)} autoFocus>
                          Cancelar
                        </Button>
                        <Button size="sm" variant="destructive" disabled={pending} onClick={() => close(phone)}>
                          Sí, cerrar teléfono
                        </Button>
                      </div>
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  );
}
