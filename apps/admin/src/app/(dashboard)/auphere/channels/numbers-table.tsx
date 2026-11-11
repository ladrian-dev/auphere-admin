"use client";

import { MoreHorizontal } from "lucide-react";
import { useState } from "react";

import {
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Skeleton,
  StatusBadge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@nexus/ui";
import type { AuphereOwnerChannelOut } from "@/lib/backend";
import { FOCUS_RING_INSET } from "@/lib/focus-ring";

import { ChangeNumberDialog, EditNumberDialog, type NumberChange } from "./number-dialogs";

/**
 * Spec 059 (historia 6; 5.1, 6.1–6.3): Auphere's own numbers. No secret
 * column and no «Rotar secret»: Meta signs with the app's secret. One action
 * in sight per row («Editar»); the rest in «⋯», with «Desactivar» last.
 */
export function NumbersTable({ numbers }: { numbers: AuphereOwnerChannelOut[] }) {
  return (
    <Table>
      <Head />
      <TableBody>
        {numbers.map((n) => (
          <TableRow key={n.id}>
            <TableCell className="whitespace-normal">
              <div className="flex min-w-0 flex-col">
                <span className="font-medium text-pretty break-words">{n.display_name}</span>
                <span className="font-mono text-xs text-muted-foreground">{n.phone_e164}</span>
              </div>
            </TableCell>
            <TableCell className="font-mono text-xs">{n.country_code ?? "—"}</TableCell>
            <TableCell className="font-mono text-xs break-all">
              {n.provider_phone_id ?? <StatusBadge tone="warning">Falta</StatusBadge>}
            </TableCell>
            <TableCell>
              {n.has_access_token ? <StatusBadge tone="muted">Guardado</StatusBadge> : <StatusBadge tone="warning">Falta</StatusBadge>}
            </TableCell>
            <TableCell>
              <div className="flex flex-wrap items-center gap-1">
                {n.active ? <StatusBadge tone="positive">Activo</StatusBadge> : <StatusBadge tone="muted">Desactivado</StatusBadge>}
                {n.is_default ? <StatusBadge tone="info">Principal</StatusBadge> : null}
              </div>
            </TableCell>
            <TableCell className="text-right">
              <NumberActions number={n} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

/** The columns, shared by the table and its skeleton. */
function Head() {
  return (
    <TableHeader>
      <TableRow>
        <TableHead>Número</TableHead>
        <TableHead>País</TableHead>
        <TableHead>Identificador del número en Meta</TableHead>
        <TableHead>Token de Meta</TableHead>
        <TableHead>Estado</TableHead>
        <TableHead className="text-right">
          <span className="sr-only">Acciones</span>
        </TableHead>
      </TableRow>
    </TableHeader>
  );
}

/** The table while the numbers are read: its own columns, and rows as tall as a number's. */
export function NumbersTableSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div role="status" aria-label="Cargando los números">
      <Table aria-hidden="true">
        <Head />
        <TableBody>
          {Array.from({ length: rows }, (_, i) => (
            <TableRow key={i}>
              <TableCell>
                <div className="flex flex-col gap-1">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-3 w-24" />
                </div>
              </TableCell>
              <TableCell>
                <Skeleton className="h-4 w-6" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-4 w-24" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-6 w-20 rounded-full" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-6 w-16 rounded-full" />
              </TableCell>
              <TableCell>
                <div className="flex justify-end gap-1">
                  <Skeleton className="h-8 w-16" />
                  <Skeleton className="size-8" />
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function NumberActions({ number }: { number: AuphereOwnerChannelOut }) {
  const [open, setOpen] = useState<"edit" | NumberChange | null>(null);
  // Each opening mounts the dialog again, so its form starts from the row as it is now.
  const [nonce, setNonce] = useState(0);
  const show = (which: "edit" | NumberChange) => () => {
    setNonce((n) => n + 1);
    setOpen(which);
  };
  const props = (which: "edit" | NumberChange) => ({
    number,
    open: open === which,
    onOpenChange: (next: boolean) => setOpen(next ? which : null),
  });

  const regular: { key: NumberChange; label: string }[] = number.active
    ? [number.is_default ? { key: "demote", label: "Quitar como principal" } : { key: "promote", label: "Marcar como principal" }]
    : [{ key: "reactivate", label: "Reactivar" }];
  const change = open && open !== "edit" ? open : null;

  return (
    <div className="flex items-center justify-end gap-1">
      <Button size="sm" variant="outline" onClick={show("edit")} aria-label={`Editar ${number.display_name}`}>
        Editar
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button variant="ghost" size="icon-sm" aria-label={`Más acciones de ${number.display_name}`}>
              <MoreHorizontal aria-hidden="true" className="size-4" />
            </Button>
          }
        />
        <DropdownMenuContent align="end" className="min-w-48">
          <DropdownMenuGroup>
            {regular.map((item) => (
              <DropdownMenuItem key={item.key} className={FOCUS_RING_INSET} onClick={show(item.key)}>
                {item.label}
              </DropdownMenuItem>
            ))}
            {number.active ? (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive" className={FOCUS_RING_INSET} onClick={show("deactivate")}>
                  Desactivar
                </DropdownMenuItem>
              </>
            ) : null}
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>
      {open === "edit" ? <EditNumberDialog key={`edit-${nonce}`} {...props("edit")} /> : null}
      {change ? <ChangeNumberDialog key={`${change}-${nonce}`} change={change} {...props(change)} /> : null}
    </div>
  );
}
