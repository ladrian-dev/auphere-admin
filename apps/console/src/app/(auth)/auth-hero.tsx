import { BrandLockup } from "@nexus/ui";

import { LiquidBackdropLazy } from "@/components/auth/liquid-backdrop-lazy";

import { AuthHeroCopy, type HeroCopy } from "./auth-hero-copy";

/**
 * El panel del líquido — spec 066, requisitos 1 a 3.
 *
 * Cuatro capas, de abajo arriba:
 *
 * 1. el respaldo CSS (`.auth-hero-bg`): manchas de los mismos verdes, lo que se
 *    ve mientras carga el líquido o si no hay WebGL (R2.7, R2.8);
 * 2. el lienzo del líquido, que aparece con un fundido encima del respaldo;
 * 3. un velo oscuro abajo, para que el titular se lea sobre cualquier color del
 *    líquido (R3.4);
 * 4. el logo, «Beta» y el titular, que en el alta lleva los tres pasos del
 *    arranque (spec 067, `auth-hero-copy.tsx`).
 *
 * El titular no es un `h1`: el `h1` es el de cada página («Inicia sesión.»,
 * «Recupera tu cuenta.»), que es lo que la persona viene a hacer.
 */
export function AuthHero({ base, signup, beta }: { base: HeroCopy; signup: HeroCopy; beta: string }) {
  return (
    <div className="auth-hero" data-testid="auth-hero">
      <div className="auth-hero-bg" aria-hidden="true">
        <i />
        <i />
        <i />
        <i />
        <i />
      </div>
      <LiquidBackdropLazy />
      <div className="auth-hero-veil" aria-hidden="true" />
      <div className="auth-hero-top">
        <BrandLockup className="auth-hero-lockup" markClassName="size-7 text-white" />
        {/* Owner, 2026-10-19: la consola está en beta. Neutro, no ámbar: el
            ámbar es de los avisos y esto no avisa de nada (R3.2). */}
        <span className="auth-beta">{beta}</span>
      </div>
      <AuthHeroCopy base={base} signup={signup} />
    </div>
  );
}
