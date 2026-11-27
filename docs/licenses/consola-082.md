# Licencias: datos al día en la consola (spec 082, T005, §VIII)

Una dependencia nueva de `apps/console`, en el lockfile raíz (`pnpm-lock.yaml`).

Los textos se leyeron enteros el 2026-11-26 en `apps/console/node_modules/@tanstack/react-query/LICENSE` y `node_modules/.pnpm/@tanstack+query-core@5.108.4/node_modules/@tanstack/query-core/LICENSE`.

**No es AGPL ni una «Apache modificada».** No limita el uso multi-tenant ni el alojamiento como servicio.

| Paquete | Versión | Licencia | Fichero leído | Párrafo que permite el uso |
|---|---|---|---|---|
| `@tanstack/react-query` | 5.108.4 | MIT | `LICENSE`: «Copyright (c) 2021-present Tanner Linsley» | «Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software» |
| `@tanstack/query-core` | 5.108.4 (la trae la anterior) | MIT | `LICENSE`: mismo autor y texto | el mismo párrafo MIT |

## Notas

- **Sin más dependencias en tiempo de ejecución.** `@tanstack/query-core` no trae ninguna.
- **`peerDependencies`:** `react ^18 || ^19`. La consola usa React 19.2.4.
- **La misma serie que el teléfono.** La app (`apps/mobile`, su propio workspace) usa `^5.104.5`. Las claves e invalidaciones de la consola siguen las de `apps/mobile/src/api/query.ts`.
