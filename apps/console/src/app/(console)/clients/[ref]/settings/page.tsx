import { permanentRedirect } from "next/navigation";

/**
 * Spec 018 (R2.2): «Datos del cliente» ya no es una pestaña.
 *
 * Eran dos campos —nombre y zona horaria— con una pantalla entera para
 * ellos. Ahora se editan en el Resumen, que es donde ya se leían. Paridad en
 * `specs/018-ficha-ligera-y-catalogos/parity.md`, filas 22–25.
 *
 * Redirección **permanente**: la URL puede estar en un correo o en un
 * marcador, y quien la abra tiene que acabar donde está lo que buscaba.
 */
export default async function ClientSettingsPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  permanentRedirect(`/clients/${encodeURIComponent(ref)}`);
}
