"""Los dos números que la spec 012 eligió, en un solo sitio.

Ninguno de los dos sale de una medición: los dos son decisiones, y por eso
llevan escrito **por qué** ese valor y no otro. El día que alguien quiera
cambiarlos, lo que hace falta no es el número — es el argumento.

Viven en ``core/`` porque los necesitan dos capas que no se importan entre sí:
el servicio que registra una máquina y la ruta que decide si la sesión sirve. Un
número que hace falta a los dos lados de una frontera no puede vivir en ninguno
de los dos: se copia, y las copias divergen. En este repositorio ya pasó con el
techo de la muestra de salida, que estaba escrito a mano en tres tests y en la
aplicación (``core/local_exec_limits.py``).
"""

from __future__ import annotations

from datetime import timedelta

#: Cuánto puede llevar abierta una sesión y seguir valiendo para **registrar una
#: máquina** (spec 012, R3.2).
#:
#: Se mide desde que la sesión se **abrió**, no desde que se usó por última vez.
#: Son cosas distintas y confundirlas es un error silencioso: una sesión abierta
#: hace seis días y usada hace diez segundos daría «recién confirmada» siendo
#: justo el caso que este umbral existe para atajar. **Tener la aplicación
#: abierta no es haber demostrado nada.**
#:
#: Una hora es el estándar de re-autenticación para acciones sensibles. En el
#: camino normal —instalar, entrar, volver— la sesión tiene segundos de vida y
#: esto no se nota; solo muerde donde debe.
SESSION_FRESH_FOR = timedelta(hours=1)

#: Cuántas máquinas activas puede tener una persona (spec 012, R4.1).
#:
#: Hasta la 012 no había ninguno, y el límite de facto era **la fricción de
#: pedir un código de emparejamiento**. Al retirar esa fricción hay que reponer
#: el freno, o no queda ninguno.
#:
#: No hay dato de producción detrás: cinco es el número que no estorba a quien
#: trabaje normal —portátil, sobremesa, y sitio para reinstalar y probar— y que
#: hace ruido si algo va mal. Las archivadas **no cuentan**; si contaran, cada
#: restablecimiento de contraseña cerraría el tope un poco más y acabaría siendo
#: un tope que se cierra solo.
MAX_ACTIVE_MACHINES_PER_PRINCIPAL = 5

__all__ = ["MAX_ACTIVE_MACHINES_PER_PRINCIPAL", "SESSION_FRESH_FOR"]
