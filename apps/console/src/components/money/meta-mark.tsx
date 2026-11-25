/**
 * La marca de Meta junto a «Mensajes de Meta» en Consumo — spec 072 (4.3).
 * Como la «G» de Google (spec 067): un archivo en `public/third-party/`, con el
 * color de Meta y no un token nuestro, y de fondo porque es decorativa: la
 * etiqueta ya dice qué es.
 */
export function MetaMark({ className = "" }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      data-testid="meta-mark"
      className={`inline-block size-4 shrink-0 bg-[url(/third-party/meta.svg)] bg-contain bg-center bg-no-repeat ${className}`}
    />
  );
}
