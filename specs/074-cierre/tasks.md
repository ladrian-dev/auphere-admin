# Tareas: Cierre (spec 074)

- [x] T001 Tests del marco: hasta 900 px, una sola navegación (la barra inferior con cuatro secciones y la lente), sin ☰ ni fila arriba, y el tema en el menú del perfil (1.1–1.4).
- [x] T002 `console-shell-v2.tsx`: la barra inferior `shell-tabbar`, con la zona segura y objetivos de 48 px. Fuera la fila de arriba y el ☰.
- [x] T003 `nav-v2.ts` (`splitForPhone`): la Guía del partner y Teammate van al menú del perfil en el teléfono, bajo «Operar».
- [x] T004 `profile-menu.tsx`: «Pasar a modo oscuro / claro» (`ThemeItem`, que lee el tema solo con el menú abierto). El interruptor se esconde hasta 900 px.
- [x] T005 Clientes por debajo de 760 px: tarjetas con todo lo de la fila y el mismo ⋯ de 44 × 44 (2.1–2.3).
- [x] T006 e2e del marco (`shell.spec.ts`) a 390 px con la barra inferior (4.2); e2e de Clientes a 375, 390 y 640 px.
- [x] T007 Todas las suites e2e de `e2e/*.config.ts` en verde. Se dice cuál estaba atrasada y por qué (4.1).
- [x] T008 axe sin «serious» ni «critical» en las pantallas del partner, en claro y en oscuro, a 1280 y a 390 px (3.1, 3.2): las suites lo miden en cada pantalla. Salió un fallo «serious» («list»), que estaba en las pestañas del cliente. La lente se puso al lado de la lista.
- [ ] T009 Comprobar en staging a 375 px.

## Notas

- La configuración principal (`playwright.config.ts`) necesita la consola contra una API real con su base de datos (`global.setup.ts`). No se pasa en CI ni aquí. Las suites con API simulada sí.
- Cambiar la lectura del tema a `ThemeItem` arregló el e2e «cada pantalla tiene su URL y el botón atrás vuelve a la anterior». Con `useTheme` en el menú cerrado, el segundo «atrás» desde Equipo no salía de Equipo.
- Resultado del 2026-11-22: las 11 suites con API simulada pasan juntas, 82 de 82. Arreglos de la app que salieron de ellas:
  - la lente de las pestañas del cliente, dentro de su `ul` («list», serious);
  - la campana, que pedía su cuenta con dos server actions al montar y cada 60 s: una en curso deshacía un clic en un enlace. Ahora lee `GET /api/notifications/count`.
- Hueco abierto: ningún e2e cubre que el partner edite la ficha de negocio de un cliente (precio, horario, «Deshacer»).
