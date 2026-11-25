# Implementation Plan: Crear cuenta

**Branch**: `067-crear-cuenta` | **Date**: 2026-11-20 | **Spec**: [spec.md](spec.md)

## Summary

Solo consola, dentro de `(auth)`. No toca la API ni `@nexus/ui`.

1. **Panel por ruta**: `auth-hero-copy.tsx` (cliente) elige el texto con `usePathname()`. En `/signup*` muestra «Empieza con Auphere.», su frase y los tres pasos. El layout le pasa los dos textos ya traducidos. El líquido sigue en el layout y no se vuelve a montar (R1.3).
2. **`/signup`**:
   - «Paso 1 de 3»;
   - Google dentro de `SignupForm` (como `google`), para que se vaya al «enviado»;
   - «o con tu correo» y «Correo de trabajo»;
   - un «enviado» con el correo, «Usar otro correo» y «Reenviar» a los 30 s;
   - la cuenta atrás fuera de la región viva.
3. **`/signup/{token}`**:
   - el correo como texto con `BadgeCheck`;
   - contraseña con `PasswordToggle` y `PasswordRule` (`components/auth/`);
   - el enlace muerto con «Pedir otro enlace».
4. **`GoogleButton`**: dice «Registrarte con Google» cuando `intent="signup"`.
5. **Textos**: carril `i18n/lanes/auth-alta.ts`.

## Constitution Check

| Principio | Cómo se cumple |
|---|---|
| I. Aislamiento | Sin fronteras nuevas. El oráculo de la 006 (R1.2) queda fijado por un test (`signup-form.test.tsx`). |
| II. Superficie | `0`, ya abierta. |
| III, IV, VI | No aplican. |
| V. La pantalla no miente | El «enviado» no promete más de lo que sabe. Sin Google no hay botón ni separador. El enlace muerto es una sola pantalla. |
| VII. Test primero | Vitest para el panel, el alta y el segundo paso. Playwright + axe con el alta encendida (`e2e/auth-entrar.config.ts`). |
| VIII. Licencias | Sin dependencias nuevas. |
| IX. KB ↔ repo | `nexus/UX-CONSOLA-PARTNERS-2026-11-20`. |
