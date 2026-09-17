# Licencias de terceros — `apps/desktop`

Constitución §VIII: *las licencias se leen enteras antes de instalar*, y toda
dependencia nueva declara **el párrafo que permite el uso**. Esto se escribió
antes de ejecutar el `install`, no después.

| Dependencia | Versión | Licencia |
|---|---|---|
| `electron` | 44.3.0 | MIT |
| `electron-updater` | 6.8.9 | MIT |
| `electron-builder` | 26.15.3 | MIT (herramienta de build) |
| `electron-context-menu` | 5.0.0 | MIT |
| `@fontsource-variable/inter-tight` | 5.3.0 | **OFL-1.1** (la fuente) · MIT (el empaquetado) |
| `@fontsource-variable/jetbrains-mono` | 5.3.0 | **OFL-1.1** (la fuente) · MIT (el empaquetado) |
| `@playwright/test` | 1.63.0 | Apache-2.0 (herramienta de desarrollo) |
| `@axe-core/playwright` | 4.13.0 | **MPL-2.0** (herramienta de desarrollo, no se distribuye) |

Las tres que entran en los paquetes compartidos por la spec 010, con la misma
regla: `react-resizable-panels` 4.12.4 (MIT, «Copyright (c) 2018 Brian Vaughn»),
`@tanstack/react-virtual` 3.14.13 (MIT, «Copyright (c) 2021-present Tanner
Linsley») y `use-stick-to-bottom` 1.1.6 (MIT, «Copyright (c) 2024 - present
StackBlitz»).

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

## Las dos que no son MIT y por qué se aceptan

**OFL-1.1** (las dos fuentes). El texto leído del paquete instalado dice:

> This Font Software is licensed under the SIL Open Font License, Version 1.1.

Permite usar, estudiar, modificar y **redistribuir** el software de fuente, con o
sin modificaciones, incluida su venta como parte de un producto mayor. Lo único
que prohíbe es venderlo **por sí solo** y usar los nombres reservados en trabajos
derivados. Una aplicación que empaqueta la fuente para pintar su interfaz es
exactamente el caso permitido. Sin cláusula de red.

**MPL-2.0** (`@axe-core/playwright`). Copyleft **por fichero**: obliga a publicar
las modificaciones *de sus propios ficheros*, no del software que lo usa. Se
acepta porque es **herramienta de desarrollo**, no se distribuye con el producto
y no se modifica ninguno de sus ficheros. Queda declarado aquí para que la
decisión sea visible y no haya que volver a razonarla.

## Lo que ya estaba

`vitest` y `typescript` (MIT) entraron con `T005` como herramientas de desarrollo:
no viajan en el paquete distribuido.
