# Licencias — el renderer de la aplicación de escritorio (spec 003, §VIII)

Dependencias nuevas de `apps/desktop` y `packages/companion-ui`, leídas enteras
en `node_modules` del workspace: las de la 003 el 2026-09-10, y las tres de
`@testing-library` el 2026-09-11, al abrir la US4 (los tres ficheros `LICENSE`
leídos uno a uno; las versiones son las instaladas, no las pedidas). Todas MIT. Ninguna alcanza el
uso en red (no es AGPL ni «Apache modificada») ni limita el uso multi-tenant.

| Paquete | Versión instalada | Licencia | Fichero leído | Párrafo que permite el uso |
|---|---|---|---|---|
| `react`, `react-dom` | 19.2.4 | MIT | `react/LICENSE` — «Copyright (c) Meta Platforms, Inc. and affiliates.» | «Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software» |
| `vite` | 8.2.1 | MIT | `vite/LICENSE.md` — «Vite is released under the MIT license: Copyright (c) 2019-present, VoidZero Inc. and Vite contributors» | ídem |
| `@vitejs/plugin-react` | 6.0.5 | MIT | `@vitejs/plugin-react/LICENSE` — «Copyright (c) 2019-present, Yuxi (Evan) You and Vite contributors» | ídem |
| `tailwindcss`, `@tailwindcss/vite` | 4.3.3 | MIT | `tailwindcss/LICENSE` — «Copyright (c) Tailwind Labs, Inc.» | ídem |
| `tw-animate-css` | 1.4.0 | MIT | ya en `apps/console` con la misma licencia | ídem |
| `@types/react`, `@types/react-dom`, `jsdom` | dev | MIT | solo en desarrollo y tests | — |
| `@testing-library/react` | 16.3.2 | MIT | `@testing-library/react/LICENSE` — «The MIT License (MIT) · Copyright (c) 2017-Present Kent C. Dodds» | «Permission is hereby granted, free of charge, to any person obtaining a copy of this software … to deal in the Software without restriction» |
| `@testing-library/jest-dom` | 6.10.0 | MIT | `@testing-library/jest-dom/LICENSE` — «Copyright (c) 2017 Kent C. Dodds» | ídem |
| `@testing-library/user-event` | 14.6.4 | MIT | `@testing-library/user-event/LICENSE` — «Copyright (c) 2020 Giorgio Polvara» | ídem |

**De KiroCrew no entra ningún fichero.** El plan copia decisiones (supervisión
del backend, token local, bandeja e instancia única), no código; la licencia
Apache-2.0 del sustrato sigue leída en `apps/edition/THIRD-PARTY-LICENSES.md`.
