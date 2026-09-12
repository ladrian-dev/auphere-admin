"use client";

/**
 * Spec 005 · R8.4 — llegar a las facturas del proveedor.
 *
 * El recibo de la consola explica el consumo; **la factura del proveedor es el
 * documento fiscal**. Quien la necesita para su contabilidad tiene que poder
 * llegar sin escribir a soporte.
 *
 * Se delega en el portal del proveedor en vez de construir una pantalla de
 * facturas propia. Construirla significaría traer datos de pago a nuestra
 * infraestructura, que es justo lo que la página alojada evita — y además
 * duplicaría un documento que ya existe, con el riesgo de que las dos
 * versiones dejen de coincidir.
 *
 * **No se nombra al proveedor.** Cuál es es un detalle de implementación
 * nuestro; el día que cambie, esta pantalla no tiene por qué cambiar con él.
 */

import { useTransition } from "react";
import { toast } from "sonner";

import { Button } from "@nexus/ui";

import { openPortalAction } from "@/app/(console)/billing/actions";
import { useT } from "@/i18n/client";

export function ProviderInvoicesLink({ hasSubscription }: { hasSubscription: boolean }) {
  const t = useT();
  const [pending, start] = useTransition();

  // Sin suscripción no hay facturas que ver. No se pinta apagado (§V).
  if (!hasSubscription) return null;

  function open() {
    start(async () => {
      const res = await openPortalAction();
      if (!res.ok) {
        toast.error(t("membership.error.unavailable"));
        return;
      }
      window.location.assign(res.data.url);
    });
  }

  return (
    <Button variant="outline" size="sm" disabled={pending} onClick={open}>
      {t("membership.invoices")}
    </Button>
  );
}
