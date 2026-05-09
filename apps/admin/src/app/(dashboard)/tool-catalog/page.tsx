import { PageHeader } from "@/components/brand/page-header";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { backend, type ToolCatalog } from "@/lib/backend";

export const metadata = { title: "Catálogo de tools · Nexus" };

const STATUS_LABEL: Record<string, string> = {
  active: "Activa",
  deprecated: "Deprecada",
  experimental: "Experimental",
  internal: "Interna",
};

export default async function ToolCatalogPage({
  searchParams,
}: {
  searchParams: Promise<{ include_internal?: string; include_deprecated?: string }>;
}) {
  const sp = await searchParams;
  const includeInternal = sp.include_internal === "1";
  const includeDeprecated = sp.include_deprecated === "1";

  const tools = await backend.listToolCatalog(includeDeprecated);
  const filtered: ToolCatalog[] = tools.filter(
    (t) => includeInternal || t.status !== "internal",
  );

  const grouped = new Map<string, ToolCatalog[]>();
  for (const t of filtered) {
    const list = grouped.get(t.mcp_server) ?? [];
    list.push(t);
    grouped.set(t.mcp_server, list);
  }
  const groups = Array.from(grouped.entries()).sort(([a], [b]) =>
    a.localeCompare(b),
  );

  return (
    <>
      <PageHeader
        eyebrow="Catálogo"
        title="Tools del agente"
        description="Catálogo global. Cada tool atómica define schema Pydantic estricto y se filtra por whitelist. Las tools internas (status='internal') jamás aparecen en el editor de whitelist por diseño."
      />

      <div className="flex items-center gap-3 text-sm">
        <CatalogToggle
          label="Mostrar tools internas"
          active={includeInternal}
          href={`?${new URLSearchParams({
            include_internal: includeInternal ? "0" : "1",
            include_deprecated: includeDeprecated ? "1" : "0",
          }).toString()}`}
        />
        <CatalogToggle
          label="Incluir deprecadas"
          active={includeDeprecated}
          href={`?${new URLSearchParams({
            include_internal: includeInternal ? "1" : "0",
            include_deprecated: includeDeprecated ? "0" : "1",
          }).toString()}`}
        />
      </div>

      <div className="grid gap-6">
        {groups.map(([server, list]) => (
          <section key={server} className="grid gap-3">
            <header className="flex items-baseline gap-2">
              <h2
                className="font-mono text-sm uppercase"
                style={{ letterSpacing: "var(--tracking-eyebrow)" }}
              >
                {server}
              </h2>
              <span className="text-xs text-muted-foreground tabular-nums">
                {list.length} tool{list.length === 1 ? "" : "s"}
              </span>
            </header>
            <div className="rounded-md border border-border bg-card overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[280px]">Tool</TableHead>
                    <TableHead>Descripción</TableHead>
                    <TableHead>Side effects</TableHead>
                    <TableHead className="text-right">Estado</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {list.map((t) => (
                    <TableRow
                      key={t.id}
                      className={
                        t.status === "internal" ? "opacity-70" : undefined
                      }
                    >
                      <TableCell className="font-mono text-sm">
                        {t.name}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground max-w-md">
                        {t.description}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          {t.side_effects.map((eff) => (
                            <Badge key={eff} variant="outline" className="font-mono text-[10px]">
                              {eff}
                            </Badge>
                          ))}
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        <Badge
                          variant={t.status === "active" ? "secondary" : "outline"}
                          className={
                            t.status === "internal"
                              ? "bg-muted text-muted-foreground"
                              : undefined
                          }
                        >
                          {STATUS_LABEL[t.status] ?? t.status}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </section>
        ))}
      </div>
    </>
  );
}

function CatalogToggle({
  label,
  active,
  href,
}: {
  label: string;
  active: boolean;
  href: string;
}) {
  return (
    <a
      href={href}
      className={
        active
          ? "rounded-full border border-[color:var(--color-primary)] bg-[color:var(--color-primary)]/10 px-3 py-1 text-xs font-medium text-[color:var(--color-primary-deep)]"
          : "rounded-full border border-border px-3 py-1 text-xs text-muted-foreground hover:text-foreground transition"
      }
    >
      {label}
    </a>
  );
}
