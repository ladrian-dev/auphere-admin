import { getT } from "@/i18n/server";

import { AuthHero } from "./auth-hero";
import "./auth.css";

/**
 * El marco de las páginas públicas — spec 066, requisito 1.
 *
 * Partido desde 900 px: el líquido a la izquierda y la página a la derecha, en
 * una columna de 360 px. Por debajo, el líquido es una franja encima.
 *
 * **El líquido vive aquí y no en cada página** (R1.3): un layout no se vuelve a
 * montar al navegar entre sus páginas, así que al pasar de Entrar a Recuperar la
 * cuenta el líquido sigue donde estaba. La página que cambia entra con su propio
 * fundido (`template.tsx`, R6.1).
 *
 * Spec 056 (14.1): sin principal, el idioma es el de la cookie o el del
 * navegador (`getT()` sin argumento), el mismo que usa el cuerpo de cada página.
 */
export default async function AuthLayout({ children }: { children: React.ReactNode }) {
  const { t } = await getT();
  return (
    <main className="auth-shell">
      <AuthHero
        beta={t("shell.beta")}
        base={{ eyebrow: t("login.eyebrow"), title: t("auth.hero.title") }}
        signup={{
          eyebrow: t("login.eyebrow"),
          title: t("signup.hero.title"),
          body: t("signup.hero.body"),
          stepsLabel: t("signup.hero.steps"),
          currentLabel: t("signup.step.current"),
          nextLabel: t("signup.step.next"),
          steps: [
            { title: t("signup.step1.title"), body: t("signup.step1.body") },
            { title: t("signup.step2.title"), body: t("signup.step2.body") },
            { title: t("signup.step3.title"), body: t("signup.step3.body") },
          ],
        }}
      />
      <div className="auth-side">
        <div className="auth-col">
          {/* Sin pie «Auphere» (owner, 2026-11-20, spec 067): el logo ya está
              en el panel. */}
          {children}
        </div>
      </div>
    </main>
  );
}
