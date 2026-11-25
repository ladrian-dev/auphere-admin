---
description: "Tareas de la spec 067: crear cuenta"
---

# Tasks: Crear cuenta

**Tests**: obligatorios (§VII). **Aislamiento**: ninguna garantía tocada. **Licencias**: nada nuevo. **Medidor**: nada.

- [X] T001 Test y código del panel por ruta (`auth-hero-copy.tsx`, `auth-hero.test.tsx`). _Requisitos: 1.1–1.4_
- [X] T002 Test y código de `/signup`:
  - Google primero;
  - «Correo de trabajo»;
  - «enviado» con el correo, «Usar otro correo» y «Reenviar»;
  - el oráculo cerrado;
  - el 429.

  Archivos: `signup-form.tsx`, `signup/page.tsx`, `signup-form.test.tsx`. _Requisitos: 2.1–2.4, 3.1–3.5, 5.2_
- [X] T003 Test y código de `/signup/{token}`:
  - el correo legible;
  - la regla en vivo y mostrar/ocultar;
  - el foco en el error;
  - entra sin mandar el correo;
  - «Pedir otro enlace».

  Archivos: `finish-form.tsx`, `[token]/page.tsx`, `finish-form.test.tsx`. _Requisitos: 4.1–4.6_
- [X] T004 «Registrarte con Google» en `google-button.tsx`. _Requisitos: 2.2_
- [X] T005 Playwright:
  - Entrar → alta sin volver a montar el líquido;
  - Google encima;
  - el «enviado»;
  - el segundo paso y el enlace muerto;
  - axe y 320 px en `/signup` y `/signup/{token}`.

  _Requisitos: 1.3, 2.2, 3.1, 4.2, 4.6_
- [ ] T006 Pasada en staging con un alta real (la hace el equipo).
