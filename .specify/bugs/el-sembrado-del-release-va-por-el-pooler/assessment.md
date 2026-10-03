# Bug Assessment: el sembrado del release va por el pooler

- **Slug**: el-sembrado-del-release-va-por-el-pooler
- **Created**: 2026-10-03
- **Source**: encontrado al poner la rama 011 al día con `develop` — `ci` salía
  verde y `deploy-staging` fallaba en cada commit del día
- **Verdict**: valid
- **Severity**: high — aborta **todo** despliegue a staging, y abortaría el de
  producción por la misma razón. La base queda migrada y los servicios sin
  rodar: el despliegue muere a medias.

## Symptom

`deploy-staging` falla en el paso bloqueante «run migration task» en todos los
commits de `develop` del 2026-10-03 (los cuatro últimos seguidos; el anterior
verde es «the sidebar glides»). `ci` pasa en los mismos sha. La tubería imprime:

```
migration exit code: 1 (Essential container in task exited)
::error::La migración falló — deploy ABORTADO. Logs en /nexus/staging/migrate.
```

**Y el mensaje es falso.** En `/nexus/staging/migrate`, la migración termina
bien:

```
release: alembic upgrade head
INFO [alembic.runtime.migration] Running upgrade 0138_audit_vocab_money -> 0139_audit_vocab_words
release: seeding connectors catalog
Traceback (most recent call last):
  File "/app/apps/api/scripts/seed_connectors.py", line 62, in <module>
...
socket.gaierror: [Errno -2] Name or service not known
```

Lo que muere es el paso siguiente del mismo script, el sembrado del catálogo de
conectores, y muere en DNS.

## Root cause

Las dos mitades de `release.sh` leían URLs de base distintas:

| | lee | en staging apunta a |
|---|---|---|
| `alembic upgrade head` | `database_url_direct or database_url` (`alembic/env.py`) | el endpoint de Aurora |
| `seed_connectors.py` | `database_url`, vía `get_engine()` | `pgbouncer.nexus-staging.internal` |

`pgbouncer.nexus-staging.internal` es un nombre de Service Connect: lo resuelven
las tareas **inscritas en ese namespace**. La tarea de migración es un
`aws ecs run-task` suelto, no un servicio, así que para ella ese nombre no
existe — de ahí `gaierror` y no un error de conexión. Alembic nunca lo sufrió
porque iba al endpoint de Aurora, que resuelve en toda la VPC.

Dicho de otro modo: la tarea está **diseñada** para hablar directo, y el
sembrador era el único que se desviaba por el pooler. Tampoco le hace falta —
es una pasada única con `ON CONFLICT`, no tráfico de aplicación.

## Por qué todo salía verde

Ninguna prueba cubría esto, y no por descuido de una spec concreta:

- En local y en CI no hay pooler. `database_url_direct` va vacía y
  `get_engine()` apunta a la misma base que Alembic, así que las dos mitades
  coinciden y el fallo es **inobservable**.
- `scripts/seed_connectors.py` no es un módulo del paquete; nada lo importaba
  en los tests.
- La diferencia solo aparece cuando hay un pooler delante **y** quien corre no
  está en su namespace. Eso pasa en exactamente un sitio: la tarea de release.

## Fix

Un motor explícito para lo que corre en el release —`get_direct_engine()`, la
misma URL que usa Alembic y por la misma razón— y el sembrador pidiéndolo. Ver
`./fix.md`.

## Alternativa descartada

Inscribir la tarea de migración en el namespace de Service Connect, o apuntar
`NEXUS_DATABASE_URL` de esa tarea al endpoint directo. Las dos funcionan y las
dos son cambios de infraestructura que hay que aplicar con Terraform. Se
descartan porque dejan el defecto de fondo en pie: el código seguiría
decidiendo por qué camino va según una variable que en la tarea de release no
debería importar, y el próximo script que se añada al `release.sh` volvería a
tropezar. El arreglo en código hace que **todo** lo que corre ahí use la misma
URL, que es lo que el sitio pide.
