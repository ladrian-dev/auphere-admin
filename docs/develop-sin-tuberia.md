# `develop` sin tubería

> Decisión de Luis, 2026-11-03: `develop` deja de pasar por `ci` para que un
> arreglo pequeño llegue a staging en minutos. Producción no cambia.

## Qué corre ahora

| Evento | Antes | Ahora |
|---|---|---|
| Push a `develop` | `ci` + `deploy-staging` esperando a `ci` (~85 min) | Solo `deploy-staging`, sin espera (~10 min) |
| PR a `develop` | `ci` | Nada |
| PR a `main` | `ci` | Igual |
| Push a `main` | `ci` + `deploy-prod` esperando a `ci` | Igual |

`ci` sigue pudiéndose lanzar a mano sobre `develop`:

```bash
gh workflow run ci --ref develop
```

GitHub puede no mostrar el botón ni aceptar la orden hasta que este cambio llegue
a `main`, que es la rama por defecto.

## Por qué

La medida es del run de `ci` del 2026-11-03 (41690169789): 72 minutos, de los que
67 son el `pytest` de la API.

| Parte de `ci` | Tiempo |
|---|---|
| `tests/integration` | 28 min |
| `tests/isolation` | 24 min |
| `tests/unit` | 16 min |
| Cada uno de los otros seis jobs | Menos de 6 min |

Hasta el 2026-10-22 `ci` tardaba 26–36 minutos. Desde el 2026-10-28 tarda 42–79.
Esa subida sigue sin explicar: esta decisión la esquiva, no la arregla.

## Qué se pierde

- **Nada comprueba `develop` por sí solo.** Una regresión llega a staging, y staging
  lo usan partners en beta.
- **Un test de aislamiento en rojo ya no para el camino a staging.** Sigue parando
  el de producción: `deploy-prod` no avanza sin `ci` en verde. La garantía en
  runtime no cambia; lo que se retrasa es enterarse.
- **Los fallos se acumulan hasta el PR a `main`.** `pytest -x` para en el primero,
  así que cada fallo acumulado puede costar otra hora de `ci`.

## Qué sigue protegiendo staging

- La task de migración sigue siendo bloqueante: si falla, no se rueda ningún servicio.
- El circuit breaker de ECS sigue revirtiendo un servicio que no arranca.
- Una imagen que no construye sigue abortando el despliegue.

## Qué hacer a cambio

1. Antes de fusionar en `develop`: `./scripts/verify.sh lint` y los archivos de
   prueba de lo tocado.
2. Antes de abrir el PR a `main`: lanzar `ci` a mano sobre `develop`, para no
   descubrir los fallos con el PR ya abierto.

## Cómo volver

Revertir el commit que introdujo este documento devuelve los disparadores de
`ci.yml` y la espera de `deploy-staging.yml`.

## Archivos que toca el cambio

- `.github/workflows/ci.yml`: disparadores.
- `.github/workflows/deploy-staging.yml`: fuera la espera a `ci` y su permiso.
- `.github/workflows/deploy-prod.yml`: solo comentarios.
- `docs/spec-driven-development.md`, `docs/app-movil.md`,
  `docs/go-live-consola-y-teammates.md` e `infra/terraform/README.md`: lo que
  describían y deja de ser cierto.
