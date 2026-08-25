import { notFound } from "next/navigation";

import { Eyebrow } from "@/components/brand/eyebrow";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { BackendError, backend } from "@/lib/backend";

import { BlockLlmForm } from "./block-form";
import { AllowlistForm } from "./models-form";

/**
 * Modelos del partner — allowlist del catálogo cerrado + block LiteLLM.
 * Sin UI LiteLLM. Sin keys.
 */
export default async function PartnerModelsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const partner = await backend.getPartner(id);
  if (!partner) notFound();

  const models = await backend.getPartnerModels(id);
  if (!models) notFound();

  let llm: { blocked: boolean } | null = null;
  let llmUnavailable = false;
  try {
    llm = await backend.getPartnerLlm(id);
  } catch (e) {
    if (e instanceof BackendError && (e.status === 409 || e.status === 401)) {
      llmUnavailable = true;
    } else {
      throw e;
    }
  }

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <Eyebrow>Modelos</Eyebrow>
          <CardTitle>Allowlist del partner</CardTitle>
          <CardDescription>
            Qué ids del catálogo cerrado ve el partner en la consola. Apagar
            Terra quita Terra del picker. No reescribe el binding de un
            cliente ya elegido.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <AllowlistForm partnerId={partner.id} items={models.items} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <Eyebrow>LiteLLM</Eyebrow>
          <CardTitle>Virtual key del partner</CardTitle>
          <CardDescription>
            Bloquear deja fail-closed el hop. No hay UI LiteLLM ni techos
            TPM/USD desde este panel.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {llmUnavailable || !llm ? (
            <p className="rounded-md border border-dashed border-border px-3 py-4 text-sm text-muted-foreground">
              Este partner no tiene virtual key mapeada. No se puede
              bloquear ni activar desde aquí.
            </p>
          ) : (
            <BlockLlmForm partnerId={partner.id} blocked={llm.blocked} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
