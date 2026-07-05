import Link from "next/link";
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

import { partnerKeyState } from "../key-state";
import { OriginsEditor } from "./origins-editor";

/**
 * Allowed origins por key. El verificador del embed rechaza cualquier
 * petición del widget cuyo ``Origin`` no esté en la lista de la key que
 * mintó el session token — este editor es la única superficie para
 * mantener esa lista.
 */
export default async function PartnerOriginsPage({
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

  // Solo keys que siguen autenticando (activas o en gracia): editar los
  // origins de una key muerta no tiene efecto.
  const editableKeys = keys.filter((k) => {
    const state = partnerKeyState(k);
    return state === "active" || state === "grace";
  });

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <Eyebrow>Allowed origins</Eyebrow>
          <CardTitle>Dominios autorizados por key</CardTitle>
          <CardDescription>
            El iframe del widget solo acepta peticiones desde estos origins.
            Formato: <code>https://…</code> (o <code>http://localhost</code>{" "}
            para desarrollo). Los cambios aplican de inmediato.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          {editableKeys.length === 0 ? (
            <div className="rounded-md border border-dashed border-border py-12 text-center text-sm text-muted-foreground">
              Sin keys activas para configurar.{" "}
              <Link
                href={`/partners/${partner.id}`}
                className="underline underline-offset-2 hover:text-foreground"
              >
                Crea una key primero
              </Link>
              .
            </div>
          ) : (
            editableKeys.map((key) => (
              <OriginsEditor
                key={`${key.id}-${key.allowed_origins.join(",")}`}
                partnerId={partner.id}
                apiKey={key}
              />
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
