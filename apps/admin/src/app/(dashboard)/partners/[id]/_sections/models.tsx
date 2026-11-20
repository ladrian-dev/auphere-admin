import { notFound } from "next/navigation";

import { Card, CardContent, CardDescription, CardHeader, CardTitle, Eyebrow } from "@nexus/ui";
import { BackendError, backend } from "@/lib/backend";
import { modelsBackend } from "@/lib/backend-models";

import { BlockLlmForm } from "./block-form";
import { AllowlistForm } from "./models-form";

/**
 * Modelos del partner — allowlist del catálogo cerrado + block LiteLLM.
 * Sin UI LiteLLM. Sin keys.
 *
 * Spec 065 (T075): la lista trae los seis modelos que se pueden ofrecer; los que
 * aún no responden en este entorno lo dicen.
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
  // Spec 065: the models enabled to answer here; if the read fails, the list says nothing about it.
  const respond = await Promise.resolve()
    .then(() => modelsBackend.getRespondDefault())
    .catch(() => null);
  const enabled = respond ? respond.options.map((o) => o.model_id) : null;

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
          <CardDescription className="text-pretty">
            Qué modelos ve el partner en el selector de cada agente. Quitar uno
            pasa al modelo por defecto de Auphere los agentes que el partner
            tenía con él, desde su próximo mensaje, y le avisa con el nombre de
            cada agente. No toca los que fijó Auphere.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <AllowlistForm partnerId={partner.id} items={models.items} enabled={enabled} />
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
