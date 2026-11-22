# Tareas: Cierre (spec 074)

- [x] T001 Tests del marco: hasta 900 px, una sola navegación (la barra inferior con cuatro secciones y la lente), sin ☰ ni fila arriba, y el tema en el menú del perfil (1.1–1.4).
- [x] T002 `console-shell-v2.tsx`: la barra inferior `shell-tabbar`, con la zona segura y objetivos de 48 px. Fuera la fila de arriba y el ☰.
- [x] T003 `nav-v2.ts` (`splitForPhone`): la Guía del partner y Teammate van al menú del perfil en el teléfono, bajo «Operar».
- [x] T004 `profile-menu.tsx`: «Pasar a modo oscuro / claro» (`ThemeItem`, que lee el tema solo con el menú abierto). El interruptor se esconde hasta 900 px.
- [x] T005 Clientes por debajo de 760 px: tarjetas con todo lo de la fila y el mismo ⋯ de 44 × 44 (2.1–2.3).
- [x] T006 e2e del marco (`shell.spec.ts`) a 390 px con la barra inferior (4.2); e2e de Clientes a 375, 390 y 640 px.
- [ ] T007 Todas las suites e2e de `e2e/*.config.ts` en verde. Se dice cuál estaba atrasada y por qué (4.1).
- [ ] T008 axe sin «serious» ni «critical» en las pantallas del partner, en claro y en oscuro, a 1280 y a 390 px (3.1, 3.2).
- [ ] T009 Comprobar en staging a 375 px.

## Notas

- La configuración principal (`playwright.config.ts`) necesita la consola contra una API real con su base de datos (`global.setup.ts`). No se pasa en CI ni aquí. Las suites con API simulada sí.
- Cambiar la lectura del tema a `ThemeItem` arregló el e2e «cada pantalla tiene su URL y el botón atrás vuelve a la anterior». Con `useTheme` en el menú cerrado, el segundo «atrás» desde Equipo no salía de Equipo.
