import { EmptyState, Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@nexus/ui";

import { settingsFields } from "./settings-schema";

/**
 * Spec 047 (T172; 36.2, 36.4): what an integration asks for when an agent
 * turns it on — each setting with its type and its rules.
 */
export function SettingsFields({ schema }: { schema: Record<string, unknown> | null | undefined }) {
  const fields = settingsFields(schema);
  if (!fields.length) {
    return <EmptyState readonly title="No pide ajustes" description="Se activa sin datos propios: le basta la conexión." />;
  }
  return (
    <div className="overflow-x-auto rounded-md ring-1 ring-foreground/10">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Ajuste</TableHead>
            <TableHead>Tipo</TableHead>
            <TableHead>Reglas</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {fields.map((f) => (
            <TableRow key={f.key}>
              <TableCell>
                <code className="text-xs">{f.key}</code>
                {f.required ? <span className="ml-2 text-xs text-muted-foreground">Obligatorio</span> : null}
              </TableCell>
              <TableCell className="text-sm">{f.type}</TableCell>
              <TableCell className="text-sm text-pretty text-muted-foreground">{f.rules.length ? f.rules.join(" · ") : "—"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
