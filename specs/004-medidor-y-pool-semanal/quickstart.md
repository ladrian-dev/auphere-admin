# Fase 1 — Cómo se verifica que esto funciona

**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Fecha**: 2026-09-11

Guía de validación, no de implementación. Cada comprobación de aquí es un
criterio de aceptación de la spec, y **se ve en rojo antes de escribir el
código** (principio VII: *un test que hace `skip` puntúa como aprobado y por
tanto no cubre nada*).

## Prerrequisitos

```bash
docker compose up -d          # Postgres (con AGE y pgvector) + Redis + Mailhog
curl -s http://localhost:8000/health
# → {"status":"ok"}
```

## Los comandos

```bash
cd apps/api && uv run pytest tests/unit/ -x
```

```bash
cd apps/api && uv run pytest tests/isolation/ -x
```

```bash
cd apps/api && uv run pytest tests/integration/ -x
```

```bash
pnpm --filter @nexus/companion-ui test && pnpm --filter console test
```

```bash
cd apps/desktop && pnpm test
```

---

## Las comprobaciones, por requisito

### R1 · Toda tarifa que el producto vende está cargada — `tests/unit` + `tests/integration`

| # | Qué comprueba | Estado esperado |
|---|---|---|
| V01 | Los tres modelos del catálogo cerrado tienen entrada, entrada cacheada y salida | tres filas con tarifa |
| V02 | La escritura de caché de esos tres sigue **ausente**, no a cero | `NULL`, y el test lo afirma explícitamente |
| V03 | Aplicar la migración revalora el consumo que estaba sin valorar, y **no toca** el que ya tenía coste | idempotente: aplicarla dos veces no cambia una fila |
| V04 | Un consumo de modelo sin tarifa sigue sin valorar y se cuenta aparte | `complete = false` y el recuento de filas sin precio |
| V05 | Un mes con tráfico de los modelos que vendemos responde `complete = true` | **CE-003** |
| V06 | Los medidores sin precio unitario, o tienen fila o están declarados como no valorables | ninguno desaparece en silencio de un total |

### R2 · El período es semanal y la semana es la del partner — `tests/unit` + `tests/integration`

| # | Qué comprueba | Estado esperado |
|---|---|---|
| V07 | El vencimiento cae a siete días del ancla, no el día 1 del mes | función pura, sin base |
| V08 | Dos partners dados de alta en días distintos vencen en días distintos | **no** hay lunes global |
| V09 | Al vencer, el pool vuelve al tamaño completo y **lo no gastado no se suma** | **CE-006** |
| V10 | Con el proceso de renovación detenido tres días, al volver repone de inmediato | dispara por caducidad, no por calendario |
| V11 | `purchased` sobrevive a la renovación, al cambio de período y al vaciado del incluido | **R2.5**, invariante |
| V12 | El volumen mensual de cada partner no cambia al migrar de mes a semana | **CE-007** |
| V13 | Un partner recién creado nace con pool y con su vencimiento puesto **en el mismo acto** | no hay ventana sin saldo |
| V14 | Cambiar el tamaño del pool no exige migración ni despliegue | **CE-009** |

### R3 · La unidad pesa según el cerebro — `tests/unit`

| # | Qué comprueba | Estado esperado |
|---|---|---|
| V15 | **Invarianza**: agotar un pool de tamaño fijo cuesta lo mismo con los seis modelos del catálogo | banda 3,5144–3,5154 $ por millón. **CE-002**. Test de propiedad sobre el catálogo entero, no un caso suelto |
| V16 | Los factores están declarados como dato y **no** se derivan de la tarifa vigente | cambiar una tarifa no mueve el contador del partner |
| V17 | Un modelo con factor ausente **no atiende ni un turno**, con error que lo nombra | **CE-010**, fail-closed |
| V18 | La transcripción por minutos **sigue funcionando** con el factor ausente | no pasa por la cuota de LLM; es el error que alguien "arreglará" en seis meses |
| V19 | Cambiar un factor **no** revalúa asientos ya escritos | un asiento es un hecho contable |
| V20 | Los tres llamantes pasan el factor | test estructural: falla si alguno olvida el parámetro |

### R4 · Un solo medidor — `tests/integration` + `tests/isolation`

| # | Qué comprueba | Estado esperado |
|---|---|---|
| V21 | **El test que hoy falla**: consumir por canal hasta vaciar el libro y comprobar que el presupuesto lo refleja | hoy diría 20 % con el libro vacío |
| V22 | Las tres lecturas (consola, operador, aplicación) derivan del mismo dato y período | **CE-001** |
| V23 | La diferencia entre el total y lo atribuido a teammates se nombra, no se reparte ni se oculta | la línea «gastado en otro sitio» ya existe |
| V24 | Con el libro ilegible, el saldo es cero y no hay llamada al modelo | fail-closed intacto |
| V25 | No queda **ningún** segundo tope de otro alcance comparándose contra la misma cifra | **CE-008**. Test estructural |
| V26 | Un partner no puede leer el presupuesto de otro | `tests/isolation/`, RLS por `partner_id` |

### R5 · Dos bolsillos — `tests/integration`

| # | Qué comprueba | Estado esperado |
|---|---|---|
| V27 | Teammates y Companion gastan incluido primero y comprado después | orden intacto |
| V28 | El canal de clientes finales **nunca** toca el incluido | **R5.2**, el cambio de bolsillo |
| V29 | Agotado el incluido a mitad de ciclo, el trabajo continúa **sin intervención** | **CE-004** |
| V30 | Sin incluido y sin comprado: pausa por tope, confirmaciones vivas, **nada cancelado ni archivado** | **CE-005** |
| V31 | El mismo turno reprocesado **no** descuenta dos veces | idempotencia, incluido el reparto entre cubos |

### R6 · El tope por cliente — `tests/integration`

| # | Qué comprueba | Estado esperado |
|---|---|---|
| V32 | El disponible para asignar se calcula sobre **comprado** | ya no sobre incluido + comprado |
| V33 | El tope por cliente se repone **mensualmente**, no con el ciclo semanal | no es una porción de lo incluido |
| V34 | Un cliente que agota su tope calla **solo él**; los demás siguen atendiendo | el caso difícil de diagnosticar desde fuera |
| V35 | Los avisos al 80 % y al 100 % siguen llegando, sin duplicar | dedupe por umbral y período |
| V36 | La suma de topes no puede superar el saldo sobre el que se calculan | invariante conservada |

### R7 · La barra — `vitest` en aplicación, consola y paquete compartido

| # | Qué comprueba | Estado esperado |
|---|---|---|
| V37 | La pantalla del partner muestra proporción y fecha, **no** la cifra del pool | **R7.1** |
| V38 | El panel de operador **sí** muestra las cifras absolutas | **R7.2** |
| V39 | El medidor conserva sus tres valores y su texto alternativo | **R7.4**: quien usa lector de pantalla recibe lo mismo |
| V40 | El saldo **comprado** sigue mostrándose en unidades | **R7.6**: es dinero que el partner pagó |
| V41 | El aviso de pausa ya **no** pinta «X de Y» | `composer.tsx` del paquete compartido |
| V42 | El texto de desbloqueo dice las salidas que ahora existen | hoy dice *«esperar no lo desbloquea»*, y con el pool semanal **esperar sí lo desbloquea** |
| V43 | El medidor de **ventana de contexto** y el del **turno** siguen intactos | R7 abstrae el pool, no todo número en pantalla |

**43 comprobaciones.** Las de `tests/isolation/` bloquean merge.

---

## El recorrido de humo, de punta a punta

Prueba manual que demuestra la spec entera. Si esto funciona, funciona.

1. **Deja un partner con el pool casi vacío.** Pide turnos hasta que quede poco.
   → La barra baja. No aparece ninguna cifra de tokens del pool.
2. **Agota el pool.** → El trabajo **continúa** si hay saldo comprado, y la
   pantalla dice de qué bolsillo sale. Nada se detiene.
3. **Vacía también el saldo comprado.** → Pausa por tope. Las confirmaciones
   pendientes **siguen ahí**. Ningún teammate desaparece del roster. El texto
   dice cuándo vuelve el pool.
4. **Compara las tres pantallas** en ese instante: consola, panel de operador y
   Cuenta en la aplicación. → El mismo período y el mismo dato. El operador ve
   cifras; el partner, barra.
5. **Adelanta el reloj más allá del vencimiento del partner** y deja correr el
   cron. → El pool vuelve solo, completo, y lo que no se había gastado **no** se
   suma.
6. **Haz el mismo trabajo con el cerebro barato y con el caro.** → El caro
   consume más pool; el coste en dólares de agotar el pool es el mismo.
7. **Mira el coste del mes en el panel de operador.** → `complete = true` y cero
   filas sin valorar para los modelos que vendemos.

## Lo que este recorrido NO prueba, y hay que decirlo

- **Que los tamaños de pool sean los correctos.** Esta spec preserva el volumen
  mensual de hoy; qué debe dar cada plan se decide en la Spec B, con el turno
  real ya medido.
- **Que el margen sea bueno.** Prueba que el margen es **calculable**, que es
  otra cosa y es la que faltaba.
- **Nada de cobro.** No hay Stripe aquí.
