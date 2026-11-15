import { Section } from "@nexus/ui";

import { ReadError } from "@/components/states/read-error";
import { connectorAccessBackend } from "@/lib/backend-connector-access";

import { PartnerConnectorsList } from "./partner-connectors-list";

export const dynamic = "force-dynamic";

/**
 * Spec 060 (requisito 2): qué conectores puede usar este partner. Cada uno sigue el
 * valor por defecto del conector salvo que Auphere decida otra cosa para este partner.
 */
export default async function PartnerConnectorsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await connectorAccessBackend.forPartner(id).catch(() => null);
  if (!data) {
    return (
      <ReadError
        title="No se pudieron leer los conectores"
        description="La API no respondió. Vuelve a intentarlo en un momento."
      />
    );
  }
  return (
    <Section
      title="Conectores"
      description="Los conectores que los clientes de este partner pueden conectar y usar en sus agentes. Lo que deshabilites desaparece de su consola y sus agentes dejan de usarlo; las conexiones no se borran."
    >
      <PartnerConnectorsList partnerId={id} items={data.items} />
    </Section>
  );
}
