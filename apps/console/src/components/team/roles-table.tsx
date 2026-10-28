import { Check, Minus } from "lucide-react";

import { TableBody, TableCell, TableHead, TableHeader, TableRow } from "@nexus/ui";

import { roleKey, type MessageKey } from "@/i18n/messages";
import { can, type Permission, type Role } from "@/lib/permissions";

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

export const ROLE_ORDER: readonly Role[] = ["owner", "admin", "builder", "analyst", "billing"];

/**
 * Lo que se puede hacer, en palabras, con el permiso que lo decide. Sale del
 * mismo mapa que la API (`lib/permissions.ts`, espejo de `core/console_auth.py`):
 * la tabla no puede decir algo distinto de lo que la consola deja hacer (49.6).
 */
export const ROLE_CAPABILITIES: readonly { key: MessageKey; permission: Permission }[] = [
  { key: "team.roles.cap.clientsRead", permission: "clients:read" },
  { key: "team.roles.cap.clientsWrite", permission: "agents:write" },
  { key: "team.roles.cap.clientsDelete", permission: "clients:delete" },
  { key: "team.roles.cap.playground", permission: "playground:run" },
  { key: "team.roles.cap.usageRead", permission: "usage:read" },
  { key: "team.roles.cap.usageWrite", permission: "usage:write" },
  { key: "team.roles.cap.audit", permission: "audit:read" },
  { key: "team.roles.cap.team", permission: "team:manage" },
  { key: "team.roles.cap.keys", permission: "keys:manage" },
  { key: "team.roles.cap.billing", permission: "billing:manage" },
];

/**
 * «Qué puede hacer cada rol» en Equipo (spec 047, T165; requisito 49.2): una
 * fila por cosa que se hace y una columna por rol, con su descripción. Cada
 * celda dice «Sí» o «No» también a los lectores de pantalla. En un teléfono la
 * tabla se desplaza dentro de su caja.
 */
export function RolesTable({ t }: { t: T }) {
  return (
    // Spec 047 (prototipo): una tarjeta como las otras dos de Equipo.
    <section aria-labelledby="roles-h" className="flex min-w-0 flex-col gap-4 rounded-lg bg-card p-4 ring-1 ring-foreground/10" data-slot="roles-table">
      <div className="grid gap-1">
        <h2 id="roles-h" className="text-base font-semibold">
          {t("team.roles.title")}
        </h2>
        <p className="text-sm text-pretty text-muted-foreground">{t("team.roles.intro")}</p>
      </div>
      {/* En un teléfono la tabla se desplaza en su caja, que toma el foco para moverla con el teclado. */}
      <div
        role="group"
        aria-labelledby="roles-h"
        tabIndex={0}
        className="min-w-0 overflow-x-auto rounded-lg border border-border focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        data-scroll-x
      >
        <table data-slot="table" className="w-full caption-bottom text-sm" aria-labelledby="roles-h">
          <TableHeader>
            <TableRow>
              <TableHead scope="col" className="min-w-48">
                {t("team.roles.capability")}
              </TableHead>
              {ROLE_ORDER.map((role) => (
                <TableHead key={role} scope="col" className="min-w-24 text-center">
                  {t(roleKey(role))}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {ROLE_CAPABILITIES.map((cap) => (
              <TableRow key={cap.key}>
                <TableHead scope="row" className="min-w-48 font-normal whitespace-normal text-foreground">
                  {t(cap.key)}
                </TableHead>
                {ROLE_ORDER.map((role) => {
                  const yes = can(role, cap.permission);
                  return (
                    <TableCell key={role} className="text-center">
                      {yes ? (
                        <Check className="inline size-4 text-status-positive-text" aria-hidden="true" />
                      ) : (
                        <Minus className="inline size-4 text-muted-foreground" aria-hidden="true" />
                      )}
                      <span className="sr-only">{t(yes ? "team.roles.yes" : "team.roles.no")}</span>
                    </TableCell>
                  );
                })}
              </TableRow>
            ))}
          </TableBody>
        </table>
      </div>
      {/* El `dl` del prototipo: el rol en una columna de 160 px y lo que hace al lado. */}
      <dl className="grid min-w-0 gap-x-4 gap-y-2 text-sm sm:grid-cols-[160px_minmax(0,1fr)]">
        {ROLE_ORDER.map((role) => (
          <div key={role} className="contents">
            <dt className="text-muted-foreground">{t(roleKey(role))}</dt>
            <dd className="text-pretty">{t(`role.${role}.desc` as MessageKey)}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
