# Contrato — el servidor MCP de `console.*`

El teammate opera la plataforma **llamando a herramientas, no navegando** (§VI). El
navegador de un agente es para lo que no tiene API; nunca para la consola de
Auphere, porque multiplica el coste, se rompe con cualquier cambio de interfaz y
mete una sesión autenticada de la consola dentro del ambiente del agente — que es
justo lo que el aislamiento prohíbe.

## Qué expone

Las herramientas `console.*` que ya existen, **filtradas por la lista blanca del
tenant**. El servidor no publica un catálogo propio ni un superconjunto: publica lo
que `agent_config.tools` dice para ese tenant, que es el contrato que ya fija
`tests/isolation/test_2_tool_whitelist_contract.py`.

## Invariantes

1. **El catálogo de la sesión es exactamente la lista blanca del tenant.** Ni una
   entrada más, venga de donde venga (Requisito 5.1).
2. **Nada del ambiente de la máquina entra.** Si el entorno declara herramientas
   adicionales, no se exponen y el intento se registra (Requisito 5.2).
3. **El partner no puede añadir herramientas** — ni desde su máquina ni desde la
   consola. El catálogo lo configura solo Auphere (Requisito 5.4). Es una
   prohibición, no una defensa oportunista.
4. **Fail-closed**: si no se puede garantizar (1), la sesión **no se abre**
   (Requisito 5.3). Una sesión que arranca sin poder demostrar su catálogo es peor
   que ninguna sesión.
5. **El `tenant_id` no viaja en la llamada.** Sale del contexto, igual que en el
   resto de la plataforma.
6. **Ninguna credencial de cliente final** entra en el ambiente donde corre el
   agente.

## El documento del catálogo

La edición pide el catálogo a la API en cada turno. Forma acordada:

```json
{"tools": [{"name": "console.clients.list", "reaches_network": false}]}
```

- `name` es obligatorio. Una entrada sin nombre **invalida el documento entero**: es
  más seguro no abrir la sesión que abrirla con un catálogo que no se entiende.
- `reaches_network` **ausente se conserva como no declarado**, y no declarado cuenta
  como que alcanza la red (Requisito 14.2). No se rellena con `false`: rellenarlo
  convertiría un olvido en permiso.
- Cualquier fallo —red, cuerpo ilegible, otra forma— significa lo mismo: *no se puede
  garantizar el catálogo*, y la sesión no abre (Requisito 5.3).

**El endpoint que sirve este documento todavía no existe**; es trabajo de API y tiene
su propia tarea. La forma se fija aquí para que las dos mitades se construyan contra
lo mismo.
