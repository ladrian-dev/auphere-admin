"use client";

import { Plug } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import {
  EmptyState,
  NativeSelect,
  StatusDot,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@nexus/ui";

import { setConnectorPartnerStateAction } from "@/app/(dashboard)/connectors/access-actions";
import { ConnectorLogo } from "@/components/brand/connector-logo";
import { AccessChangeDialog } from "@/components/connectors/access-change-dialog";
import type { ConnectorAuthKind } from "@/lib/backend";
import type { PartnerConnector, PartnerConnectorState } from "@/lib/backend-connector-access";

const STATE_LABEL: Record<PartnerConnectorState, string> = {
  enabled: "Habilitado",
  disabled: "Deshabilitado",
  default: "Como el valor por defecto",
};

function defaultText(enabled: boolean): string {
  return enabled ? "habilitado" : "deshabilitado";
}

function clients(n: number): string {
  return n === 0 ? "Ninguno" : n === 1 ? "1 cliente" : `${n} clientes`;
}

type Pending = { item: PartnerConnector; state: PartnerConnectorState };

/**
 * Spec 060 (requisito 2): la vista por partner. Cada fila dice si sus clientes
 * pueden usar el conector y de dónde sale: del valor por defecto del conector o de
 * una decisión para este partner. Cambiarlo pide un motivo, y quitarlo a clientes
 * que lo tienen conectado pide confirmar viendo a quién afecta.
 */
export function PartnerConnectorsList({
  partnerId,
  items,
}: {
  partnerId: string;
  items: PartnerConnector[];
}) {
  const router = useRouter();
  const [pending, setPending] = React.useState<Pending | null>(null);
  // El diálogo se anima al cerrarse: mientras tanto sigue diciendo lo mismo.
  const [shown, setShown] = React.useState<Pending | null>(null);
  // El selector que abrió el diálogo, para devolverle el foco al cerrarlo.
  const opener = React.useRef<HTMLElement | null>(null);
  const ask = (next: Pending, from: HTMLElement) => {
    opener.current = from;
    setShown(next);
    setPending(next);
  };

  if (items.length === 0) {
    return (
      <EmptyState
        icon={Plug}
        title="No hay conectores en el catálogo"
        description="Cuando Auphere publique uno, aparecerá aquí con su disponibilidad para este partner."
        readonly
      />
    );
  }

  return (
    <>
      <div className="overflow-x-auto rounded-md ring-1 ring-foreground/10">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Conector</TableHead>
              <TableHead>Para sus clientes</TableHead>
              <TableHead>Conectados</TableHead>
              <TableHead className="w-64">Decisión</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.slug}>
                <TableCell>
                  <Link
                    href={`/connectors/${encodeURIComponent(item.slug)}`}
                    className="flex min-w-0 items-center gap-3 font-medium hover:underline"
                  >
                    <ConnectorLogo
                      connector={{
                        slug: item.slug,
                        display_name: item.display_name,
                        auth_kind: item.auth_kind as ConnectorAuthKind,
                        provider_meta: {},
                      }}
                      size="sm"
                    />
                    <span className="truncate">{item.display_name}</span>
                  </Link>
                </TableCell>
                <TableCell className="max-w-xs whitespace-normal">
                  <span className="inline-flex items-center gap-2">
                    <StatusDot tone={item.effective ? "positive" : "muted"} />
                    {item.effective ? "Disponible" : "No disponible"}
                  </span>
                  <span className="block text-xs text-pretty wrap-anywhere text-muted-foreground">
                    {item.partner_state === "default"
                      ? `Por defecto (${defaultText(item.default_enabled)})`
                      : `Decidido para este partner${item.reason ? `: ${item.reason}` : ""}`}
                  </span>
                </TableCell>
                <TableCell className="tabular-nums">{clients(item.connected_clients)}</TableCell>
                <TableCell>
                  <NativeSelect
                    aria-label={`Decisión sobre ${item.display_name} para este partner`}
                    value={item.partner_state}
                    size="sm"
                    // Sin ancho propio, la tabla lo encoge hasta no leerse en un móvil.
                    wrapperClassName="w-52"
                    onChange={(e) => {
                      const state = e.target.value as PartnerConnectorState;
                      if (state !== item.partner_state) ask({ item, state }, e.currentTarget);
                    }}
                  >
                    <option value="default">{`Por defecto (${defaultText(item.default_enabled)})`}</option>
                    <option value="enabled">{STATE_LABEL.enabled}</option>
                    <option value="disabled">{STATE_LABEL.disabled}</option>
                  </NativeSelect>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <AccessChangeDialog
        open={pending !== null}
        onOpenChange={(open) => !open && setPending(null)}
        title={shown ? `${shown.item.display_name}: ${STATE_LABEL[shown.state].toLowerCase()}` : ""}
        description={
          shown?.state === "disabled"
            ? "Los clientes de este partner dejarán de ver este conector en su consola y sus agentes no podrán usarlo."
            : shown?.state === "enabled"
              ? "Los clientes de este partner podrán conectarlo y usarlo, sea cual sea el valor por defecto."
              : "Este partner seguirá lo que diga el valor por defecto del conector."
        }
        confirmLabel="Guardar"
        doneLabel="Disponibilidad guardada"
        returnFocus={() => opener.current}
        submit={(reason, confirm) =>
          setConnectorPartnerStateAction(pending!.item.slug, partnerId, {
            state: pending!.state,
            reason,
            confirm,
          })
        }
        onDone={() => {
          setPending(null);
          router.refresh();
        }}
      />
    </>
  );
}
