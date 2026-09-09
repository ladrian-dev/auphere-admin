# Licencias de terceros — `apps/desktop`

Constitución §VIII: *las licencias se leen enteras antes de instalar*, y toda
dependencia nueva declara **el párrafo que permite el uso**. Esto se escribió
antes de ejecutar el `install`, no después.

| Dependencia | Versión | Licencia |
|---|---|---|
| `electron` | 44.3.0 | MIT |
| `electron-updater` | 6.8.9 | MIT |
| `electron-builder` | 26.15.3 | MIT (herramienta de build) |

## El párrafo que lo permite

MIT, texto íntegro en la parte que otorga:

> Permission is hereby granted, free of charge, to any person obtaining a copy of
> this software and associated documentation files (the "Software"), to deal in
> the Software **without restriction**, including without limitation the rights to
> use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
> the Software…

**Sin cláusula de red y sin restricción de multi-tenant**: se puede ofrecer como
servicio. Es lo que §VIII pide comprobar, y por lo que MIT y Apache-2.0 son un sí
mientras AGPL es un no —alcanza el uso en red— y las «Apache modificadas» hay que
leerlas enteras, porque varias prohíben exactamente el alojamiento como servicio.

## Lo que obliga

Conservar el aviso de copyright y el texto de la licencia en las copias
distribuidas. `electron-builder` incluye los avisos de las dependencias en el
paquete; la tarea de empaquetado (`T070`) comprueba que el fichero de licencias
viaja dentro.

## Lo que ya estaba

`vitest` y `typescript` (MIT) entraron con `T005` como herramientas de desarrollo:
no viajan en el paquete distribuido.
