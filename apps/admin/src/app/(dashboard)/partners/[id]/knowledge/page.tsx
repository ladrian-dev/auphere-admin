import { notFound } from "next/navigation";

import { Eyebrow } from "@/components/brand/eyebrow";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { backend, consoleHref, type KnowledgeDocumentOut } from "@/lib/backend";
import { formatBytes, relativeTime } from "@/lib/format";

const STATUS_VARIANT: Record<
  KnowledgeDocumentOut["status"],
  "default" | "secondary" | "destructive"
> = {
  indexed: "default",
  pending: "secondary",
  failed: "destructive",
};

/**
 * Conocimiento F3 del partner — playbook y packs, solo lectura.
 * Sin apply. Sin content_text. El operador no entra con sesión de
 * partner: el deep-link es una URL pública de la consola.
 */
export default async function PartnerKnowledgePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [partner, knowledge, mappings] = await Promise.all([
    backend.getPartner(id),
    backend.getPartnerKnowledge(id),
    backend.listPartnerTenants(id),
  ]);
  if (!partner || !knowledge) notFound();

  const playbookHref = consoleHref("/knowledge");
  const packs = await Promise.all(
    mappings.map(async (m) => {
      const ref = m.external_client_ref;
      const [pack, runs] = await Promise.all([
        backend.getPartnerClientWorkflow(id, ref),
        backend.getPartnerClientWorkflowRuns(id, ref),
      ]);
      return {
        ref,
        clientName: m.client_name,
        pack,
        runs: runs.items.length,
        href: consoleHref(`/clients/${encodeURIComponent(ref)}/knowledge`),
      };
    }),
  );

  const ratio =
    knowledge.prompt_char_cap > 0
      ? Math.min(100, (knowledge.indexed_chars / knowledge.prompt_char_cap) * 100)
      : 0;

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <Eyebrow>Conocimiento</Eyebrow>
          <CardTitle>Playbook del partner</CardTitle>
          <CardDescription>
            Documentos indexados del playbook. Solo metadatos — el texto
            extraído no sale de esta vista. Para editar, abre la{" "}
            <a
              href={playbookHref}
              target="_blank"
              rel="noreferrer"
              className="underline underline-offset-2"
            >
              consola
            </a>{" "}
            (URL pública, sin token de admin ni sesión de partner).
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <dl className="grid grid-cols-2 gap-x-6 gap-y-4 md:grid-cols-3">
            <div>
              <dt className="text-xs text-muted-foreground">Documentos</dt>
              <dd className="text-lg font-medium tabular-nums">{knowledge.total}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Chars indexados</dt>
              <dd className="text-lg font-medium tabular-nums">
                {knowledge.indexed_chars.toLocaleString("es-ES")}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Tope de prompt</dt>
              <dd className="text-lg font-medium tabular-nums">
                {knowledge.prompt_char_cap.toLocaleString("es-ES")}
              </dd>
            </div>
          </dl>
          <div aria-hidden className="h-1 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full bg-[color:var(--color-primary)]"
              style={{ width: `${ratio}%` }}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <Eyebrow>Documentos</Eyebrow>
          <CardTitle>Índice</CardTitle>
          <CardDescription>
            file / url · pending / indexed / failed. Sin content_text.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {knowledge.items.length === 0 ? (
            <div className="rounded-md border border-dashed border-border py-12 text-center text-sm text-muted-foreground">
              Este partner aún no tiene playbook. Aparece cuando sube
              documentos en la consola.
            </div>
          ) : (
            <div className="rounded-md border border-border overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Título</TableHead>
                    <TableHead>Tipo</TableHead>
                    <TableHead>Estado</TableHead>
                    <TableHead className="hidden md:table-cell">Mime</TableHead>
                    <TableHead className="text-right">Tamaño</TableHead>
                    <TableHead className="text-right hidden md:table-cell">
                      Chunks
                    </TableHead>
                    <TableHead className="hidden lg:table-cell text-right">
                      Indexado
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {knowledge.items.map((doc) => (
                    <TableRow key={doc.id}>
                      <TableCell>
                        <div className="font-medium">{doc.title}</div>
                        {doc.source_url ? (
                          <div className="font-mono text-xs text-muted-foreground truncate max-w-[28rem]">
                            {doc.source_url}
                          </div>
                        ) : null}
                      </TableCell>
                      <TableCell className="font-mono text-xs">{doc.kind}</TableCell>
                      <TableCell>
                        <Badge variant={STATUS_VARIANT[doc.status]}>
                          {doc.status}
                        </Badge>
                        {doc.error_code ? (
                          <div className="mt-1 font-mono text-xs text-muted-foreground">
                            {doc.error_code}
                          </div>
                        ) : null}
                      </TableCell>
                      <TableCell className="hidden md:table-cell font-mono text-xs text-muted-foreground">
                        {doc.mime}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatBytes(doc.size_bytes)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums hidden md:table-cell">
                        {doc.chunk_count}
                      </TableCell>
                      <TableCell className="hidden lg:table-cell text-right text-muted-foreground tabular-nums">
                        {relativeTime(doc.indexed_at)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <Eyebrow>Packs</Eyebrow>
          <CardTitle>Workflow por cliente</CardTitle>
          <CardDescription>
            Pack v1 de cada cliente mapeado. Solo lectura — aplicar sigue en
            la consola del partner.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {packs.length === 0 ? (
            <div className="rounded-md border border-dashed border-border py-12 text-center text-sm text-muted-foreground">
              Sin clientes mapeados. No hay packs que mostrar.
            </div>
          ) : (
            <div className="rounded-md border border-border overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Cliente</TableHead>
                    <TableHead>Pack</TableHead>
                    <TableHead>Trigger</TableHead>
                    <TableHead className="text-right">Versión</TableHead>
                    <TableHead className="text-right hidden md:table-cell">
                      Runs
                    </TableHead>
                    <TableHead>Consola</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {packs.map((row) => (
                    <TableRow key={row.ref}>
                      <TableCell>
                        <div className="font-medium">
                          {row.clientName ?? row.ref}
                        </div>
                        <div className="font-mono text-xs text-muted-foreground">
                          {row.ref}
                        </div>
                      </TableCell>
                      <TableCell>
                        {row.pack?.is_set ? "Definido" : "Sin pack"}
                      </TableCell>
                      <TableCell>{row.pack?.trigger ?? "—"}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        {row.pack?.version ?? "—"}
                      </TableCell>
                      <TableCell className="text-right tabular-nums hidden md:table-cell">
                        {row.runs}
                      </TableCell>
                      <TableCell>
                        <a
                          href={row.href}
                          target="_blank"
                          rel="noreferrer"
                          className="underline underline-offset-2 text-sm"
                        >
                          Abrir
                        </a>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
