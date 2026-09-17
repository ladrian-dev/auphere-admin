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
          <li>Mientras respondes, las doce respuestas se quedan en tu navegador y el resultado se calcula en tu propio dispositivo.</li>
          <li>
            Al enviar el formulario, y solo entonces, salen de tu dispositivo <strong>tus datos de contacto</strong> (nombre y apellido, empresa,
            correo y teléfono si lo das) <strong>junto con el diagnóstico completo</strong>: las doce respuestas, la puntuación, el nivel de
            oportunidad y las tres recomendaciones.
          </li>
          <li>Todo eso llega por correo electrónico al equipo de Auphere y Amacrux, que lo usa para escribirte sobre lo que has indicado.</li>
          <li>
            El envío lo hace Resend, nuestro proveedor de correo, que conserva el mensaje y sus metadatos según su propia política. No guardamos tus
            datos en ninguna otra base de datos.
          </li>
          <li>Si no envías el formulario, no sale nada de tu navegador y no queda ningún rastro tuyo.</li>
          <li>No te enviaremos comunicaciones comerciales distintas de ese contacto.</li>
          <li>La medición del uso de esta página es anónima: no incluye tu nombre, correo ni respuestas concretas.</li>
        </ul>
        <h2 className="mt-8 font-display text-xl font-semibold">Tus derechos</h2>
        <p className="mt-2 leading-relaxed">
          Puedes pedir el acceso, la rectificación o la eliminación de tus datos escribiendo a{" "}
          <a href="mailto:contacto+event@auphere.com" className="underline underline-offset-2">
            contacto+event@auphere.com
          </a>
          . Atender una supresión es borrar el correo del buzón y su copia en el registro de Resend.
          {/* TODO_COMERCIAL: validar con Amacrux el responsable del tratamiento y la base legal. */}
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
