---
description: "Tareas de la spec 066: Entrar con el líquido vivo"
---

# Tasks: Entrar con el líquido vivo

**Input**: [spec.md](spec.md), [plan.md](plan.md)

**Tests**: obligatorios (constitución §VII). Rojo antes de verde.

## Reglas de este repo

- Cada tarea cita sus requisitos.
- **Sin commits**: los hace Luis. Al cerrar se entregan los mensajes.
- **Aislamiento**: ninguna garantía tocada. **Licencias**: ninguna dependencia nueva. **Medidor**: nada.

## Fase 1: El líquido

- [X] T001 Test `src/components/auth/__tests__/liquid-backdrop-model.test.ts`:
  - el puntero se acerca al objetivo con suavizado;
  - el dedo invisible toma el mando a los 2,5 s;
  - la cola guarda cuatro ondas como máximo;
  - el lienzo va a media resolución con DPR ≤ 2;
  - un cuadro quieto con reducir movimiento.

  _Requisitos: 2.1–2.4, 2.6_
- [X] T002 `src/components/auth/liquid-backdrop-model.ts`. _Requisitos: 2.1–2.4, 2.6_
- [X] T003 Test `src/components/auth/__tests__/liquid-backdrop.test.tsx`:
  - sin WebGL no pinta lienzo y no falla;
  - el lienzo lleva `aria-hidden`;
  - al desmontar se cancela el pintado.

  _Requisitos: 2.7, 2.9, 2.10_
- [X] T004 `src/components/auth/liquid-backdrop.tsx` (shader, bucle, eventos, observadores, limpieza, guarda de cuadros lentos). _Requisitos: 2.1–2.10_

## Fase 2: El marco

- [X] T005 Test `src/app/(auth)/__tests__/auth-hero.test.tsx`:
  - el panel lleva el logo de verdad y «Beta» sin ámbar;
  - los textos van en el idioma pedido.

  _Requisitos: 3.1–3.3_
- [X] T006 `(auth)/layout.tsx`, `(auth)/auth-hero.tsx`, `(auth)/auth.css` y el carril `i18n/lanes/auth-entrar.ts`. _Requisitos: 1.1–1.4, 2.8, 3.1–3.4, 6.1_

## Fase 3: Entrar y recuperar

- [X] T007 Test `src/app/(auth)/__tests__/login-form.test.tsx`:
  - mostrar/ocultar con `aria-pressed`;
  - el correo escrito pasa a `sessionStorage` al pulsar el enlace, y no a la URL.

  _Requisitos: 4.1–4.3_
- [X] T008 `login-form.tsx` y `login/page.tsx` (separador «o»). _Requisitos: 4.1–4.3_
- [X] T009 Test `src/app/(auth)/__tests__/forgot-form.test.tsx`:
  - el correo se lee de `sessionStorage` y se borra;
  - «enviado» repite el correo;
  - «Cambiar» vuelve al formulario;
  - «Reenviar» espera 30 s y vuelve a llamar.

  **Oráculo**: la acción devuelve `ok` siempre, así que el test fija que la pantalla no depende de nada más que del correo escrito.

  _Requisitos: 4.3–4.5_
- [X] T010 `forgot-form.tsx`. _Requisitos: 4.3–4.5_

## Fase 4: Contraseña nueva

- [X] T011 Test `src/app/(auth)/__tests__/reset-form.test.tsx`:
  - las reglas se marcan al escribir;
  - un envío inválido pone el error en el campo y el foco en él;
  - mostrar/ocultar cambia los dos campos;
  - el aviso sigue antes del botón;
  - «hecho» no abre sesión.

  _Requisitos: 5.1–5.4_
- [X] T012 `reset-form.tsx`. _Requisitos: 5.1–5.4_

## Fase 5: En un navegador

- [X] T013 `e2e/auth-mock.mjs`, `e2e/auth-entrar.config.ts` y `e2e/auth-entrar.e2e.ts`:
  - pantalla partida a 1280 px y franja a 390 px, sin desplazamiento horizontal a 320 px;
  - el lienzo existe y no tapa el formulario;
  - el líquido sigue al navegar Entrar → Recuperar;
  - axe sin violaciones graves en las tres páginas;
  - reducir movimiento.

  _Requisitos: 1.1–1.3, 2.5, 2.6, 6.2, 6.3_
- [ ] T014 Pasada en staging contra el recorrido de la demo (lo hace el equipo tras el despliegue).
