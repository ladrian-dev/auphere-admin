import { ErrorState, Section } from "@nexus/ui";

import { backend } from "@/lib/backend";

import { BetaChannelsForm } from "./beta-channels-form";
import { ModulesForm } from "./modules-form";

export const dynamic = "force-dynamic";

/** Spec 032: Auphere chooses which console views and services this partner has. */
export default async function PartnerModulesPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [access, beta] = await Promise.all([
    backend.getPartnerAccess(id).catch(() => null),
    backend.getPartnerBetaChannels(id).catch(() => null),
  ]);
  if (!access) {
    return <ErrorState title="No se pudieron leer los módulos" description="La API no respondió. Vuelve a intentarlo en un momento." />;
  }
  return (
    <div className="flex flex-col gap-8">
      <Section
        title="Módulos de la consola"
        description="Qué secciones y servicios ve este partner en su consola. Lo que apagues desaparece de su menú y de su buscador; sus datos no se borran."
      >
        <ModulesForm partnerId={id} access={access} />
      </Section>
      {/* Spec 049: Instagram y Messenger, hasta que Meta los apruebe para todos. */}
      {beta ? (
        <Section
          title="Canales en beta"
          description="Instagram y Messenger esperan la aprobación de Meta. Mientras tanto, solo los partners encendidos aquí los ven en su consola."
        >
          <BetaChannelsForm partnerId={id} beta={beta} />
        </Section>
      ) : null}
    </div>
  );
}
