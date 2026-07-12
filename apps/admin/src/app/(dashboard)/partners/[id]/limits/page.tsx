import { notFound } from "next/navigation";

import { Eyebrow } from "@/components/brand/eyebrow";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { backend } from "@/lib/backend";

import { BlueprintForm } from "./blueprint-form";
import { LimitsForm } from "./limits-form";

/**
 * Caps y rate limits del partner + kill-switch (suspender) + blueprint
 * de auto-provisión. Todo va por el mismo PATCH /admin/partners/:id.
 */
export default async function PartnerLimitsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [partner, seedTemplates] = await Promise.all([
    backend.getPartner(id),
    backend.listSeedTemplates(),
  ]);
  if (!partner) notFound();

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <Eyebrow>Límites</Eyebrow>
          <CardTitle>Caps y rate limits</CardTitle>
          <CardDescription>
            El cap de broadcast limita destinatarios por envío; los rate
            limits protegen el mint de session tokens y las llamadas del
            embed. Suspender el partner corta TODAS sus keys de inmediato
            sin revocarlas — es el kill-switch reversible.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <LimitsForm partner={partner} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <Eyebrow>Blueprint</Eyebrow>
          <CardTitle>Auto-provisión de clientes</CardTitle>
          <CardDescription>
            Con el blueprint configurado, cada cliente que el partner
            provisiona nace con su agente clonado del seed (promovido a v1)
            y el connector instalado con las credenciales que envía; el
            signup de WhatsApp activa el tenant sin operador en el loop.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <BlueprintForm partner={partner} seedTemplates={seedTemplates} />
        </CardContent>
      </Card>
    </div>
  );
}
