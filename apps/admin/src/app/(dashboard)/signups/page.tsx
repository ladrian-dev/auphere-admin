import Link from "next/link";

import { PageHeader } from "@/components/brand/page-header";
import { StatusDot } from "@/components/brand/status-dot";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { backend } from "@/lib/backend";
import { fullDateTime, relativeTime } from "@/lib/format";
import {
  canResend,
  entryRouteLabel,
  isHalfFinished,
  signupStatusLabel,
  signupTone,
} from "@/lib/signups";

import { ResendButton } from "./resend-button";

export const metadata = { title: "Altas" };

/**
 * Quién entró solo — spec 006, Requisito 8.
 *
 * Esta página existe porque al abrir la puerta el panel deja de ser donde se
 * crean los partners y pasa a ser donde uno **se entera** de los que se crearon
 * sin él. De ahí que la tabla mezcle a propósito dos cosas que no son iguales:
 * empresas ya nacidas y registros a medias. Separarlas en dos pantallas
 * escondería justo la relación que el operador necesita ver.
 */
export default async function SignupsPage() {
  const signups = await backend.listSignups();
  const aMedias = signups.filter(isHalfFinished).length;
  const nacidos = signups.filter((s) => s.partner !== null).length;

  return (
    <>
      <PageHeader
        eyebrow="Altas"
        title="Registro autónomo"
        description="Quién pidió cuenta sin que nadie del equipo ejecutara nada, y en qué quedó. Suspender un partner ya nacido se hace desde su ficha."
      />

      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-muted-foreground">
        <span>
          <strong className="tabular-nums text-foreground">{nacidos}</strong> partners nacidos solos
        </span>
        <span>
          <strong className="tabular-nums text-foreground">{aMedias}</strong> a medias
        </span>
      </div>

      <div className="overflow-x-auto rounded-md border border-border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Correo</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead>Vía de entrada</TableHead>
              <TableHead>Empresa</TableHead>
              <TableHead className="hidden md:table-cell text-right">Fecha</TableHead>
              <TableHead className="text-right">Acción</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {signups.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="py-12 text-center text-pretty text-muted-foreground">
                  Nadie se ha registrado por su cuenta todavía. Con la bandera apagada esto es lo
                  esperado, no un fallo.
                </TableCell>
              </TableRow>
            ) : (
              signups.map((s) => (
                <TableRow key={s.id} className="transition-colors hover:bg-muted/40">
                  <TableCell className="min-w-0">
                    <span className="block truncate font-medium">{s.email}</span>
                  </TableCell>
                  <TableCell>
                    <span className="inline-flex items-center gap-2 whitespace-nowrap">
                      <StatusDot tone={signupTone(s.status)} />
                      <span>{signupStatusLabel(s.status)}</span>
                    </span>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{entryRouteLabel(s.provider)}</Badge>
                  </TableCell>
                  <TableCell className="min-w-0">
                    {s.partner ? (
                      <Link
                        href={`/partners/${s.partner.id}`}
                        className="flex min-w-0 flex-col gap-0.5 rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        <span className="truncate font-medium">{s.partner.name}</span>
                        <span className="truncate font-mono text-xs text-muted-foreground">
                          {s.partner.slug} · {s.partner.tier} · {s.partner.status}
                        </span>
                      </Link>
                    ) : (
                      // Ni un guion ni un hueco: un registro a medias es un
                      // estado con reloj, y el reloj es lo accionable.
                      <span className="text-pretty text-sm text-muted-foreground">
                        Sin nombrar todavía
                        {s.status === "pending" ? (
                          <>
                            {" · "}
                            <time dateTime={s.expires_at} title={fullDateTime(s.expires_at)}>
                              caduca {relativeTime(s.expires_at)}
                            </time>
                          </>
                        ) : null}
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="hidden text-right tabular-nums text-muted-foreground md:table-cell">
                    <time dateTime={s.created_at} title={fullDateTime(s.created_at)}>
                      {relativeTime(s.created_at)}
                    </time>
                  </TableCell>
                  <TableCell className="text-right">
                    <ResendButton signupId={s.id} enabled={canResend(s)} />
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </>
  );
}
