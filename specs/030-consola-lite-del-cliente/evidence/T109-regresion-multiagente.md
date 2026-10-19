# T109 — La batería de evaluación antes y después del multiagente (CE-006)

**Fecha:** 2026-10-19 · **Antes:** código `6c7b9857` (el último anterior a la
spec 030, migraciones hasta 0146) · **Después:** `main@28a5b562` más el cambio
de cierre de la spec, migrado a la cabeza (0157, con 0152–0153).

## Qué se compara

CE-006: «tras el despliegue del multiagente, los clientes existentes responden
igual: su batería de evaluación da el mismo resultado que antes». La
comparación se hizo **con el código de cada lado**:

1. Una base nueva (`nexus_t109`, local) migrada con el código de antes.
2. Con ese código, un cliente por cada vertical que tiene batería semilla: dos
   números de WhatsApp, la configuración activa de su plantilla y su conjunto
   de evaluación (`services/evals/seed_datasets/`). Son los «clientes
   existentes» del ensayo.
3. La batería de cada cliente por el **pipeline real** (`run_eval`, el mismo
   camino que el botón «Run evals» del admin y que el cron de evaluación
   continua) con un modelo determinista, y una foto del resultado.
4. La misma base migrada a la cabeza con el código de después. 0153 crea el
   «Agente principal» de cada cliente y le asigna sus números.
5. La misma batería con el código de después y otra foto. Las dos fotos tienen
   que ser iguales.

El modelo determinista **depende de lo que recibe**: elige la intención a
partir del mensaje del cliente (así recorre los cinco manejadores y su parte de
la lista blanca), llama a la primera herramienta que se le ofrece y responde
con lo que ha visto. La foto guarda, por caso, el estado, las aserciones, las
herramientas despachadas con su estado y la respuesta, y el sha256 de cada
llamada al modelo (rol, modelo, mensajes y herramientas ofrecidas), con los
identificadores y las horas normalizados. Con el código de después también
anota qué configuración contesta en cada número (`agent_for_channel`).

Herramienta: `apps/api/scripts/dev_eval_battery_snapshot.py` (`seed`,
`snapshot`, `compare`). Solo usa APIs que existen a los dos lados y se niega a
correr fuera de una base local.

## Resultado

| Cliente (vertical) | Casos | Antes | Después | Llamadas al modelo | Mismo contexto y resultado | Misma configuración en cada número |
|---|---|---|---|---|---|---|
| aesthetic-clinic-v1 | 30 | 25/30 · 0,833 | 25/30 · 0,833 | 90 | sí | sí |
| barbershop-v1 | 15 | 14/15 · 0,933 | 14/15 · 0,933 | 45 | sí | sí |
| beauty-salon-v1 | 8 | 7/8 · 0,875 | 7/8 · 0,875 | 24 | sí | sí |
| dental-v1 | 8 | 7/8 · 0,875 | 7/8 · 0,875 | 24 | sí | sí |
| medspa-v1 | 8 | 8/8 · 1,000 | 8/8 · 1,000 | 24 | sí | sí |
| nail-studio-v1 | 8 | 7/8 · 0,875 | 7/8 · 0,875 | 24 | sí | sí |
| spa-v1 | 8 | 7/8 · 0,875 | 7/8 · 0,875 | 24 | sí | sí |
| **Total** | **85** | | | **255** | **7/7** | **7/7** |

Tras 0152–0153 cada cliente tiene un solo agente («Agente principal»), con una
versión activa, y es dueño de todos sus números (3/3: los dos sembrados y el
que crea la propia batería).

Los fallos son del modelo de juguete, no de la plataforma. Llama siempre a la
primera herramienta que ve, así que un caso que espera otra herramienta falla,
y falla igual a los dos lados. Lo que se mide es la igualdad, no la nota.

## La comparación no es vacía

| Control | Esperado | Resultado |
|---|---|---|
| Dos fotos seguidas con el código de antes | iguales | iguales |
| Quitar `booking.check_availability` de la lista blanca de la barbería | distinta solo la barbería | **distinta**: cambian los casos y el contexto del modelo |
| Añadir un punto al prompt de la barbería | distinta solo la barbería | **distinta**: cambia el contexto del modelo |
| Restaurar los dos cambios | iguales | iguales |

La primera versión del ensayo mandaba todos los casos al manejador `info`. El
primer control **no** detectó el cambio, porque esa herramienta solo se ofrece
al reservar. Por eso la intención se elige ahora a partir del mensaje del
cliente. Las tablas de arriba son de la segunda versión, repetida entera desde
una base nueva.

## Lo que esto no cubre

- **Los clientes reales de producción.** Son las siete plantillas semilla, no
  las configuraciones de Cultor, Amacrux y demás. Comparar sus baterías de
  producción exige leer su historial de `eval_runs` (antes y después del
  10-oct) o correrlas con el modelo real; la sesión no tuvo permiso para leer
  datos de producción. Ver [T110-produccion.md](T110-produccion.md).
- **El modelo real.** Con Claude la respuesta no es determinista. Lo que se
  prueba es que el modelo recibe exactamente lo mismo (prompt, herramientas,
  historial) y que todo lo que la plataforma hace con su respuesta sale igual.
- **El despachador por número.** La batería fija la configuración y no pasa por
  `channel → agente`. Que en cada número conteste la misma configuración se
  comprueba aparte, aquí (`agent_for_channel` por número) y en T020/T091.

## Cómo repetirlo

```bash
git worktree add --detach /tmp/pre030 6c7b9857 && (cd /tmp/pre030/apps/api && uv sync --extra dev)
export NEXUS_DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5433/nexus_t109 NEXUS_REDIS_URL=redis://localhost:6379/12
docker exec -i nexus-postgres psql -U nexus -d nexus -c "CREATE DATABASE nexus_t109"
SNAP=$PWD/apps/api/scripts/dev_eval_battery_snapshot.py
(cd /tmp/pre030/apps/api && uv run alembic upgrade head && uv run python $SNAP seed && uv run python $SNAP snapshot --out /tmp/antes.json)
(cd apps/api && uv run alembic upgrade head && uv run python $SNAP snapshot --out /tmp/despues.json && uv run python $SNAP compare /tmp/antes.json /tmp/despues.json)
```
