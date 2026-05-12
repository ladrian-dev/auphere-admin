import { Eyebrow } from "@/components/brand/eyebrow";
import { PageHeader } from "@/components/brand/page-header";
import { StatusDot } from "@/components/brand/status-dot";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { backend, type Connector } from "@/lib/backend";

export const metadata = { title: "Connectors · Nexus" };

const AUTH_KIND_LABEL: Record<Connector["auth_kind"], string> = {
  oauth_composio: "OAuth (Composio)",
  browser_credentials: "Credenciales (browser)",
  webhook_manual: "Webhook manual",
  api_key: "API key",
};

const CATEGORY_LABEL: Record<string, string> = {
  messaging: "Mensajería",
  booking: "Reservas",
  calendar: "Calendario",
  docs: "Documentos",
  crm: "CRM",
};

export default async function ConnectorsCatalogPage() {
  const connectors = await backend.listConnectors();

  // Group by category for visual scanning.
  const byCategory = new Map<string, Connector[]>();
  for (const c of connectors) {
    const key = c.category;
    const arr = byCategory.get(key) ?? [];
    arr.push(c);
    byCategory.set(key, arr);
  }
  const categories = Array.from(byCategory.keys()).sort();

  return (
    <>
      <PageHeader
        eyebrow="Connectors"
        title="Catálogo de integraciones"
        description="Cada connector se vuelve invocable para los agentes una vez que un tenant le otorga consentimiento. WhatsApp y AgendaPro son los del lanzamiento; los demás aterrizan vía Composio en el flujo OAuth operator-initiated."
      />

      <div className="flex items-center gap-6 text-sm text-muted-foreground">
        <span>
          <strong className="text-foreground tabular-nums">
            {connectors.length}
          </strong>{" "}
          connectors disponibles
        </span>
        <span>
          <strong className="text-foreground tabular-nums">
            {connectors.filter((c) => c.auth_kind === "oauth_composio").length}
          </strong>{" "}
          OAuth
        </span>
      </div>

      {categories.map((cat) => (
        <section key={cat} className="flex flex-col gap-3">
          <Eyebrow>{CATEGORY_LABEL[cat] ?? cat}</Eyebrow>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {byCategory.get(cat)?.map((c) => (
              <ConnectorCatalogCard key={c.id} connector={c} />
            ))}
          </div>
        </section>
      ))}
    </>
  );
}

function ConnectorCatalogCard({ connector }: { connector: Connector }) {
  const iconUrl = (connector.provider_meta as { icon_url?: string })?.icon_url;
  const channelOnly = (connector.provider_meta as { channel_only?: boolean })
    ?.channel_only;
  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex flex-row items-start gap-3 space-y-0">
        {iconUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={iconUrl}
            alt=""
            aria-hidden="true"
            className="size-8 rounded-sm object-contain bg-white border border-border p-1"
          />
        ) : (
          <span
            aria-hidden="true"
            className="size-8 rounded-sm bg-muted grid place-items-center text-xs font-mono"
          >
            {connector.display_name.slice(0, 2).toUpperCase()}
          </span>
        )}
        <div className="flex-1 min-w-0">
          <CardTitle className="text-base flex items-center gap-2 flex-wrap">
            <span className="truncate">{connector.display_name}</span>
            {connector.status !== "available" ? (
              <Badge variant="outline" className="text-[10px]">
                {connector.status}
              </Badge>
            ) : null}
          </CardTitle>
          <CardDescription className="text-xs">
            {connector.vendor}
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-2 text-xs">
        <div className="flex items-center gap-2 text-muted-foreground">
          <StatusDot
            tone={connector.status === "available" ? "positive" : "muted"}
          />
          <span>{AUTH_KIND_LABEL[connector.auth_kind]}</span>
          {channelOnly ? (
            <Badge variant="secondary" className="text-[10px]">
              canal
            </Badge>
          ) : null}
        </div>
        <div className="flex gap-1 flex-wrap">
          {connector.capabilities.map((cap) => (
            <Badge key={cap} variant="outline" className="text-[10px]">
              {cap}
            </Badge>
          ))}
        </div>
        {connector.auto_enable_destructive ? (
          <p className="text-[11px] text-muted-foreground">
            Tools destructivas se habilitan al conectar.
          </p>
        ) : (
          <p className="text-[11px] text-muted-foreground">
            Tools destructivas quedan bloqueadas hasta override del operador.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
