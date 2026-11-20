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
        eyebrow={t("login.eyebrow")}
        title={t("auth.hero.title")}
        beta={t("shell.beta")}
      />
      <div className="auth-side">
        <div className="auth-col">
          {children}
          <p className="text-xs text-muted-foreground">{t("login.footer")}</p>
        </div>
      </div>
    </main>
  );
}
