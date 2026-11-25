"use client";

import { usePathname } from "next/navigation";

export type HeroStep = { title: string; body: string };

export type HeroCopy = {
  eyebrow: string;
  title: string;
  /** Solo en el alta (spec 067, R1). */
  body?: string;
  steps?: HeroStep[];
  stepsLabel?: string;
  currentLabel?: string;
  nextLabel?: string;
};

/**
 * El texto del panel del líquido — spec 066 (R3) y spec 067 (R1).
 *
 * Es lo único del panel que cambia con la ruta: en el alta enseña los tres
 * pasos del arranque, en las demás el titular de siempre. Va aparte y en
 * cliente para que el layout (y con él el líquido) no se vuelva a montar al
 * pasar de Entrar al alta: solo cambia esto.
 */
export function AuthHeroCopy({ base, signup }: { base: HeroCopy; signup: HeroCopy }) {
  const path = usePathname() ?? "";
  const copy = path === "/signup" || path.startsWith("/signup/") ? signup : base;
  return (
    <div className="auth-hero-copy" key={copy.title}>
      <p className="auth-hero-eyebrow">{copy.eyebrow}</p>
      <p className="auth-hero-title">{copy.title}</p>
      {copy.body ? <p className="auth-hero-body">{copy.body}</p> : null}
      {copy.steps ? (
        <ol className="auth-steps" aria-label={copy.stepsLabel}>
          {copy.steps.map((s, i) => {
            const current = i === 0;
            return (
              <li key={s.title} data-current={current ? "" : undefined} aria-current={current ? "step" : undefined}>
                <span className="auth-step-n" aria-hidden="true">
                  {i + 1}
                </span>
                <span className="auth-step-t">
                  <b>{s.title}</b>
                  <small>{s.body}</small>
                </span>
                <span className="sr-only">{current ? copy.currentLabel : copy.nextLabel}</span>
              </li>
            );
          })}
        </ol>
      ) : null}
    </div>
  );
}
