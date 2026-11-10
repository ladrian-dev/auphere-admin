#!/usr/bin/env python
"""Recalcula lo que infló INC-70. **Por defecto solo lee.**

Hasta la corrección, ``llm.input_tokens`` se valoraba por el prompt bruto, con la
caché dentro, y la caché se cobraba además en su fila. Esto corrige lo ya escrito:

- ``usage_records.cost_usd`` de las filas de entrada de una llamada con caché. Las
  demás filas ya estaban bien y no se tocan.
- ``partner_build_budget.spent_micros`` de cada mes. El tope sigue igual; si la
  partida queda por debajo, se limpian ``exhausted_at`` y ``warned_at`` con la misma
  regla que al subir el tope en ``admin/partner_money.py``.

No mueve el dinero de nadie: las bolsas y la cuenta del partner cobran por cuota
(``_turn_quota``), que nunca dependió de ``cost_usd``. Tampoco toca los contadores
de presupuesto de Redis (``nexus:budget:*``): imprime lo que sobra en cada cliente y
se decide aparte.

**Cómo sabe qué corregir, y por qué repetirlo no cambia nada.** Una fila no dice si
ya se corrigió, así que se compara su coste con las dos cuentas posibles, a la
tarifa de ``model_profiles``:

- igual a ``entrada neta x tarifa``: ya está bien, también las de después del
  arreglo;
- igual a ``prompt bruto x tarifa``: está inflada y se corrige;
- ninguna de las dos: se valoró con otra tarifa. **No se toca** y sale en el
  informe. Si se sabe cuál fue, se pasa con ``--also-rate`` y se vuelve a mirar.

Las filas con ``cost_usd`` NULL tampoco se tocan, solo se cuentan. Quien las valore
no puede copiar el ``_PRICE_EXPR`` de la 0114, que tiene este mismo fallo.

La partida se recalcula con ``min(lo gastado, suma de lo medido x 2,2)``, la misma
cuenta con la que Consumo lee los meses pasados, y nunca sube. El mes es el de
ingesta (``created_at``, UTC), que es cuando ``_record_build_line`` la sumó. Los
partners que no están en USD no se tocan: se listan, porque la partida se convirtió
a su moneda y ``_record_build_line`` le sigue sumando dólares.

Uso, con ``NEXUS_DATABASE_URL`` apuntando al entorno::

    cd apps/api
    uv run python scripts/reprice_cached_input_inc70.py
    uv run python scripts/reprice_cached_input_inc70.py --partner <uuid>
    uv run python scripts/reprice_cached_input_inc70.py --also-rate openai/gpt-5.6-sol=5.00
    uv run python scripts/reprice_cached_input_inc70.py --apply --confirm-host <host de la base>

Cada cliente y cada partner van en su propia transacción. Si se corta, se vuelve a
lanzar y sigue por donde iba.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.metering.quota import priced_input_tokens

INPUT_METER = "llm.input_tokens"
READ_METER = "llm.cache_read"
WRITE_METER = "llm.cache_write"

_MTOK = Decimal(1_000_000)
_SCALE = Decimal("0.00000001")
#: ``cost_usd`` está cuantizado a 8 decimales: una unidad es redondeo, no otra tarifa.
_TOLERANCE = _SCALE
#: Lo mismo que ``_record_build_line`` y ``usage_lines``: coste por 2,2 en cien milésimas.
_PRICE_MULTIPLIER = Decimal("2.2")
_UNITS = Decimal(100_000)
_WARN_SHARE = Decimal("0.8")

RIGHT = "ya correcta"
INFLATED = "inflada"
UNKNOWN_RATE = "otra tarifa"
NO_RATE = "modelo sin tarifa de entrada"

_RATES_SQL = sa.text("SELECT model_id, price_input_per_mtok FROM model_profiles")
_TENANTS_SQL = sa.text("SELECT id FROM tenants ORDER BY id")
_PARTNER_TENANTS_SQL = sa.text("SELECT partner_id, tenant_id FROM partner_tenants")
_POLICIES_SQL = sa.text(
    "SELECT scope_id FROM budget_policies WHERE active IS TRUE AND scope = 'tenant'"
)
_LLM_ROWS_SQL = sa.text(
    """
    SELECT id, occurred_at, created_at, meter, quantity, cost_usd, source, line, model,
           idempotency_key
      FROM usage_records
     WHERE meter LIKE 'llm.%'
    """
)
_OTHER_BUILD_SQL = sa.text(
    """
    SELECT date_trunc('month', created_at AT TIME ZONE 'UTC')::date AS month,
           coalesce(sum(cost_usd), 0) AS cost
      FROM usage_records
     WHERE meter NOT LIKE 'llm.%' AND line = 'build'
     GROUP BY 1
    """
)
_UPDATE_COST_SQL = sa.text(
    """
    UPDATE usage_records
       SET cost_usd = :new
     WHERE id = :id AND occurred_at = :occurred_at AND cost_usd = :old
    """
)
_BUDGETS_SQL = sa.text(
    """
    SELECT b.month, b.cap_micros, b.spent_micros, b.exhausted_at, b.warned_at,
           (SELECT w.currency FROM partner_wallets w WHERE w.partner_id = b.partner_id)
      FROM partner_build_budget b
     WHERE b.partner_id = :partner_id
     ORDER BY b.month
    """
)
_UPDATE_BUDGET_SQL = sa.text(
    """
    UPDATE partner_build_budget
       SET spent_micros = CAST(:new AS bigint),
           exhausted_at = CASE WHEN CAST(:new AS bigint) < cap_micros THEN NULL
                               ELSE exhausted_at END,
           warned_at = CASE WHEN CAST(:new AS bigint) < cap_micros * 0.8 THEN NULL
                            ELSE warned_at END
     WHERE partner_id = :partner_id AND month = :month AND spent_micros = :read
    """
)


@dataclass
class TenantReport:
    tenant_id: uuid.UUID
    counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    #: veredicto, modelo → filas. Lo que no se pudo corregir hay que poder buscarlo.
    untouched_by_model: dict[tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))
    unpriced_by_model: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    llm_cost_before: Decimal = Decimal(0)
    excess_by_source: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    #: Por mes de ingesta: lo medido en la partida, ya corregido.
    build_cost_by_month: dict[date, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    #: Exceso del canal por mes y día de ``occurred_at``: lo que sobra en Redis.
    channel_excess_by_month: dict[date, Decimal] = field(
        default_factory=lambda: defaultdict(Decimal)
    )
    channel_excess_by_day: dict[date, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    updated: int = 0
    changed_meanwhile: int = 0

    @property
    def excess(self) -> Decimal:
        return sum(self.excess_by_source.values(), Decimal(0))


@dataclass(frozen=True)
class BudgetChange:
    partner_id: uuid.UUID
    month: date
    currency: str
    cap: int
    spent: int
    measured: int
    new_spent: int
    was_exhausted: bool
    written: bool | None = None

    @property
    def unblocks(self) -> bool:
        return self.was_exhausted and self.new_spent < self.cap


@dataclass
class Report:
    tenants: list[TenantReport] = field(default_factory=list)
    budgets: list[BudgetChange] = field(default_factory=list)
    skipped_budgets: list[BudgetChange] = field(default_factory=list)
    tenants_with_policy: set[uuid.UUID] = field(default_factory=set)


def _call_key(idempotency_key: str, meter: str) -> str:
    """``{turno}:{seq}:{medidor}`` → ``{turno}:{seq}``, como ``consumer._llm_call_key``."""
    suffix = f":{meter}"
    return idempotency_key[: -len(suffix)] if idempotency_key.endswith(suffix) else idempotency_key


def split_calls(rows: Iterable[Mapping[str, Any]]) -> Iterator[dict[str, Mapping[str, Any]]]:
    """Las filas de un cliente, por llamada: ``{medidor: fila}``.

    Un trabajo reintentado repite ``turn_id`` y ``call_seq`` con otro ``occurred_at``,
    y la clave de idempotencia lo admite. Por eso un medidor repetido abre otra
    llamada: el colector emite cada llamada de una vez, sin repetir medidor.
    """
    by_key: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_key[_call_key(row["idempotency_key"], row["meter"])].append(row)
    for group in by_key.values():
        call: dict[str, Mapping[str, Any]] = {}
        for row in sorted(group, key=lambda r: r["occurred_at"]):
            if row["meter"] in call:
                yield call
                call = {}
            call[row["meter"]] = row
        yield call


def _close(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= _TOLERANCE


def reprice(
    cost: Decimal, quantity: Decimal, net: int, rates: Sequence[Decimal]
) -> tuple[str, Decimal | None]:
    """Veredicto de una fila de entrada y su coste correcto, si hay que corregirla."""
    if not rates:
        return NO_RATE, None
    if any(_close(cost, net * rate / _MTOK) for rate in rates):
        return RIGHT, None
    for rate in rates:
        if _close(cost, quantity * rate / _MTOK):
            return INFLATED, (net * rate / _MTOK).quantize(_SCALE)
    return UNKNOWN_RATE, None


def _month(moment: datetime) -> date:
    return moment.date().replace(day=1)


def scan_rows(
    tenant_id: uuid.UUID,
    rows: Iterable[Mapping[str, Any]],
    rates: Mapping[str, Sequence[Decimal]],
) -> tuple[TenantReport, list[dict[str, Any]]]:
    """El informe de un cliente y las filas que hay que corregir. No escribe."""
    report = TenantReport(tenant_id)
    fixes: list[dict[str, Any]] = []
    for call in split_calls(rows):
        cache_read = int(call[READ_METER]["quantity"]) if READ_METER in call else 0
        cache_write = int(call[WRITE_METER]["quantity"]) if WRITE_METER in call else 0
        for meter, row in call.items():
            cost = row["cost_usd"]
            if cost is None:
                report.unpriced_by_model[str(row["model"])] += 1
                continue
            report.llm_cost_before += cost
            new_cost = cost
            if meter == INPUT_METER and (cache_read or cache_write):
                net = priced_input_tokens(int(row["quantity"]), cache_read, cache_write)
                verdict, fixed = reprice(
                    cost, row["quantity"], net, rates.get(str(row["model"]), ())
                )
                report.counts[verdict] += 1
                if verdict in (UNKNOWN_RATE, NO_RATE):
                    report.untouched_by_model[(verdict, str(row["model"]))] += 1
                if fixed is not None:
                    new_cost = fixed
                    excess = cost - fixed
                    report.excess_by_source[str(row["source"])] += excess
                    if row["source"] == "channel":
                        report.channel_excess_by_month[_month(row["occurred_at"])] += excess
                        report.channel_excess_by_day[row["occurred_at"].date()] += excess
                    fixes.append(
                        {
                            "id": row["id"],
                            "occurred_at": row["occurred_at"],
                            "old": cost,
                            "new": fixed,
                        }
                    )
            if row["line"] == "build":
                report.build_cost_by_month[_month(row["created_at"])] += new_cost
    return report, fixes


def budget_change(
    partner_id: uuid.UUID,
    month: date,
    *,
    cap: int,
    spent: int,
    currency: str,
    measured_cost: Decimal,
    was_exhausted: bool,
) -> BudgetChange:
    measured = int(measured_cost * _PRICE_MULTIPLIER * _UNITS)
    return BudgetChange(
        partner_id=partner_id,
        month=month,
        currency=currency,
        cap=cap,
        spent=spent,
        measured=measured,
        new_spent=min(spent, measured),
        was_exhausted=was_exhausted,
    )


async def _input_rates(also: Mapping[str, Sequence[Decimal]]) -> dict[str, list[Decimal]]:
    async with get_sessionmaker()() as session:
        rows = (await session.execute(_RATES_SQL)).all()
    rates: dict[str, list[Decimal]] = defaultdict(list)
    for model, rate in rows:
        if rate is not None:
            rates[str(model)].append(Decimal(rate))
    for model, extra in also.items():
        rates[model].extend(extra)
    return rates


async def _scope(
    partner: uuid.UUID | None,
) -> tuple[list[uuid.UUID], dict[uuid.UUID, list[uuid.UUID]]]:
    """Los clientes a recorrer y los de cada partner. La partida se calcula siempre
    con **todos** los clientes del partner: con menos, el ``min`` la dejaría corta."""
    async with get_sessionmaker()() as session:
        pairs = (await session.execute(_PARTNER_TENANTS_SQL)).all()
        tenants = [uuid.UUID(str(t)) for (t,) in (await session.execute(_TENANTS_SQL)).all()]
    by_partner: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for partner_id, tenant_id in pairs:
        by_partner[uuid.UUID(str(partner_id))].append(uuid.UUID(str(tenant_id)))
    if partner is None:
        return tenants, dict(by_partner)
    return by_partner.get(partner, []), {partner: by_partner.get(partner, [])}


async def _process_tenant(
    tenant_id: uuid.UUID, rates: Mapping[str, Sequence[Decimal]], *, apply: bool
) -> TenantReport:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        rows = (await session.execute(_LLM_ROWS_SQL)).mappings().all()
        report, fixes = scan_rows(tenant_id, rows, rates)
        for month, cost in (await session.execute(_OTHER_BUILD_SQL)).all():
            report.build_cost_by_month[month] += Decimal(cost)
        if apply:
            for fix in fixes:
                result = await session.execute(_UPDATE_COST_SQL, fix)
                if result.rowcount:
                    report.updated += 1
                else:
                    report.changed_meanwhile += 1
    return report


async def _process_partner(
    partner_id: uuid.UUID, tenants: Iterable[TenantReport], *, apply: bool
) -> tuple[list[BudgetChange], list[BudgetChange]]:
    measured: dict[date, Decimal] = defaultdict(Decimal)
    for tenant in tenants:
        for month, cost in tenant.build_cost_by_month.items():
            measured[month] += cost
    changes: list[BudgetChange] = []
    skipped: list[BudgetChange] = []
    async with get_sessionmaker()() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        rows = (await session.execute(_BUDGETS_SQL, {"partner_id": str(partner_id)})).all()
        for month, cap, spent, exhausted_at, _warned_at, currency in rows:
            change = budget_change(
                partner_id,
                month,
                cap=int(cap),
                spent=int(spent),
                currency=str(currency or "USD"),
                measured_cost=measured.get(month, Decimal(0)),
                was_exhausted=exhausted_at is not None,
            )
            if change.currency != "USD":
                skipped.append(change)
                continue
            if change.new_spent == change.spent:
                continue
            written = None
            if apply:
                result = await session.execute(
                    _UPDATE_BUDGET_SQL,
                    {
                        "new": change.new_spent,
                        "partner_id": str(partner_id),
                        "month": month,
                        "read": change.spent,
                    },
                )
                written = bool(result.rowcount)
            changes.append(replace(change, written=written))
    return changes, skipped


async def run(
    *,
    apply: bool = False,
    partner: uuid.UUID | None = None,
    also_rates: Mapping[str, Sequence[Decimal]] | None = None,
) -> Report:
    rates = await _input_rates(also_rates or {})
    tenant_ids, by_partner = await _scope(partner)
    report = Report()
    by_tenant: dict[uuid.UUID, TenantReport] = {}
    for tenant_id in tenant_ids:
        by_tenant[tenant_id] = await _process_tenant(tenant_id, rates, apply=apply)
    report.tenants = list(by_tenant.values())
    for partner_id, tenants in sorted(by_partner.items(), key=lambda kv: str(kv[0])):
        changes, skipped = await _process_partner(
            partner_id, (by_tenant[t] for t in tenants if t in by_tenant), apply=apply
        )
        report.budgets += changes
        report.skipped_budgets += skipped
    async with get_sessionmaker()() as session:
        policies = (await session.execute(_POLICIES_SQL)).all()
    report.tenants_with_policy = {
        uuid.UUID(str(s)) for (s,) in policies if uuid.UUID(str(s)) in by_tenant
    }
    return report


def _usd(amount: Decimal) -> str:
    return f"{amount:.4f}"


def _micros(amount: int) -> str:
    return f"{Decimal(amount) / _UNITS:.2f}"


def print_report(report: Report, *, apply: bool) -> None:
    before = sum((t.llm_cost_before for t in report.tenants), Decimal(0))
    excess = sum((t.excess for t in report.tenants), Decimal(0))
    counts: dict[str, int] = defaultdict(int)
    by_source: dict[str, Decimal] = defaultdict(Decimal)
    untouched: dict[tuple[str, str], int] = defaultdict(int)
    unpriced: dict[str, int] = defaultdict(int)
    for tenant in report.tenants:
        for verdict, count in tenant.counts.items():
            counts[verdict] += count
        for source, amount in tenant.excess_by_source.items():
            by_source[source] += amount
        for key, count in tenant.untouched_by_model.items():
            untouched[key] += count
        for model, count in tenant.unpriced_by_model.items():
            unpriced[model] += count

    print(f"\nFilas de entrada en una llamada con caché: {dict(counts)}")
    after = before - excess
    ratio = f"{before / after:.2f}" if after > 0 else "sin datos"
    print(f"Coste LLM: {_usd(before)} USD → {_usd(after)} USD (x{ratio} sobre lo correcto)")
    print(f"Exceso por origen: { {s: _usd(a) for s, a in sorted(by_source.items())} }")

    if any(t.excess for t in report.tenants):
        print("\nClientes con exceso (tenant, USD de más, escritas, cambiadas entretanto):")
        for tenant in sorted(report.tenants, key=lambda t: t.excess, reverse=True):
            if tenant.excess:
                print(
                    f"  {tenant.tenant_id}  {_usd(tenant.excess)}  "
                    f"{tenant.updated}  {tenant.changed_meanwhile}"
                )

    if untouched:
        print("\nNO se tocan (otra tarifa o modelo sin tarifa: ver --also-rate):")
        for (verdict, model), count in sorted(untouched.items()):
            print(f"  {verdict}  {model}: {count}")
    if unpriced:
        print(f"\nFilas LLM con cost_usd NULL, sin tocar: {dict(unpriced)}")

    print("\nPartida «Construcción y pruebas» (USD):")
    if not report.budgets:
        print("  nada que cambiar")
    for change in report.budgets:
        state = "se desbloquea" if change.unblocks else ""
        written = "" if change.written is None else ("escrita" if change.written else "CAMBIÓ")
        print(
            f"  {change.partner_id} {change.month:%Y-%m}  tope {_micros(change.cap)}  "
            f"{_micros(change.spent)} → {_micros(change.new_spent)}  {state} {written}"
        )
    for change in report.skipped_budgets:
        print(
            f"  SIN TOCAR {change.partner_id} {change.month:%Y-%m} en {change.currency}: "
            f"gastado {_micros(change.spent)}, medido {_micros(change.measured)} USD"
        )

    print("\nContadores de Redis, sin tocar (exceso del canal por mes; * = política activa):")
    channel = [t for t in report.tenants if t.channel_excess_by_month]
    if not channel:
        print("  nada")
    for tenant in channel:
        mark = "*" if tenant.tenant_id in report.tenants_with_policy else " "
        months = {f"{m:%Y-%m}": _usd(a) for m, a in sorted(tenant.channel_excess_by_month.items())}
        print(f"  {mark} {tenant.tenant_id}  {months}")

    print("\nESCRITO." if apply else "\nSolo lectura: no se ha escrito nada.")


def _parse_rate(raw: str) -> tuple[str, Decimal]:
    model, _, rate = raw.partition("=")
    if not model or not rate:
        raise argparse.ArgumentTypeError(f"se esperaba modelo=tarifa, no {raw!r}")
    return model, Decimal(rate)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recalcula lo que infló INC-70. Sin --apply, solo lee."
    )
    parser.add_argument("--apply", action="store_true", help="Escribe. Exige --confirm-host.")
    parser.add_argument("--confirm-host", help="El host de la base, para no escribir en otra.")
    parser.add_argument("--partner", type=uuid.UUID, help="Solo este partner y sus clientes.")
    parser.add_argument(
        "--also-rate",
        type=_parse_rate,
        action="append",
        default=[],
        metavar="MODELO=USD_POR_MTOK",
        help="Otra tarifa de entrada que tuvo el modelo. Se puede repetir.",
    )
    args = parser.parse_args()

    async with get_sessionmaker()() as session:
        url = (await session.connection()).engine.url
    print(f"Base: {url.host} / {url.database}  ·  {'ESCRITURA' if args.apply else 'solo lectura'}")
    if args.apply and args.confirm_host != url.host:
        parser.error(f"--apply exige --confirm-host {url.host}")

    also: dict[str, list[Decimal]] = defaultdict(list)
    for model, rate in args.also_rate:
        also[model].append(rate)
    report = await run(apply=args.apply, partner=args.partner, also_rates=also)
    print_report(report, apply=args.apply)


if __name__ == "__main__":
    asyncio.run(main())
