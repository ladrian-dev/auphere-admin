# Validación de la 007

Cómo se comprueba, de punta a punta, que la cuota cobra por carril. Sin código de
implementación: esto es la guía de ejecución.

## Antes de nada

```bash
docker compose up -d
cd apps/api && uv run alembic upgrade head
```

## 1 · El invariante, que es lo que esta spec compra

El suelo se comprueba **sobre el catálogo real de la base**, no sobre una lista
escrita en un test. Una lista escrita a mano pasa en verde el día que alguien
añade un modelo y no la toca — que es justo el fallo que hay que impedir.

```bash
cd apps/api && uv run pytest tests/integration/ -k quota_floor -x
```

Esperado: un caso por carril y por modelo del catálogo. Con el catálogo de hoy,
dieciocho casos a 2,20x.

**Y hay que romperlo para creerlo.** Un test que pasa no demuestra que vigile.

**No sirve romper el dato.** El `conftest` de la API hace `DROP SCHEMA public
CASCADE` + `alembic upgrade head` al empezar cada sesión: la base se reconstruye
desde las migraciones y cualquier `UPDATE` hecho a mano desaparece antes del
primer caso. Se intentó, y el test pasó en verde — que es justo el falso verde
que este paso existe para cazar. (Ojo además con la base: `get_sessionmaker()`
desde un script apunta a `nexus`, la de desarrollo, no a `nexus_test`.)

Eso es **bueno**: quiere decir que el test vigila el catálogo **tal como lo
siembran las migraciones**, que es lo que llega a producción. Así que lo que se
rompe es la **fuente**:

```bash
cd apps/api && sed -i.bak 's/^_TARGET = "2.2"$/_TARGET = "0.5"/' \
  alembic/versions/0120_quota_weights_per_lane.py
uv run pytest tests/integration/test_quota_floor.py -q -p no:randomly   # DEBE fallar
mv alembic/versions/0120_quota_weights_per_lane.py.bak \
   alembic/versions/0120_quota_weights_per_lane.py
```

El fallo tiene que **nombrar el modelo y el carril**, uno por línea, con el peso
y la tarifa. Si falla sin decir cuál, el test no sirve: en producción nadie
sabrá qué fila mirar. Salida real en
[`evidence/floor-red.txt`](./evidence/floor-red.txt) — 21 carriles nombrados.

## 2 · La fórmula dice lo mismo en los dos sitios que debitan

```bash
cd apps/api    && uv run pytest tests/unit/ -k quota -x
cd apps/worker && uv run pytest tests/unit/ -k "quota or metering" -x
```

Esperado: una misma llamada produce la misma cifra en el camino de la API
(Companion y teammates) y en el del worker (canal). Hay un test que falla si
divergen.

## 3 · Nadie paga de más

```bash
cd apps/api && uv run pytest tests/unit/ -k "cliente_final or end_customer" -x
```

Esperado: el turno típico de cliente final (10 K / 8 K / 1 K) no sube. En
`claude-sonnet-4-6` baja de 5.210 a 5.148 unidades, un −1,2 %.

## 4 · La bolsa deja de perder dinero

```bash
cd apps/api && uv run pytest tests/unit/ -k margen -x
```

Esperado, con el turno de teammate (5 K / 4 K / 3 K) sobre `claude-sonnet-4-6` y
la bolsa agotada todas las semanas del mes:

| plan | margen antes | margen después |
|---|---|---|
| Pro | 11 % | 51 % |
| Team | −18 % | 34 % |
| Business | −42 % | 21 % |

## 5 · El aislamiento sigue en pie

```bash
cd apps/api && uv run pytest tests/isolation/ -x
```

Esperado: verde, incluido `test_pool_not_exposed_to_tenant.py` con los tres
nombres nuevos en su lista `FORBIDDEN`. **Un rojo aquí bloquea el merge.**

## 6 · Lo que corre la tubería, entero

```bash
./scripts/verify.sh
```

No la mitad. Lo que se olvida no son las pruebas de la API: son **el worker,
`mypy --strict`, el paquete compartido y el `next build`**, y han roto la tubería
dos veces por eso mismo (2026-09-11 y 2026-09-13). Se lee **la cola en crudo**,
no un resumen.

## 7 · El `downgrade()` es real

```bash
cd apps/api && uv run alembic downgrade -1 && uv run alembic upgrade head
```

Esperado: baja y sube sin error. Ninguna columna se borra en la subida, así que
la bajada no puede perder datos.

## Lo que **no** hay que validar, porque no cambia

- Saldos, bolsas en curso y consumo ya asentado: **nada se revalora** (D5). Si
  algún importe histórico cambia, es un defecto, no un efecto esperado.
