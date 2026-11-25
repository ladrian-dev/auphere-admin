import { notFound } from "next/navigation";

import { EmptyState, Section, StatusBadge } from "@nexus/ui";

import { ReadError } from "@/components/states/read-error";
import { backend, type TemplateMessageRowOut } from "@/lib/backend";
import { FAILURE_LABEL, templateMessageStatus } from "@/lib/send-only";

import { ApiKeysPanel } from "./keys-panel";

export const metadata = { title: "Envío por API" };

const API_URL = "https://api.auphere.com/v1/messages/template";
const TONE = { positive: "positive", neutral: "muted", danger: "danger" } as const;
const TIME = new Intl.DateTimeFormat("es", { dateStyle: "short", timeStyle: "medium" });

/**
 * Spec 077 (requisitos 5 y 10): «Envío por API» of a client. Its keys, how
 * its system calls (address, header, a request and the 202 and 402 answers)
 * and its last 50 template sends — the recipient masked by the API, never a
 * code. Each block reads on its own: one failing does not hide the others.
 */
export default async function TenantApiPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [tenant, keys, sends] = await Promise.all([
    backend.getTenant(id),
    backend.listTenantApiKeys(id).catch(() => null),
    backend.listTemplateMessages(id, 50).catch(() => null),
  ]);
  if (!tenant) notFound();
  // The example names a template the client really uses, when there is one.
  const exampleTemplate = sends?.find((s) => s.template)?.template ?? "nombre_de_su_plantilla";

  return (
    <div className="flex flex-col gap-8">
      <ApiKeysPanel tenantId={id} tenantName={tenant.name} keys={keys} />
      <HowItCalls template={exampleTemplate} />
      <LastSends sends={sends} />
    </div>
  );
}

function HowItCalls({ template }: { template: string }) {
  const request = [
    `POST ${API_URL}`,
    "Authorization: Bearer ak_live_…",
    "Content-Type: application/json",
    "",
    "{",
    '  "to": "+56912345678",',
    `  "template_name": "${template}",`,
    '  "language": "es",',
    '  "code": "482913",',
    '  "idempotency_key": "login-7f3a"',
    "}",
  ].join("\n");
  return (
    <section aria-labelledby="how-title" className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <h2 id="how-title" className="text-lg font-semibold text-balance">
          Cómo llama su sistema
        </h2>
        <p className="text-sm text-pretty text-muted-foreground">
          Una llamada por código, con su clave en la cabecera. El código va en su propio campo: sale en el cuerpo y en el
          botón de copiar de la plantilla de autenticación. La misma <code className="font-mono">idempotency_key</code> dos
          veces no envía dos mensajes.
        </p>
      </div>
      <div className="grid min-w-0 gap-3 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <figure className="flex min-w-0 flex-col gap-2">
          <figcaption className="text-xs font-medium text-muted-foreground">Petición</figcaption>
          {/* Focusable so a keyboard can scroll it at 360 px (WCAG 2.1.1). */}
          <pre
            tabIndex={0}
            role="region"
            aria-label="Petición de ejemplo"
            className="overflow-x-auto rounded-md bg-muted p-4 font-mono text-xs leading-relaxed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          >
            {request}
          </pre>
        </figure>
        <div className="flex min-w-0 flex-col gap-3">
          <figure className="flex min-w-0 flex-col gap-2">
            <figcaption>
              <StatusBadge tone="positive">202 · en cola</StatusBadge>
            </figcaption>
            <pre
              tabIndex={0}
              role="region"
              aria-label="Respuesta 202, en cola"
              className="overflow-x-auto rounded-md bg-muted p-4 font-mono text-xs leading-relaxed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              {'{ "message_id": "…", "status": "pending",\n  "to": "+56912345678", "duplicate": false }'}
            </pre>
          </figure>
          <figure className="flex min-w-0 flex-col gap-2">
            <figcaption>
              <StatusBadge tone="danger">402 · membresía inactiva</StatusBadge>
            </figcaption>
            <pre
              tabIndex={0}
              role="region"
              aria-label="Respuesta 402, membresía inactiva"
              className="overflow-x-auto rounded-md bg-muted p-4 font-mono text-xs leading-relaxed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              {'{ "detail": "membership_inactive: this client\'s\n  monthly membership is not active; nothing was queued" }'}
            </pre>
            <p className="text-xs text-pretty text-muted-foreground">
              Solo si tiene membresía y no está activa: no se encola nada.
            </p>
          </figure>
        </div>
      </div>
    </section>
  );
}

function LastSends({ sends }: { sends: TemplateMessageRowOut[] | null }) {
  return (
    <Section title="Últimos envíos" description="Los 50 últimos envíos de plantillas. El destinatario va enmascarado." padded={false}>
      {sends === null ? (
        <div className="p-6">
          <ReadError title="No se pudieron leer los envíos" description="La API no respondió. Vuelve a intentarlo en unos segundos." />
        </div>
      ) : sends.length === 0 ? (
        <div className="p-6">
          <EmptyState
            title="Todavía no ha enviado nada"
            description="Cuando su sistema llame a la API, cada envío aparece aquí con su estado."
            readonly
          />
        </div>
      ) : (
        <div
          tabIndex={0}
          role="region"
          aria-label="Últimos envíos"
          className="overflow-x-auto focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring"
        >
          <table className="w-full min-w-[36rem] text-sm">
            <caption className="sr-only">Últimos envíos de plantillas</caption>
            <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
              <tr>
                <th scope="col" className="px-6 py-2 font-medium">
                  Hora
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Para
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Plantilla
                </th>
                <th scope="col" className="px-6 py-2 font-medium">
                  Estado
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {sends.map((s) => {
                const status = templateMessageStatus(s.status);
                const why = s.failure_code ? (FAILURE_LABEL[s.failure_code] ?? s.failure_code) : null;
                return (
                  <tr key={s.id}>
                    <td className="px-6 py-2 whitespace-nowrap text-muted-foreground tabular-nums">
                      <time dateTime={s.created_at}>{TIME.format(new Date(s.created_at))}</time>
                    </td>
                    <td className="px-3 py-2 font-mono text-xs whitespace-nowrap tabular-nums">{s.to_masked}</td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {/* Cut to fit; the whole name on hover. */}
                      <span className="block max-w-48 truncate" title={s.template ?? undefined}>
                        {s.template ?? "—"}
                      </span>
                    </td>
                    <td className="px-6 py-2">
                      <StatusBadge tone={TONE[status.tone]} className="max-w-full">
                        <span className="max-w-64 truncate" title={why ? `${status.label} · ${why}` : undefined}>
                          {status.label}
                          {why ? ` · ${why}` : ""}
                        </span>
                      </StatusBadge>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}
