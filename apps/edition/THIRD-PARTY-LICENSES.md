# Licencias de terceros

Constitución §VIII: *las licencias se leen enteras antes de instalar*, y toda
dependencia nueva declara su licencia con **el párrafo que permite el uso**. Esto no
es una lista de nombres: es la cita que autoriza a ofrecer esto como servicio.

## KiroCrew `0.7.0` @ `37933a5` — Apache-2.0

**Lo que concede** (§2, *Grant of Copyright License*):

> …a perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable
> copyright license to reproduce, prepare Derivative Works of, publicly display,
> publicly perform, sublicense, and distribute the Work and such Derivative Works
> in Source or Object form.

Sin cláusula de red y sin restricción de multi-tenant: **se puede ofrecer como
servicio**. Esto es lo que ninguna otra base del campo permite — Suna es Elastic
License 2.0, Dify prohíbe el multi-tenant y n8n es Sustainable Use.

**Lo que obliga** (§4.d): conservar el `NOTICE` en lo distribuido. Está en
[`NOTICE`](./NOTICE), y `scripts/build-substrate-wheel.sh` **falla** si la rueda que
construye no lo lleva dentro — la obligación es una puerta del build, no una
costumbre.

**Lo que NO concede** (§6, *Trademarks*): los nombres comerciales, marcas y logos
quedan expresamente fuera del otorgamiento. Las marcas «Kiro» y «Kiro Crew» no están
licenciadas y no se usan.

## `@agentclientprotocol/claude-agent-acp` `0.75.1` — Apache-2.0

Mismos §2, §4.d y §6. Verificado en el `package.json` publicado en el registro.

## Lo que no entra, y por qué

**AGPL es un no** y no admite matices: alcanza el uso en red, que es exactamente lo
que hacemos. Cualquier «Apache modificada», Elastic License, BSL o Sustainable Use se
lee **completa** antes de instalar — varias prohíben justo el uso multi-tenant o el
alojamiento como servicio.
