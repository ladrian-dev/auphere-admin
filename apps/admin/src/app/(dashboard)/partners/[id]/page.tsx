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

import { KeysPanel } from "./keys-panel";

/**
 * Default tab del partner: API keys. Crear y rotar terminan en el dialog
 * de plaintext (una sola vez); revocar es inmediato y sin gracia.
 */
export default async function PartnerKeysPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [partner, keys] = await Promise.all([
    backend.getPartner(id),
    backend.listPartnerKeys(id),
  ]);
  if (!partner) notFound();

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <Eyebrow>API keys</Eyebrow>
          <CardTitle>Claves secretas del partner</CardTitle>
          <CardDescription>
            Autentican las llamadas server-to-server (<code>/v1/partners</code>
            ). El panel solo guarda el prefijo — el plaintext se muestra una
            única vez al crear o rotar. Rotar deja la key vieja viva durante
            el período de gracia; revocar la mata al instante.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <KeysPanel partnerId={partner.id} keys={keys} />
        </CardContent>
      </Card>
    </div>
  );
}
