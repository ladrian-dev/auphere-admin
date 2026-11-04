# Bug Assessment: el modal de las pruebas dice 4 o 5 veces lo que cuestan

- **Slug**: el-modal-de-pruebas-exagera-el-coste
- **Created**: 2026-11-04
- **Source**: Luis (sesión del 2026-11-04), captura del modal y logs de staging
- **Verdict**: valid
- **Severity**: medium

## Report

«Sale un modal que dice que costará X pero es demasiado; quizá ni debería mostrarse.»

## Symptom

«¿Ejecutar 17 pruebas? Costará unos 10,97 USD.» Las pasadas enteras de esas 17 pruebas
costaron de 0,92 a 1,32 USD de proveedor: de 2,03 a 2,91 USD a precio de venta.

## Reproduction

`estimate.py`, con Sol (4 / 20 USD por millón):
17 × 3 × (4 × 0,017 + 4 × 0,0052 + 0,009) × 2,2 = **10,97 USD**, exacto.

## Root cause

- Sin caché: el 82 % de la entrada del agente sale de ella, a una décima parte del precio.
- Salida de 250 tokens por llamada; la medida es de unos 45.
- 4 mensajes del cliente simulado por pasada; los medidos son 1,4.
- Cuenta un juez que en staging no corría, y no cuenta el clasificador.

Lo de fondo: «Construcción y pruebas» la paga Auphere hasta el tope, así que confirmar un
gasto normal es fricción sin decisión detrás.
