# Licencias — el navegador de respaldo (spec 047, T203, §VIII)

Dependencias de `apps/renderer`, el servicio de renderizado del requisito 59.2
(research D50). **Ninguna entra en la API ni en el worker**: viven solo en esta
imagen. Lo que la API gana es `renderer_client.py`, que usa `httpx` y
`pydantic-settings`, ya instalados.

Leídas el 2026-10-29 en el entorno instalado desde `apps/renderer/uv.lock`
(`.venv/lib/python3.11/site-packages/*.dist-info/licenses/`). Las versiones son
las del lock, no las pedidas. Ninguna es AGPL ni «Apache modificada», ninguna
alcanza el uso en red y ninguna limita el uso multi-tenant ni el alojamiento como
servicio.

## Directas

| Paquete | Versión | Licencia | Fichero leído | Párrafo que permite el uso |
|---|---|---|---|---|
| `playwright` (Python) | 1.64.1 | Apache-2.0 (`License-Expression: Apache-2.0`) | `playwright-1.64.1.dist-info/licenses/LICENSE` (202 líneas, la Apache 2.0 sin cambios; «Portions Copyright (c) Microsoft Corporation. Portions Copyright 2017 Google Inc.») | «Subject to the terms and conditions of this License, each Contributor hereby grants to You a perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable copyright license to reproduce, prepare Derivative Works of, publicly display, publicly perform, sublicense, and distribute the Work and such Derivative Works in Source or Object form.» (§2) |
| Chromium (el navegador de la imagen base) | 156.0.8078.4 (revisión 1248, la que fija `playwright/driver/package/browsers.json`) | BSD-3-Clause | `LICENSE` de `chromium/src` (leído en chromium.googlesource.com; el binario no se descargó en local) — «Copyright 2015 The Chromium Authors» | «Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met» |
| `fastapi` | 0.162.0 | MIT | `fastapi-0.162.0.dist-info/licenses/LICENSE` — «Copyright (c) 2018 Sebastián Ramírez» | «Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software» |
| `uvicorn` | 0.54.0 | BSD-3-Clause | `uvicorn-0.54.0.dist-info/licenses/LICENSE.md` — «Copyright © 2017-present, Encode OSS Ltd» | «Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met» |

**Lo que trae dentro el paquete `playwright`.** El *wheel* lleva el driver de
Node: `playwright/driver/package/LICENSE` es la misma Apache 2.0 y su `NOTICE`
dice «Copyright (c) Microsoft Corporation» y que contiene código de Puppeteer
(Apache 2.0). `playwright/driver/LICENSE` es la licencia de Node.js (MIT, con
las de sus dependencias, 2.946 líneas). Las únicas menciones a la GPL ahí son
dos ficheros de construcción de ICU4C (`aclocal.m4`, `config.guess`) con la
excepción de Autoconf, que no llegan al binario. Los paquetes npm que el driver
lleva empaquetados (`package/lib/*.LICENSE`) son MIT, ISC, BSD-3-Clause y Blue
Oak; ninguno copyleft.

**Chromium.** Su política de terceros (`docs/adding_to_third_party.md`, leída
el 2026-10-29) clasifica la GPL como restringida y solo la admite en lo que no
se distribuye; la LGPL está en su lista de permitidas (p. ej. FFmpeg). Usado sin
modificar y como servicio, nada de eso impone condiciones al código de Nexus.
**Pendiente:** la lista por componente de esta versión (`about:credits`) no se ha
leído, porque la imagen no se construyó en local (disco); se lee en la primera
construcción.

## Transitivas de ejecución

Todas leídas en su fichero `LICENSE` del `dist-info`.

| Paquete | Versión | Licencia | Viene de |
|---|---|---|---|
| `starlette` | 1.10.0 | BSD-3-Clause («Copyright © 2018, Encode OSS Ltd») | fastapi |
| `pydantic`, `pydantic-core` | 2.14.1, 2.50.1 | MIT | fastapi |
| `typing-inspection`, `annotated-types`, `annotated-doc` | 0.4.4, 0.8.0, 0.0.5 | MIT | fastapi, pydantic |
| `opentelemetry-api` | 1.45.1 | Apache-2.0 | fastapi |
| `anyio` | 4.15.1 | MIT | starlette |
| `idna` | 3.20 | BSD-3-Clause | anyio |
| `h11` | 0.16.0 | MIT | uvicorn |
| `click` | 8.5.0 | BSD-3-Clause («Copyright 2014 Pallets») | uvicorn |
| `greenlet` | 3.5.6 | MIT AND PSF-2.0 (lo derivado de Stackless Python, PSF) | playwright |
| `pyee` | 13.0.1 en Python 3.11 · 14.0.0 en el 3.12 de la imagen | MIT (la 14.0.0, por sus metadatos en PyPI) | playwright |
| `typing-extensions` | 4.16.0 | PSF-2.0 | varias |

## Solo en desarrollo y CI (no entran en la imagen)

| Paquete | Versión | Licencia |
|---|---|---|
| `pytest`, `iniconfig`, `pluggy` | 9.2.0, 2.3.1, 1.7.0 | MIT |
| `pytest-asyncio` | 1.4.1 | Apache-2.0 |
| `httpx`, `httpcore` | 0.28.1, 1.0.9 | BSD-3-Clause |
| `certifi` | 2026.10.23 | MPL-2.0 (recíproca por fichero; solo se usa, no se modifica) |
| `ruff` | 0.15.12 | MIT |
| `mypy`, `mypy-extensions`, `librt`, `ast-serialize` | 2.3.0, 1.1.0, 0.16.0, 0.13.1 | MIT |
| `pathspec` | 1.1.1 | MPL-2.0 (ídem) |
| `packaging` | 26.3 | Apache-2.0 OR BSD-2-Clause |
| `pygments` | 2.21.0 | BSD-2-Clause |

La condición común de las MIT y BSD es conservar el aviso de copyright y el de
permiso en las copias; la de la Apache 2.0, además, conservar el `NOTICE`. La
imagen los conserva tal cual (los `dist-info` y `/ms-playwright` no se tocan).
