/**
 * La «G» de Google en sus cuatro colores, como pide su guía de marca para los
 * botones de «Continuar con Google» (spec 067). Va como archivo en
 * `public/third-party/`, como los logotipos de terceros: sus colores son de
 * Google, no tokens nuestros. Es un fondo y no una imagen porque es decorativa:
 * el texto del botón ya dice qué es.
 */
export function GoogleMark({ className = "" }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      data-icon="inline-start"
      data-testid="google-mark"
      className={`inline-block bg-[url(/third-party/google-g.svg)] bg-contain bg-center bg-no-repeat ${className}`}
    />
  );
}
