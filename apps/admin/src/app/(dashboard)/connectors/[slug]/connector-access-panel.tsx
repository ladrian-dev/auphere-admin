"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import {
  Button,
  Field,
  NativeSelect,
  StatusDot,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@nexus/ui";

import {
  setConnectorDefaultAction,
  setConnectorPartnerStateAction,
} from "@/app/(dashboard)/connectors/access-actions";
import { AccessChangeDialog } from "@/components/connectors/access-change-dialog";
import type { ConnectorAccess, PartnerConnectorState } from "@/lib/backend-connector-access";

type Change =
  | { kind: "default"; enabled: boolean }
  | { kind: "partner"; partnerId: string; partnerName: string; state: PartnerConnectorState };

function clients(n: number): string {
  return n === 0 ? "Ninguno" : n === 1 ? "1 cliente" : `${n} clientes`;
}

function when(iso: string | null): string {
  return iso ? new Date(iso).toLocaleDateString("es-ES", { day: "numeric", month: "short", year: "numeric" }) : "";
}

/**
 * Spec 060 (requisito 3): la vista por conector. El valor por defecto para los
 * partners y los partners con decisión propia. Escribe lo mismo que la ficha del
 * partner (3.3). Para dejar un conector solo para un partner: valor por defecto
 * «Deshabilitado» y ese partner «Habilitado».
 */
export function ConnectorAccessPanel({
  slug,
  name,
  access,
  partners,
}: {
  slug: string;
  name: string;
  access: ConnectorAccess;
  partners: { id: string; name: string }[];
}) {
  const router = useRouter();
  const [change, setChange] = React.useState<Change | null>(null);
  // El diálogo se anima al cerrarse: mientras tanto sigue diciendo lo mismo.
  const [shown, setShown] = React.useState<Change | null>(null);
  // El control que abrió el diálogo, para devolverle el foco al cerrarlo.
  const opener = React.useRef<HTMLElement | null>(null);
  // Guardar puede quitar la fila (vuelve al valor por defecto) o el formulario (ya no
  // queda partner sin decisión) que abrió el diálogo. Cuando llegan los datos nuevos,
  // si el foco se quedó sin sitio, va al valor por defecto, que siempre está.
  const defaultSelect = React.useRef<HTMLSelectElement | null>(null);
  const refocus = React.useRef(false);
  React.useEffect(() => {
    if (!refocus.current) return;
    refocus.current = false;
    const lost = document.activeElement === null || document.activeElement === document.body;
    if (lost) defaultSelect.current?.focus();
  }, [access]);
  const ask = (next: Change, from: HTMLElement | null) => {
    opener.current = from;
    setShown(next);
    setChange(next);
  };
  const decided = new Set(access.partners.map((p) => p.partner_id));
  const undecided = partners.filter((p) => !decided.has(p.id));
  const [newPartner, setNewPartner] = React.useState("");
  const [newState, setNewState] = React.useState<"enabled" | "disabled">(
    access.default_enabled ? "disabled" : "enabled",
  );

  const title =
    shown === null
      ? ""
      : shown.kind === "default"
        ? `${name}: ${shown.enabled ? "habilitado" : "deshabilitado"} por defecto`
        : `${name} para ${shown.partnerName}: ${
            shown.state === "default"
              ? "como el valor por defecto"
              : shown.state === "enabled"
                ? "habilitado"
                : "deshabilitado"
          }`;
  const description =
    shown === null
      ? ""
      : shown.kind === "default"
        ? shown.enabled
          ? "Todos los partners sin decisión propia podrán ofrecerlo a sus clientes."
          : "Ningún partner sin decisión propia podrá ofrecerlo, tampoco los que se den de alta después. Los clientes sin partner tampoco."
        : shown.state === "disabled"
          ? "Los clientes de este partner dejarán de verlo y sus agentes no podrán usarlo."
          : shown.state === "enabled"
            ? "Los clientes de este partner podrán conectarlo y usarlo, sea cual sea el valor por defecto."
            : "Este partner volverá a seguir el valor por defecto.";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-1">
          <span className="inline-flex items-center gap-2 text-sm font-medium">
            <StatusDot tone={access.default_enabled ? "positive" : "muted"} />
            {access.default_enabled
              ? "Por defecto, disponible para todos los partners"
              : "Por defecto, no disponible para ningún partner"}
          </span>
          <span className="text-xs text-muted-foreground text-pretty">
            {access.partners_without_decision === 1
              ? "1 partner sigue el valor por defecto."
              : `${access.partners_without_decision} partners siguen el valor por defecto.`}
            {access.default_reason ? ` Motivo: ${access.default_reason}` : ""}
          </span>
        </div>
        <Field label="Valor por defecto" className="w-56">
          {(a11y) => (
            <NativeSelect
              {...a11y}
              ref={defaultSelect}
              size="sm"
              value={access.default_enabled ? "enabled" : "disabled"}
              onChange={(e) => {
                const enabled = e.target.value === "enabled";
                if (enabled !== access.default_enabled) ask({ kind: "default", enabled }, e.currentTarget);
              }}
            >
              <option value="enabled">Habilitado</option>
              <option value="disabled">Deshabilitado</option>
            </NativeSelect>
          )}
        </Field>
      </div>

      {access.partners.length > 0 ? (
        <div className="overflow-x-auto rounded-md ring-1 ring-foreground/10">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Partner</TableHead>
                <TableHead>Para sus clientes</TableHead>
                <TableHead>Conectados</TableHead>
                <TableHead className="w-56">Decisión</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {access.partners.map((p) => (
                <TableRow key={p.partner_id}>
                  <TableCell>
                    <Link
                      href={`/partners/${p.partner_id}/connectors`}
                      className="inline-flex min-h-6 items-center font-medium hover:underline"
                    >
                      {p.name}
                    </Link>
                  </TableCell>
                  <TableCell className="max-w-xs whitespace-normal">
                    <span className="inline-flex items-center gap-2">
                      <StatusDot tone={p.effective ? "positive" : "muted"} />
                      {p.effective ? "Disponible" : "No disponible"}
                    </span>
                    <span className="block text-xs text-muted-foreground text-pretty wrap-anywhere">
                      {p.reason} · {when(p.set_at)}
                    </span>
                  </TableCell>
                  <TableCell className="tabular-nums">{clients(p.connected_clients)}</TableCell>
                  <TableCell>
                    <NativeSelect
                      aria-label={`Decisión para ${p.name}`}
                      size="sm"
                      // Sin ancho propio, la tabla lo encoge hasta no leerse en un móvil.
                      wrapperClassName="w-44"
                      value={p.state}
                      onChange={(e) => {
                        const state = e.target.value as PartnerConnectorState;
                        if (state !== p.state) {
                          ask(
                            { kind: "partner", partnerId: p.partner_id, partnerName: p.name, state },
                            e.currentTarget,
                          );
                        }
                      }}
                    >
                      <option value="enabled">Habilitado</option>
                      <option value="disabled">Deshabilitado</option>
                      <option value="default">Por defecto</option>
                    </NativeSelect>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">Ningún partner tiene una decisión propia sobre este conector.</p>
      )}

      {undecided.length > 0 ? (
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            const partner = undecided.find((p) => p.id === newPartner);
            if (partner) {
              // Al guardar, el botón queda deshabilitado: el foco vuelve al selector de partner.
              ask(
                { kind: "partner", partnerId: partner.id, partnerName: partner.name, state: newState },
                e.currentTarget.querySelector("select"),
              );
            }
          }}
        >
          <Field label="Decidir para un partner" className="w-64">
            {(a11y) => (
              <NativeSelect {...a11y} size="sm" value={newPartner} onChange={(e) => setNewPartner(e.target.value)}>
                <option value="">Elige un partner</option>
                {undecided.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Para sus clientes" className="w-44">
            {(a11y) => (
              <NativeSelect
                {...a11y}
                size="sm"
                value={newState}
                onChange={(e) => setNewState(e.target.value as "enabled" | "disabled")}
              >
                <option value="enabled">Habilitado</option>
                <option value="disabled">Deshabilitado</option>
              </NativeSelect>
            )}
          </Field>
          <Button type="submit" variant="outline" size="sm" disabled={newPartner === ""}>
            Añadir decisión
          </Button>
        </form>
      ) : null}

      <AccessChangeDialog
        open={change !== null}
        onOpenChange={(open) => !open && setChange(null)}
        title={title}
        description={description}
        confirmLabel="Guardar"
        doneLabel="Disponibilidad guardada"
        returnFocus={() => opener.current}
        submit={(reason, confirm) =>
          change!.kind === "default"
            ? setConnectorDefaultAction(slug, { enabled: change!.enabled, reason, confirm })
            : setConnectorPartnerStateAction(slug, change!.partnerId, { state: change!.state, reason, confirm })
        }
        onDone={() => {
          setChange(null);
          setNewPartner("");
          refocus.current = true;
          router.refresh();
        }}
      />
    </div>
  );
}
