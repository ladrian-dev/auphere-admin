# Licencia — `pgvector` para Python (spec 047, T022, §VIII)

Dependencia nueva de `apps/api` y `apps/worker`: el tipo `vector` de SQLAlchemy
para los fragmentos de conocimiento de cada cliente (`knowledge_chunks`, ola 5).
La búsqueda es exacta y por cliente; no hay un índice ANN compartido
(requisito 38.4, research D14).

Leída entera el 2026-10-26 en el paquete instalado
(`site-packages/pgvector-0.5.1.dist-info/licenses/LICENSE.txt`). Es la MIT sin
cambios. No alcanza el uso en red (no es AGPL ni «Apache modificada») y no limita
el uso multi-tenant ni el alojamiento como servicio. Sin dependencias propias:
`numpy` es opcional y no se instala.

| Paquete | Versión instalada | Licencia | Fichero leído | Párrafo que permite el uso |
|---|---|---|---|---|
| `pgvector` | 0.5.1 | MIT (`License-Expression: MIT`) | `LICENSE.txt` — «Copyright (c) 2021-2026 Andrew Kane» | «Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software» |

La única condición es conservar el aviso de copyright y el de permiso en las
copias del software. La extensión `vector` de PostgreSQL ya estaba en la imagen
de desarrollo (`infra/postgres`) y la crea el `conftest` de las pruebas; en
Aurora se habilita con `CREATE EXTENSION vector` en la migración que la use.
