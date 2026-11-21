# Licencias: la app con el diseño nuevo (spec 069, T003, §VIII)

Dependencias nuevas de `apps/mobile` (Auphere Customers). Las versiones son las que fijó `npx expo install` para Expo SDK 58 y que quedan en `apps/mobile/pnpm-lock.yaml`.

Los textos se leyeron enteros el 2026-11-21 en `apps/mobile/node_modules/<paquete>/`.

Ninguna es AGPL ni una «Apache modificada», y ninguna limita el uso multi-tenant ni el alojamiento como servicio.

| Paquete | Versión | Licencia | Fichero leído | Párrafo que permite el uso |
|---|---|---|---|---|
| `react-native-svg` | 15.16.0 | MIT | `LICENSE`: «Copyright (c) [2015-2016] [Horcrux]» | «Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software» |
| `@shopify/react-native-skia` | 2.14.0 | MIT | `LICENSE.md`: «Copyright 2026-present, William Candillon · Copyright 2021-2026, Shopify Inc.» | el mismo párrafo MIT |
| `lucide-react-native` | 1.77.0 | ISC; los iconos derivados de Feather, MIT | `LICENSE`: «Copyright (c) 2026 Lucide Icons and Contributors», y para los iconos de Feather «Copyright (c) 2013-present Cole Bemis» | «Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby granted, provided that the above copyright notice and this permission notice appear in all copies.» |

## Notas

- **El motor de Skia** que trae `@shopify/react-native-skia` es BSD-3-Clause (Google), según su documentación. Permite redistribuir en binario con el aviso de copyright.
- **Los logos de WhatsApp, Instagram y Messenger** salen de Simple Icons 15.22.0, CC0 1.0: los mismos trazados que `apps/admin/src/components/brand/brand-marks.ts` (ver `simple-icons-CC0.txt`). Las marcas son de sus dueños y solo nombran el canal.
- **La «G» de Google** es la de `apps/console/public/third-party/google-g.svg`, para el botón «Continuar con Google» como pide su guía de marca.
- **Helvena** (Zippie Letras) es comercial, «All rights reserved», y **no entra en ningún build**.
  - Su licencia de uso en apps no se ha leído: el zip de `~/Downloads` no trae texto de licencia.
  - El interruptor `APP_HELVENA=1` solo la incrusta si los archivos están en `assets/fonts/helvena/`, que git ignora.
