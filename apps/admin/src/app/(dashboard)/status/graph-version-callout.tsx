import { Callout } from "@nexus/ui";

/** Spec 050 (3.6): Meta stops serving the Graph version every call uses. */
export function GraphVersionCallout({ version, expiresOn, daysLeft }: { version: string; expiresOn: string; daysLeft: number }) {
  const gone = daysLeft <= 0;
  return (
    <Callout tone={gone ? "danger" : "warning"} title={gone ? `Meta ya no sirve la versión ${version}` : `La versión ${version} de Meta caduca en ${daysLeft} días`}>
      Meta deja de servirla el {expiresOn}. Hay que subir <code className="font-mono">meta_graph_api_version</code> en la API y los valores de la consola y el panel, y probar el alta en staging antes.
    </Callout>
  );
}
