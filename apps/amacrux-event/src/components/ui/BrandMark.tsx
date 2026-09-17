import Image from "next/image";

import { cx } from "@/lib/cx";

type Variant = "navy" | "white" | "turquoise" | "chrome" | "auto";

const src: Record<Exclude<Variant, "auto">, string> = {
  navy: "/brand/wordmark-navy.png",
  white: "/brand/wordmark-white.png",
  turquoise: "/brand/wordmark-turquoise.png",
  /** Versión cromada generada con Higgsfield a partir del wordmark oficial (fondo recortado). */
  chrome: "/brand/wordmark-chrome.png",
};
const CHROME_RATIO = 5.2632;

/**
 * Wordmark de Amacrux (PNG @3x, relación 6:1). `auto` pinta el navy en tema
 * claro y el blanco en tema oscuro (clases `brand-light`/`brand-dark` en globals.css).
 */
export function BrandMark({ variant = "auto", height = 22, className, priority = false }: { variant?: Variant; height?: number; className?: string; priority?: boolean }) {
  const width = Math.round(height * 6.1);
  const style = { width, height };
  const chromeHeight = Math.round(height * 1.3);
  const chromeStyle = { width: Math.round(chromeHeight * CHROME_RATIO), height: chromeHeight };
  if (variant === "chrome") {
    return <Image src={src.chrome} alt="Amacrux" width={chromeStyle.width} height={chromeStyle.height} priority={priority} className={cx("h-auto", className)} style={chromeStyle} />;
  }
  if (variant !== "auto") {
    return <Image src={src[variant]} alt="Amacrux" width={width} height={height} priority={priority} className={cx("h-auto", className)} style={style} />;
  }
  return (
    <>
      <Image src={src.navy} alt="Amacrux" width={width} height={height} priority={priority} className={cx("brand-light h-auto", className)} style={style} />
      <Image src={src.chrome} alt="" aria-hidden width={chromeStyle.width} height={chromeStyle.height} priority={priority} className={cx("brand-dark h-auto", className)} style={chromeStyle} />
    </>
  );
}

export function BrandIsotipo({ size = 40, variant = "turquoise", className }: { size?: number; variant?: "turquoise" | "navy" | "white"; className?: string }) {
  return <Image src={`/brand/isotipo-hex-${variant}.png`} alt="" aria-hidden width={size} height={size} className={className} />;
}
