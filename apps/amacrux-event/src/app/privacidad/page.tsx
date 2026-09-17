import type { Metadata } from "next";

import { AppShell } from "@/components/layout/AppShell";
import { BackLink } from "@/components/ui/BackLink";

export const metadata: Metadata = { title: "Privacidad" };

// TODO_COMERCIAL: validar con Amacrux el responsable del tratamiento, la dirección de contacto y la base legal.
export default function PrivacidadPage() {
  return (
    <AppShell width="wide">
      <div className="-ml-2 pt-4">
        <BackLink />
      </div>
      <article className="prose-sm max-w-none py-4 text-ink">
        <h1 className="font-display text-3xl font-bold">Privacidad del diagnóstico</h1>
        <p className="mt-4 text-ink-muted">Versión orientativa para el evento. Pendiente de validación por Amacrux.</p>
        <h2 className="mt-8 font-display text-xl font-semibold">Qué datos usamos y para qué</h2>
        <ul className="mt-2 list-disc pl-5 leading-relaxed">
          <li>Las respuestas del diagnóstico no contienen datos personales y se guardan solo en tu navegador durante la sesión.</li>
          <li>El resultado se calcula en tu dispositivo; no se envía a ningún servidor.</li>
          <li>Para ver el resultado te pedimos tus datos de contacto (nombre y apellido, empresa, correo y teléfono opcional). Con tu consentimiento se envían a Amacrux por correo electrónico junto con un resumen de tu resultado, para contactarte sobre lo que has indicado.</li>
          <li>No te enviaremos comunicaciones comerciales distintas de ese contacto.</li>
          <li>La medición del uso de esta página es anónima: no incluye tu nombre, correo ni respuestas concretas.</li>
        </ul>
        <h2 className="mt-8 font-display text-xl font-semibold">Tus derechos</h2>
        <p className="mt-2 leading-relaxed">
          Puedes pedir el acceso, la rectificación o la eliminación de tus datos de contacto escribiendo a Amacrux.
          {/* TODO_COMERCIAL: validar con Amacrux la dirección de contacto para derechos. */}
        </p>
        <h2 className="mt-8 font-display text-xl font-semibold">Recomendaciones orientativas</h2>
        <p className="mt-2 leading-relaxed">
          Las recomendaciones se generan con reglas a partir de tus respuestas. Son orientativas, no garantizan resultados y no constituyen
          asesoramiento legal, financiero ni médico.
        </p>
      </article>
    </AppShell>
  );
}
