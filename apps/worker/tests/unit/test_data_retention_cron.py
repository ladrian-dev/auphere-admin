"""Retención por tipo de dato (WP-29) — la aritmética y las redes.

Lo que se prueba aquí es sobre todo lo que NO debe borrarse. Un cron que
suelta particiones es la pieza más destructiva del sistema: si la ventana
se calcula mal por un mes, se va un mes de conversaciones de todos los
clientes y no hay vuelta atrás. Por eso los casos son, en orden de
importancia:

1. una ventana mal configurada (0, negativa) **desactiva** el paso en vez
   de borrarlo todo;
2. la partición del mes en curso y la del siguiente nunca se sueltan,
   diga lo que diga la ventana;
3. lo que no encaja con el patrón de nombre que genera
   ``ensure_month_partition`` —la DEFAULT, cualquier adjunto a mano— se
   queda donde está;
4. y solo entonces: lo viejo se va.

El listado de particiones se sustituye por un doble para poder probar el
cálculo con calendarios que no existen en la base de test. El borrado
real de particiones lo cubre el cron de mantenimiento, que las crea.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from nexus_worker.streams import data_retention_cron as retention

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 8, 11, tzinfo=UTC)

# Lo que habría en la base tras dos años largos de operación, más la
# DEFAULT y una tabla adjuntada a mano.
_PARTITIONS = [
    "messages_y2024m01",
    "messages_y2025m06",
    "messages_y2026m07",
    "messages_y2026m08",  # mes en curso
    "messages_y2026m09",  # mes siguiente
    "messages_default",
    "messages_importado_2024",
]


@pytest.fixture
def catalog(monkeypatch):
    """Sustituye la lectura de ``pg_inherits`` y registra los DROP."""
    dropped: list[str] = []

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, statement, params=None):
            sql = str(statement)
            if "pg_inherits" in sql:
                return _Result(_PARTITIONS)
            if sql.startswith("DROP TABLE"):
                dropped.append(sql.removeprefix("DROP TABLE IF EXISTS ").strip())
            return _Result([])

        async def commit(self):
            return None

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self

        def all(self):
            return list(self._rows)

    monkeypatch.setattr(retention, "get_sessionmaker", lambda: _Session)
    return dropped


async def test_expired_partitions_are_dropped(catalog) -> None:
    dropped = await retention.drop_expired_partitions(parent="messages", months=12, now=NOW)
    assert dropped == ["messages_y2024m01", "messages_y2025m06"]
    assert catalog == dropped


async def test_a_zero_window_disables_the_step_instead_of_dropping_everything(
    catalog,
) -> None:
    """El fallo que un cron destructivo no puede permitirse. Una perilla
    sin poner o puesta a cero tiene que significar "no hagas nada"."""
    assert await retention.drop_expired_partitions(parent="messages", months=0, now=NOW) == []
    assert await retention.drop_expired_partitions(parent="messages", months=-3, now=NOW) == []
    assert catalog == []


async def test_the_shortest_enabled_window_still_spares_the_live_partitions(
    catalog,
) -> None:
    """``months`` son meses de historia CONSERVADOS, así que ni con la
    ventana mínima puede caer la partición en la que se está escribiendo
    ni la que el mantenimiento acaba de crear."""
    dropped = await retention.drop_expired_partitions(parent="messages", months=1, now=NOW)
    assert "messages_y2026m08" not in dropped  # mes en curso
    assert "messages_y2026m09" not in dropped  # mes siguiente
    assert "messages_y2026m07" not in dropped  # el mes de historia que se conserva
    assert dropped == ["messages_y2024m01", "messages_y2025m06"]


async def test_a_cutoff_in_the_future_stops_everything(catalog, monkeypatch) -> None:
    """El backstop del error de signo. Con la fórmula de hoy no se puede
    alcanzar — y por eso se prueba forzándolo: es la única línea entre un
    cambio futuro mal hecho y soltar la partición viva."""
    monkeypatch.setattr(retention, "_cutoff_month", lambda months, *, now: 10**9)
    assert await retention.drop_expired_partitions(parent="messages", months=24, now=NOW) == []
    assert catalog == []


async def test_the_default_partition_and_manual_attachments_are_left_alone(
    catalog,
) -> None:
    """Solo se sueltan las que encajan con el patrón que genera
    ``ensure_month_partition``. La DEFAULT es la red que recoge lo que
    caiga fuera de rango; soltarla por coincidencia de prefijo sería
    perder datos sin ni siquiera saber de qué mes."""
    await retention.drop_expired_partitions(parent="messages", months=1, now=NOW)
    assert "messages_default" not in catalog
    assert "messages_importado_2024" not in catalog


async def test_the_window_boundary_is_the_month_not_the_day(catalog) -> None:
    """24 meses desde agosto de 2026 es agosto de 2024: la de julio de
    2024 se va y la de agosto se queda. El error de uno aquí cuesta un mes
    de conversaciones de todos los clientes."""
    assert retention._cutoff_month(24, now=NOW) == retention._month_key(2024, 8)
    assert retention._cutoff_month(1, now=NOW) == retention._month_key(2026, 7)
    # Cruce de año, que es donde falla la resta hecha sobre el número de mes.
    assert retention._cutoff_month(6, now=datetime(2026, 2, 1, tzinfo=UTC)) == (
        retention._month_key(2025, 8)
    )


async def test_usage_records_retention_is_off_by_default() -> None:
    """No es un olvido: es facturación y tiene obligación legal de
    conservación. El test existe para que encenderla sea una decisión que
    alguien tenga que tomar rompiendo esta aserción."""
    from nexus_worker.config import WorkerSettings

    assert WorkerSettings().retention_usage_months == 0
    # Y las otras dos SÍ vienen encendidas: una política de retención
    # apagada por defecto vuelve a ser un documento.
    assert WorkerSettings().retention_media_days > 0
    assert WorkerSettings().retention_message_months > 0
