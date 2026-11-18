# La tubería en 30 minutos

> Petición de Luis, 2026-11-18: un despliegue a producción no puede tardar dos
> horas. Tope: 30 minutos de push a `main` a servicios rodados.

**Estado: en producción desde el 2026-11-18. `deploy-prod` pasa de 1 h 37 min a
14 min 30 s; `ci`, de 1 h 31 min a unos 7,5 min.**

Fuera de la regla de Spec-Driven Development: no cambia el comportamiento del
producto, solo cómo y dónde corren sus pruebas. Mismo caso que
[`develop-sin-tuberia.md`](develop-sin-tuberia.md).

## Lo medido

`deploy-prod` del 2026-11-17 (run 44196268772): 1 h 37 min. De ellos, 1 h 30 min
esperando a `ci`; después, 6,5 min de imágenes, migración y servicios.

`ci` del mismo commit (44196268814): todos los jobs acaban en menos de 7 min salvo
`test-api`, que tarda 1 h 31 min:

| Tramo de `test-api` | Tiempo |
|---|---|
| Hasta arrancar `pytest` | 45 s |
| Colección de las 10 844 pruebas de la API | 1 min 46 s |
| `pytest` de la API, en serie | 81,7 min |
| OpenAPI, `companion_evals`, worker, channels, mcp (en serie, detrás) | 5,5 min |

Por directorio, sumando el tiempo por archivo del log:

| Directorio | Tiempo | Pruebas | Por prueba |
|---|---|---|---|
| `tests/integration` | 39,7 min | 2753 | 0,87 s |
| `tests/isolation` | 27,5 min | 3962 | 0,42 s |
| `tests/unit` | 12,8 min | 3947 | 0,19 s |
| `tests/evals` | 1,6 min | 171 | 0,57 s |

No hay un puñado de pruebas lentas que quitar: el archivo más caro son 7 min de 774.
**El coste es fijo por prueba**, y la mayor parte es el desmontaje de `db_session`.
En una muestra de 135 pruebas (4 archivos), en este Mac:

| Por prueba | Antes | Postgres sin durabilidad | Y vaciado sin `TRUNCATE` |
|---|---|---|---|
| Preparación | 0,12 s | 0,10 s | 0,11 s |
| La prueba | 0,14 s | 0,14 s | 0,14 s |
| Desmontaje | **0,41 s** | 0,12 s | **0,04 s** |
| La muestra entera | 95 s | 53 s | 44 s |

La causa la encontró la investigación del 2026-11-03, que quedó sin confirmar en
`ci/test-api-rapido`: el `TRUNCATE … CASCADE` alcanza **todas** las tablas del
cliente, tengan filas o no, y cambia los ficheros de cada una. El coste de cada
prueba crecía con cada migración que añadía tablas, no con lo que la prueba
escribía. Por eso la suite no crecía en línea recta, sino más deprisa: más pruebas,
y cada una más cara.

## Por qué no se saca ninguna prueba de la tubería

Se planteó repartir: unas en la tubería, otras solo en local. No resuelve esto:

- Lo más caro de `tests/isolation` son los barridos de rutas
  (`test_phone_cannot_reach_partner_or_admin`, `test_lite_route_scope`,
  `test_console_scope`: 18 min entre los tres). Un test de aislamiento en rojo
  bloquea el paso a producción (constitución), y en local nadie los corre enteros.
- Lo que se olvida en local es justo lo que ha roto la tubería tres veces (el
  worker, `mypy`, el lockfile). Lo que solo corre en local acaba sin correr.
- El coste estaba en el desmontaje, igual para todas. Quitar la mitad de las
  pruebas ahorra la mitad hoy y nada del crecimiento.

El reparto queda así: **en local**, `./scripts/verify.sh lint` y las pruebas de lo
tocado (como hasta ahora); **en la tubería**, todo, en paralelo.

## El arreglo

1. **Vaciar sin truncar** (`_empty_database`, en `apps/api/tests/conftest.py`).
   Borra solo las tablas con filas, con los mismos locks y el mismo alcance que el
   `TRUNCATE`, y reinicia las secuencias. El coste sigue a lo que escribió la
   prueba, no al tamaño del esquema. `tests/integration/test_empty_database.py` le
   pregunta a Postgres qué alcanza el `TRUNCATE` y exige lo mismo, así que una tabla
   nueva entra sola. Portado de `ci/test-api-rapido`, sin su parte de `pytest-xdist`.
2. **Postgres sin durabilidad.** En la tubería, `fsync`, `synchronous_commit` y
   `full_page_writes` apagados (nada de esa base sobrevive al job); en cualquier
   base de pruebas, `synchronous_commit = off` (lo pone el `conftest`).
3. **La API en seis tramos paralelos.** Un job por tramo, cada uno con su runner y
   su Postgres, así que ninguno pisa las filas de otro. El reparto es por archivo
   —las pruebas de un archivo corren juntas y en su orden—, con lo que tardó cada
   archivo como peso (`apps/api/tests/ci_durations.json`). Lo calcula
   `apps/api/tests/ci_shards.py` **a partir de los archivos que hay en el disco**:
   un archivo nuevo entra solo, con la mediana como peso.
   `tests/unit/test_ci_shards.py` falla si el reparto deja fuera o repite alguno.
   Sin dependencias nuevas. El repositorio es público: los jobs no cuestan minutos.
4. **Lo que iba detrás de la API, a su propio job** (`test-packages`: OpenAPI,
   `companion_evals`, worker, channels, mcp), en paralelo con los tramos.
5. **Topes.** `timeout-minutes` en cada job (30 en los tramos, 20 en el resto), y
   un aviso en el log cuando un tramo pasa de 15 min.
6. **`--maxfail=10` en vez de `-x`, y `fail-fast: false`**: una pasada enseña los
   fallos de todos los tramos, no solo el primero.

`deploy-prod` no cambia: sigue esperando a `ci` (hasta 150 min, a propósito, hasta
que un run real demuestre el tiempo nuevo).

## Probado en local

La suite entera de la API, en los seis tramos y en paralelo, cada uno contra su
propio contenedor `pgvector/pgvector:pg16` con la durabilidad apagada, en este Mac
(12 núcleos compartidos por los seis tramos y los seis Postgres):

| Pasada | Reloj | Resultado |
|---|---|---|
| 1.ª (reparto con la medida vieja de `ci`) | 7 min 23 s | 10 864 pruebas; 1 rojo, de este cambio: la medida vivía en `apps/api/scripts/`, que barre `test_no_agendapro`, y nombra un archivo con «agendapro». Se movió a `tests/` |
| 2.ª (reparto definitivo, el de este commit) | **6 min 39 s** | 10 864 pruebas, **todo en verde**. Tramos de 5 min 29 s a 6 min 17 s; los 775 archivos, cada uno en un tramo |

Ningún rojo por el orden de las pruebas en ninguna de las dos pasadas, con
repartos distintos: repartir por archivo cambia qué pruebas comparten proceso, y
esta suite ya tuvo dependencias de orden. **Sí había una dependencia del orden de
las filas**, que no salió aquí y salió después en GitHub: ver [el rojo del PR
28](#el-rojo-del-pr-28-orden-de-las-filas).

## Medido en GitHub

`ci` lanzada a mano sobre `ci/tuberia-30-min` (run 44326664712, commit 7f0584fb),
2026-11-18: **7 min 51 s, todo en verde**. Antes, 1 h 31 min.

| Job | Tiempo |
|---|---|
| `test-api`, los seis tramos | 5,9 – 7,8 min |
| `test-console` | 5,5 min |
| `test-packages` | 4,2 min |
| El resto | menos de 3 min |

- Las 10 864 pruebas de la API, las mismas que en local, repartidas en seis tramos de
  `pytest` de 4 min 50 s a 6 min 37 s. En serie suman 33,5 min (antes, 81,7).
- `fsync=off` en los seis Postgres. Instalar y preparar cada tramo cuesta menos de
  15 s, y la colección, unos 25 s.
- Ningún aviso de los 15 min.

Con los JUnit de ese run se volvió a medir el reparto (`ci_durations.json`): los
seis tramos quedan en ~5,3 min de `pytest` cada uno, así que `ci` debería quedar en
unos 7 min.

### El primer despliegue con esto, 2026-11-18

| Run | Tiempo | Detalle |
|---|---|---|
| `ci` del PR #26 a `develop` | 7 min 31 s | verde |
| `deploy-staging` (`f6f53784`) | **15 min 38 s** | 8 min 38 s esperando a `ci`; imágenes 1:44, migración 1:08, servicios 3:47 |
| `ci` del PR #27 a `main` | 7 min 31 s | verde |
| `deploy-prod` (`ecbd0eda`) | **14 min 30 s** | 7 min 38 s esperando a `ci`; imágenes 1:49, migración 0:53, servicios 3:49 |

Antes: `deploy-prod` 1 h 37 min (run 44196268772). Las dos APIs respondieron
`{"status":"ok"}` después de desplegar; la de producción se comprobó contra el ALB.

La espera a `ci` de los dos despliegues sigue en 150 min. No hace falta bajarla:
deja de esperar en cuanto `ci` acaba, y cada job de `ci` tiene un tope de 30 min.

## El rojo del PR 28: orden de las filas

El 2026-11-18, el `ci` del PR 28 (de `main` a `develop`, solo código de la consola)
falló en `test_connector_access_admin.py::test_both_views_show_and_write_the_same_decision`.
Era la sexta ejecución en GitHub con este cambio; las cinco anteriores, verdes.

**La causa es este cambio.** La prueba lee dos auditorías sin `ORDER BY` y espera
la primera escrita en `[0]`. `TRUNCATE` daba a cada prueba tablas con ficheros
nuevos, y las filas salían en el orden de inserción por casualidad. El vaciado nuevo
borra: la tabla conserva sus páginas, el autovacuum apunta el hueco libre, y una
fila nueva puede caer delante de otra escrita antes.

Reproducido a voluntad con un Postgres con el autovacuum al máximo
(`autovacuum_naptime=1s`, umbrales a 0), la prueba repetida 120 veces en una sesión:

| `conftest` | Fallos | Tiempo |
|---|---|---|
| `TRUNCATE` (antes) | 0 / 120 | 8 min 16 s |
| Vaciado nuevo | **7 / 120** | 6 min 44 s |
| Vaciado nuevo + autovacuum apagado | **0 / 120** | 6 min 40 s |

**El arreglo** devuelve la garantía de antes sin perder el vaciado barato:

- El `conftest` apaga el autovacuum en cada tabla que vacía (`_stop_autovacuum`), en
  local y en la tubería.
- La tubería lo apaga también en todo el servidor (paso «postgres sin durabilidad ni
  autovacuum»), que cubre las tablas que una prueba de migración borra y vuelve a
  crear, y avisa si Postgres no lo toma.
- La prueba busca cada auditoría por su contenido, no por su posición.

No se han tocado las demás lecturas sin `ORDER BY` de las pruebas (un barrido
encuentra 48 candidatas, la mayoría de una sola fila): con el autovacuum apagado
vuelven a comportarse como con `TRUNCATE`. Una prueba nueva debería ordenar o buscar
por contenido de todos modos: Postgres nunca ha garantizado el orden sin `ORDER BY`.

## `ci` vuelve a `develop`

Decisión de Luis, 2026-11-18, en cuanto `ci` bajó a 8 minutos: se deshace
[`develop-sin-tuberia.md`](develop-sin-tuberia.md).

| Evento | Del 2026-11-03 al 18 | Desde el 2026-11-18 |
|---|---|---|
| PR a `develop` | Nada | `ci` |
| Push a `develop` | Solo `deploy-staging`, sin espera (~7 min) | `ci` + `deploy-staging` esperando a `ci` (~15 min) |
| PR a `main` | `ci` | Igual |
| Push a `main` | `ci` + `deploy-prod` esperando a `ci` | Igual |

Staging tarda unos 8 minutos más en recibir un arreglo; a cambio, un test de
aislamiento en rojo vuelve a parar el camino a staging, que usan partners en beta.

## Cómo mantenerlo

- **Volver a medir el reparto**, con los JUnit de un run de `ci` (se guardan 14 días):
  ```bash
  gh run download <run-id> -p 'junit-api-*' -D /tmp/junit
  cd apps/api && python tests/ci_shards.py --refresh /tmp/junit/*/*.xml
  ```
- **Un tramo pasa de 15 min** (aviso amarillo en el run): primero volver a medir;
  si sigue, añadir un número a `matrix.shard` en `ci.yml`. `--total` sale de
  `strategy.job-total`, no hay que tocar nada más.
- **Se borra o se renombra un archivo de prueba**: nada. La medida vieja no deja
  fuera ningún archivo; solo desequilibra el reparto hasta la próxima medida.
- **Una tabla nueva**: nada. El plan de vaciado sigue las claves foráneas desde
  `_TRUNCATE_TABLES`, igual que el `CASCADE`.

## Cómo volver

Revertir el commit. El `conftest.py` y `ci.yml` vuelven a ser los de antes; los
archivos nuevos (`ci_shards.py`, `ci_durations.json` y las dos pruebas) se van con él.
