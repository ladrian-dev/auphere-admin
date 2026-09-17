import Image from "next/image";

/**
 * Sello "Partner oficial de" + sticker holográfico 3D de Auphere.
 * El sticker (public/brand/partner-sticker.png) se generó con Higgsfield
 * (nano_banana_2 con el logo real de Auphere como referencia, recorte de fondo
 * y versión 4K en docs/brand/). El texto va fuera del sticker, como pidió el
 * usuario, y todo el bloque enlaza a auphere.com.
 * TODO_COMERCIAL: validar con Amacrux y Auphere la fórmula exacta del sello.
 */
const SRC_W = 720;
const SRC_H = 340;

export function PartnerSticker({ width = 168, className = "" }: { width?: number; className?: string }) {
  const height = Math.round((width * SRC_H) / SRC_W);
  return (
    <a
      href="https://auphere.com"
      target="_blank"
      rel="noopener noreferrer"
      aria-label="Amacrux es partner oficial de Auphere"
      className={`inline-flex flex-col items-center gap-1.5 rounded-md text-current ${className}`}
    >
      <span className="text-[10px] font-semibold uppercase tracking-[0.18em] opacity-80">Partner oficial de</span>
      <Image src="/brand/partner-sticker.png" alt="" aria-hidden width={SRC_W} height={SRC_H} sizes={`${width}px`} style={{ width, height }} className="drop-shadow-[0_6px_14px_rgba(0,0,0,0.35)]" />
    </a>
  );
}
