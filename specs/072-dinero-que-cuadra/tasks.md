# Tareas: Dinero que cuadra (spec 072)

- [x] T001 Tests del formato único (es/en, «USD», nunca «US$») y barrido de `src` (1.1–1.4).
- [x] T002 `currencyFormat` en `@nexus/ui`; `formatAmount`, `formatUnits` y `formatMoneyCompact` en la consola; Facturación y `spend-card` sin `style: "currency"` propio.
- [x] T003 Tests de `bagBar` y `bagPace` (lo que queda, tono desde `state`, cuánto dura) (2.1–2.3).
- [x] T004 `BagMeter` en Clientes y en la ficha; fuera la barra apilada por agente y su modelo (2.4, 2.6).
- [x] T005 «Saldo disponible» del Panel: la barra es lo disponible (2.5).
- [x] T006 Test de API: las partes del gasto del Panel suman su total y es el de Consumo; Consumo sin Companion (3.1, 3.2, 4.3, D2).
- [x] T007 `partner_panel` y `usage_lines` cuentan solo las bolsas de los clientes.
- [x] T008 Panel: nombres enteros, la línea de construcción siempre con «Pedir ampliación» desde el 80 % (3.3, 3.4, 4.4).
- [x] T009 Consumo en el orden de la demo; cuatro cifras con Meta y su marca; Companion en el detalle; sin el filtro de partida; sin las tarjetas de partidas (4.1–4.4, D3, D4).
- [x] T010 `BlockChart` de barras macizas, eje entero, hoy marcado, crecen al entrar (§5).
- [x] T011 Asignar y Comprar saldo eligen el importe igual; botón con el importe, motivo si está apagado, recibo de cuatro líneas, esqueleto del mismo alto, interruptor de relleno (§6).
- [ ] T012 E2E de Consumo con axe en claro y oscuro (7.2).
- [ ] T013 Comprobar en staging contra el recorrido del estudio (7.3).
