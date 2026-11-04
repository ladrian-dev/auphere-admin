"""La salida de ``nexus:inbound:dlq``: listar, descartar y reinyectar.

Bug ``dlq-sin-salida``. El consumidor aparcaba aquí los mensajes que agotaban sus
reintentos, el vigilante decía «revisar y reinyectar», y no había con qué. Se usa
desde ``scripts/ops/dlq.sh``; el manual es ``docs/dlq.md``.

    python -m nexus_worker.ops.dlq list     [--id ID] [--older-than 30d] [--newer-than 2h]
    python -m nexus_worker.ops.dlq discard  <selección> [--yes --reason TEXTO]
    python -m nexus_worker.ops.dlq reinject <selección> [--allow-stale] [--yes --reason TEXTO]

Tres reglas:

- **En seco por defecto.** Sin ``--yes`` no escribe nada, y el ensayo es el mismo
  comando: exige también la selección.
- **Nunca sale el cuerpo ni un teléfono.** El registro solo lleva ``Entry.public()``.
  Tampoco el ``wamid``, que lleva el teléfono codificado, ni ``dlq_error`` tal cual:
  un error de SQLAlchemy arrastra los parámetros del INSERT.
- **Reinyectar no contesta dos veces**, porque el consumidor no guarda dos veces
  (``provider_message_id``) ni toma dos veces (``messages.turn_id``). Por eso se
  niega sin ``provider_message_id``. Y se niega con más de 24 h salvo
  ``--allow-stale``: una entrada que nunca se guardó se trata como recién llegada,
  y ``accept_inbound`` abre la ventana de Meta desde ahora, cuando en Meta lleva
  tiempo cerrada. ``apps/api/tests/integration/test_dlq_reinject.py`` lo fija.

Salida: 0 hecho · 1 falló · 2 orden mal escrita · 3 hizo menos de lo pedido.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, cast

import structlog
from nexus_api.core.redis_client import get_redis
from nexus_api.core.streams import INBOUND_DLQ_STREAM, INBOUND_STREAMS, xadd_capped
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from nexus_worker.config import get_worker_settings
from nexus_worker.logging import configure_logging

log = structlog.get_logger(__name__)

DLQ_STREAM = INBOUND_DLQ_STREAM
#: La ventana de servicio de Meta: pasado esto, contestar ya no es contestar.
REINJECT_MAX_AGE_S = 24 * 3600
READ_BATCH = 500
#: Sin estos campos el consumidor acusa la entrada y la tira (``_to_event``).
REQUIRED_FIELDS = ("tenant_id", "channel_id", "user_id", "content")
MAX_CAUSE_CHARS = 200

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_PARTIAL = 3

_AGE = re.compile(r"^(\d+)([smhd])$")
_AGE_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86_400}

# Dónde acaba el error y empiezan los datos, y los datos que se cuelan antes.
_CAUSE_END = re.compile(r"\n|\[SQL:|\[parameters:|DETAIL:")
_QUOTED = re.compile(r"""(?<!class )'[^']*(?:'|$)|"[^"]*(?:"|$)""")
_KEY_VALUE = re.compile(r"=\([^)]*\)")
_WAMID = re.compile(r"wamid\.\S+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_LONG_NUMBER = re.compile(r"\+?\d[\d\s().-]{5,}\d")


def safe_cause(raw: str) -> str:
    """La causa, sin lo que el error arrastra del mensaje."""
    cause = _CAUSE_END.split(raw, maxsplit=1)[0].strip()
    cause = _QUOTED.sub("[valor]", cause)
    cause = _KEY_VALUE.sub("=([valor])", cause)
    cause = _WAMID.sub("[wamid]", cause)
    cause = _EMAIL.sub("[correo]", cause)
    cause = _LONG_NUMBER.sub("[número]", cause)
    return cause[:MAX_CAUSE_CHARS]


def parse_age(raw: str) -> int:
    """``30m``, ``12h``, ``7d``, en segundos."""
    match = _AGE.match(raw)
    if match is None:
        raise argparse.ArgumentTypeError(f"«{raw}» no es una antigüedad: usa 90s, 30m, 12h o 7d")
    return int(match.group(1)) * _AGE_UNITS[match.group(2)]


def human_age(seconds: int) -> str:
    days, rest = divmod(seconds, 86_400)
    hours, rest = divmod(rest, 3600)
    if days:
        return f"{days}d {hours}h"
    return f"{hours}h {rest // 60}m" if hours else f"{rest // 60}m"


def _text(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


def _entry_ms(entry_id: str | None) -> int | None:
    head = (entry_id or "").split("-", 1)[0]
    return int(head) if head.isdigit() else None


@dataclass(frozen=True, slots=True)
class Entry:
    entry_id: str
    #: Aquí van el cuerpo y el teléfono: fuera del ``repr`` y de ``public()``.
    fields: dict[str, str] = field(repr=False)
    #: Desde que el mensaje llegó, no desde que se aparcó.
    age_s: int

    @property
    def source_stream(self) -> str:
        return self.fields.get("dlq_source_stream", "")

    @property
    def tenant_id(self) -> str | None:
        return self.fields.get("tenant_id")

    @property
    def original(self) -> dict[str, str]:
        return {k: v for k, v in self.fields.items() if not k.startswith("dlq_")}

    @property
    def cause(self) -> str:
        return safe_cause(self.fields.get("dlq_error", ""))

    def public(self) -> dict[str, Any]:
        """Lo único de una entrada que sale al registro."""
        attempts = self.fields.get("dlq_attempts", "")
        return {
            "entry_id": self.entry_id,
            "tenant_id": self.tenant_id,
            "source_stream": self.source_stream,
            "age": human_age(self.age_s),
            "age_s": self.age_s,
            "attempts": int(attempts) if attempts.isdigit() else None,
            "cause": self.cause,
        }


async def _read_all(redis: Redis, *, now: float) -> list[Entry]:
    entries: list[Entry] = []
    start = "-"
    while True:
        # Los stubs de redis tipan xrange como unión amplia; la forma real es
        # list[(id, fields)], en bytes o en str según ``decode_responses``.
        batch = cast(
            "list[tuple[Any, dict[Any, Any]]]",
            await redis.xrange(DLQ_STREAM, min=start, max="+", count=READ_BATCH),
        )
        if not batch:
            return entries
        for raw_id, raw_fields in batch:
            entry_id = _text(raw_id)
            fields = {_text(k): _text(v) for k, v in raw_fields.items()}
            ms = _entry_ms(fields.get("dlq_source_entry_id")) or _entry_ms(entry_id) or 0
            entries.append(Entry(entry_id, fields, max(0, int(now - ms / 1000))))
        start = f"({_text(batch[-1][0])}"


def _select(entries: list[Entry], args: argparse.Namespace) -> list[Entry]:
    selected = entries
    if args.id:
        wanted = set(args.id)
        selected = [e for e in selected if e.entry_id in wanted]
    if args.older_than is not None:
        selected = [e for e in selected if e.age_s > args.older_than]
    if args.newer_than is not None:
        selected = [e for e in selected if e.age_s < args.newer_than]
    return selected


def _missing_ids(entries: list[Entry], args: argparse.Namespace) -> list[str]:
    present = {e.entry_id for e in entries}
    missing = [i for i in args.id or [] if i not in present]
    for entry_id in missing:
        log.warning("ops.dlq.id_not_found", entry_id=entry_id)
    return missing


async def _consumed_streams(redis: Redis) -> set[str]:
    """Los streams de entrantes con el grupo del consumidor. Publicar en otro
    dejaría la última copia del mensaje donde nadie la va a leer."""
    group = get_worker_settings().inbound_consumer_group
    consumed: set[str] = set()
    for stream in INBOUND_STREAMS:
        try:
            groups = await redis.xinfo_groups(stream)
        except ResponseError:  # el stream no existe
            continue
        if any(_text(g.get("name", "")) == group for g in groups):
            consumed.add(stream)
    return consumed


def _refusal(entry: Entry, *, consumed: set[str], allow_stale: bool) -> str | None:
    if entry.source_stream not in consumed:
        return "source_stream_not_consumed"
    original = entry.original
    if any(name not in original for name in REQUIRED_FIELDS):
        return "missing_fields"
    if not original.get("provider_message_id"):
        return "no_provider_message_id"
    if entry.age_s > REINJECT_MAX_AGE_S and not allow_stale:
        return "stale"
    return None


async def _move_to_source(redis: Redis, entry: Entry) -> tuple[Any, int]:
    """Publicar y borrar, los dos o ninguno: es la última copia del mensaje."""
    async with redis.pipeline(transaction=True) as pipe:
        await xadd_capped(pipe, entry.source_stream, entry.original)
        await pipe.xdel(DLQ_STREAM, entry.entry_id)
        new_id, deleted = await pipe.execute()
    return new_id, deleted


async def _list(redis: Redis, args: argparse.Namespace, now: float) -> int:
    entries = await _read_all(redis, now=now)
    selected = _select(entries, args)
    shown = selected[: args.limit]
    for entry in shown:
        log.info("ops.dlq.entry", **entry.public())
    log.info(
        "ops.dlq.summary",
        command="list",
        applied=False,
        total=len(entries),
        selected=len(selected),
        shown=len(shown),
        missing=len(_missing_ids(entries, args)),
        oldest=human_age(max(e.age_s for e in selected)) if selected else None,
        newest=human_age(min(e.age_s for e in selected)) if selected else None,
        by_tenant=dict(Counter(e.tenant_id for e in selected)),
        by_cause=dict(Counter(e.cause for e in selected)),
    )
    return EXIT_OK


async def _discard(redis: Redis, args: argparse.Namespace, now: float) -> int:
    entries = await _read_all(redis, now=now)
    selected = _select(entries, args)
    done = 0
    for entry in selected:
        if not args.yes:
            log.info("ops.dlq.would_discard", **entry.public())
            continue
        deleted = await redis.xdel(DLQ_STREAM, entry.entry_id)
        log.warning(
            "ops.dlq.discarded", **entry.public(), reason=args.reason, deleted=bool(deleted)
        )
        done += 1
    return _summary("discard", args, total=entries, selected=selected, done=done, refused=0)


async def _reinject(redis: Redis, args: argparse.Namespace, now: float) -> int:
    entries = await _read_all(redis, now=now)
    selected = _select(entries, args)
    consumed = await _consumed_streams(redis)
    done = refused = 0
    for entry in selected:
        refusal = _refusal(entry, consumed=consumed, allow_stale=args.allow_stale)
        if refusal is not None:
            log.warning("ops.dlq.refused", **entry.public(), refusal=refusal)
            refused += 1
            continue
        if not args.yes:
            log.info("ops.dlq.would_reinject", **entry.public())
            continue
        new_id, deleted = await _move_to_source(redis, entry)
        log.warning(
            "ops.dlq.reinjected",
            **entry.public(),
            reason=args.reason,
            new_entry_id=_text(new_id),
            deleted=bool(deleted),
        )
        done += 1
    return _summary("reinject", args, total=entries, selected=selected, done=done, refused=refused)


def _summary(
    command: str,
    args: argparse.Namespace,
    *,
    total: list[Entry],
    selected: list[Entry],
    done: int,
    refused: int,
) -> int:
    missing = len(_missing_ids(total, args))
    log.info(
        "ops.dlq.summary",
        command=command,
        applied=bool(args.yes),
        total=len(total),
        selected=len(selected),
        done=done,
        refused=refused,
        missing=missing,
    )
    return EXIT_PARTIAL if args.yes and (refused or missing) else EXIT_OK


_COMMANDS = {"list": _list, "discard": _discard, "reinject": _reinject}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m nexus_worker.ops.dlq",
        description="Listar, descartar y reinyectar nexus:inbound:dlq. Manual: docs/dlq.md.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    filters = argparse.ArgumentParser(add_help=False)
    filters.add_argument(
        "--id", action="append", metavar="ID", help="Id de la entrada. Se puede repetir."
    )
    filters.add_argument(
        "--older-than",
        type=parse_age,
        metavar="EDAD",
        help="Mensajes de más de: 90s, 30m, 12h, 7d.",
    )
    filters.add_argument(
        "--newer-than", type=parse_age, metavar="EDAD", help="Mensajes de menos de."
    )

    writes = argparse.ArgumentParser(add_help=False)
    writes.add_argument("--all", action="store_true", help="Todas las entradas, sin filtro.")
    writes.add_argument("--yes", action="store_true", help="Escribe. Sin esto es un ensayo.")
    writes.add_argument("--reason", help="Por qué. Queda en el registro. Obligatorio con --yes.")

    listing = commands.add_parser("list", parents=[filters], help="Qué hay, sin datos del mensaje.")
    listing.add_argument("--limit", type=int, default=200, help="Líneas como mucho (200).")
    commands.add_parser("discard", parents=[filters, writes], help="Borrar la entrada.")
    reinject = commands.add_parser(
        "reinject", parents=[filters, writes], help="Devolverla a su stream, sin los campos dlq_*."
    )
    reinject.add_argument(
        "--allow-stale",
        action="store_true",
        help="También con más de 24 h: contesta tarde, y abre la ventana de Meta sin estarlo.",
    )
    return parser


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    parser = _build_parser()
    args = parser.parse_args(list(argv))
    if args.command != "list":
        if not (args.all or args.id or args.older_than is not None or args.newer_than is not None):
            parser.error("di cuáles: --id, --older-than, --newer-than o --all")
        if args.yes and not (args.reason or "").strip():
            parser.error("--yes exige --reason: el motivo queda en el registro")
    return args


async def _execute(redis: Redis, args: argparse.Namespace, *, now: float | None = None) -> int:
    try:
        return await _COMMANDS[args.command](redis, args, time.time() if now is None else now)
    except Exception as exc:
        log.error("ops.dlq.failed", command=args.command, error=safe_cause(str(exc)))
        return EXIT_FAILED


async def run(redis: Redis, argv: Sequence[str], *, now: float | None = None) -> int:
    return await _execute(redis, _parse(argv), now=now)


async def _amain(args: argparse.Namespace) -> int:
    redis = get_redis()
    try:
        return await _execute(redis, args)
    finally:
        await redis.aclose()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse(sys.argv[1:] if argv is None else argv)
    configure_logging()
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    sys.exit(main())
