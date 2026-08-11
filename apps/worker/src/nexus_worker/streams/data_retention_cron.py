"""Retención por tipo de dato (WP-29, RGPD) — política ejecutable.

El plan lo pide así, literal: "política de retención por tipo de dato
implementada como crons, no como documento". Hasta ahora había crons de
retención para lo que crecía sin control (checkpoints, versiones de
memoria) — es decir, retención por motivos de coste. Esto es la otra:
retención porque el dato es de una persona y no hay razón para
conservarlo indefinidamente.

Tres tipos, tres ventanas, y no es simetría decorativa:

1. **Transcripciones de notas de voz y punteros a media.** La ventana más
   corta. Una transcripción es la voz de un cliente convertida en texto
   —dato personal de una categoría que nadie pidió generar, se generó
   para poder contestarle— y deja de tener utilidad en cuanto la
   conversación se cierra. Se ANONIMIZA el mensaje (se vacían
   ``media_transcript`` y los punteros) en vez de borrarlo: el historial
   de la conversación sigue teniendo sentido con "[nota de voz]" donde
   estaba la transcripción.
2. **Mensajes.** Ventana larga. Se borran soltando la PARTICIÓN mensual
   entera, no con DELETE: es instantáneo, no deja hinchada la tabla y no
   compite con los escritores. La contrapartida es que la granularidad es
   el mes, lo cual es correcto para una política de retención (nadie
   redacta "13 meses y dos días").
3. **Consumo (``usage_records``).** Desactivado por defecto. Es la base de
   la facturación y tiene obligación legal de conservación; borrarlo por
   higiene sería cambiar un problema por otro. La perilla existe para
   poder fijar una ventana cuando el asesor fiscal diga cuál.

**Todo lo destructivo aquí es opt-in por configuración y con red de
seguridad**: nunca se sueltan la partición del mes en curso ni la del
siguiente, y una ventana absurda (0 o negativa) desactiva el paso en vez
de borrarlo todo. Un error de configuración tiene que producir "no se
borró nada", nunca "se borró todo".

Corre en la familia del scheduler (con elección de líder: exactamente una
instancia), como el resto de los barridos.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
import structlog
from nexus_api.db.base import get_sessionmaker

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 24 * 3600.0
BATCH_ROWS = 5_000
BATCH_PAUSE_S = 0.5

# Solo se sueltan particiones cuyo nombre encaje con el patrón que genera
# ``ensure_month_partition``. La tabla DEFAULT y cualquier cosa que
# alguien haya adjuntado a mano se quedan donde están: soltar una
# partición es irreversible y no se hace por coincidencia de prefijo.
_PARTITION_NAME = re.compile(r"^(?P<parent>[a-z_]+)_y(?P<year>\d{4})m(?P<month>\d{2})$")

_ANONYMISE_MEDIA_SQL = sa.text(
    """
    WITH doomed AS (
        SELECT id, created_at
          FROM messages
         WHERE created_at < :cutoff
           AND (media_transcript IS NOT NULL OR media_s3_key IS NOT NULL)
         LIMIT :batch
    )
    UPDATE messages m
       SET media_transcript = NULL,
           media_s3_key = NULL,
           media_filename = NULL
      FROM doomed d
     WHERE m.id = d.id AND m.created_at = d.created_at
    """
)

_PARTITIONS_SQL = sa.text(
    """
    SELECT c.relname
      FROM pg_inherits i
      JOIN pg_class c ON c.oid = i.inhrelid
      JOIN pg_class p ON p.oid = i.inhparent
     WHERE p.relname = :parent
     ORDER BY c.relname
    """
)


def _month_key(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def _cutoff_month(months: int, *, now: datetime) -> int:
    """Clave de mes por debajo de la cual una partición es desechable."""
    return _month_key(now.year, now.month) - months


async def anonymise_expired_media(*, days: int, now: datetime | None = None) -> int:
    """Vacía transcripciones y punteros a media de mensajes antiguos.

    Devuelve cuántas filas tocó. ``days <= 0`` desactiva el paso — no lo
    convierte en "borrar todo", que es el fallo que una perilla mal
    puesta produciría en el sentido contrario.
    """
    if days <= 0:
        return 0
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=days)
    sm = get_sessionmaker()
    total = 0
    while True:
        async with sm() as session:
            result = await session.execute(
                _ANONYMISE_MEDIA_SQL, {"cutoff": cutoff, "batch": BATCH_ROWS}
            )
            await session.commit()
        touched = result.rowcount or 0
        total += touched
        if touched < BATCH_ROWS:
            break
        # Por lotes y con pausa: el objetivo es no competir con los
        # escritores, igual que el barrido de checkpoints.
        await asyncio.sleep(BATCH_PAUSE_S)
    return total


async def drop_expired_partitions(
    *, parent: str, months: int, now: datetime | None = None
) -> list[str]:
    """Suelta las particiones mensuales de ``parent`` anteriores a la
    ventana. Devuelve los nombres soltados.

    ``months`` se lee como "meses de historia que se conservan": con 24,
    en agosto de 2026 sobrevive todo desde agosto de 2024. La partición
    del mes en curso y la del siguiente quedan siempre por encima del
    corte, así que nunca entran en el barrido.

    ``months <= 0`` desactiva el paso.
    """
    if months <= 0:
        return []
    now = now or datetime.now(UTC)
    cutoff = _cutoff_month(months, now=now)
    current = _month_key(now.year, now.month)
    if cutoff > current:
        # Inalcanzable con la fórmula de hoy (``cutoff = actual - meses``
        # con meses >= 1), y por eso mismo está escrito: es la única
        # línea que separa un error de signo futuro de soltar la
        # partición en la que se está escribiendo. Se para en seco y se
        # grita, en vez de borrar.
        log.error(
            "data_retention.cutoff_in_the_future",
            parent=parent,
            months=months,
            cutoff_month=cutoff,
            current_month=current,
        )
        return []

    sm = get_sessionmaker()
    async with sm() as session:
        names = list((await session.execute(_PARTITIONS_SQL, {"parent": parent})).scalars().all())

    dropped: list[str] = []
    for name in names:
        matched = _PARTITION_NAME.match(name)
        if not matched or matched.group("parent") != parent:
            # DEFAULT y adjuntos a mano: no son nuestras para soltar.
            continue
        key = _month_key(int(matched.group("year")), int(matched.group("month")))
        if key >= cutoff:
            continue
        async with sm() as session:
            # El nombre viene del catálogo y ha pasado por la expresión
            # regular, así que no puede llevar nada interpolable.
            await session.execute(sa.text(f"DROP TABLE IF EXISTS {name}"))
            await session.commit()
        dropped.append(name)
        log.warning("data_retention.partition_dropped", parent=parent, partition=name)
    return dropped


async def run_data_retention_once(
    *,
    media_days: int,
    message_months: int,
    usage_months: int,
    now: datetime | None = None,
) -> dict[str, object]:
    media = await anonymise_expired_media(days=media_days, now=now)
    messages = await drop_expired_partitions(parent="messages", months=message_months, now=now)
    usage = await drop_expired_partitions(parent="usage_records", months=usage_months, now=now)
    return {
        "media_rows_anonymised": media,
        "message_partitions_dropped": messages,
        "usage_partitions_dropped": usage,
    }


async def run_data_retention_cron(
    *,
    stop: asyncio.Event,
    media_days: int,
    message_months: int,
    usage_months: int,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
) -> None:
    log.info(
        "data_retention.start",
        media_days=media_days,
        message_months=message_months,
        usage_months=usage_months,
    )
    while not stop.is_set():
        try:
            summary = await run_data_retention_once(
                media_days=media_days,
                message_months=message_months,
                usage_months=usage_months,
            )
            log.info("data_retention.ok", **summary)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("data_retention.failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("data_retention.stopped")
