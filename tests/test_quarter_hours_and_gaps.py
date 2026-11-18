"""La frontera de 15 minutos, los huecos y los días incompletos.

El mercado diario pasó a periodos de 15 minutos el 1 oct 2025 (primer día de
entrega; la subasta fue el 30 sep). Antes, 24 precios por día; después, 96 cuartos
que `spot_price_hourly` junta en 24 horas haciendo la media de cada cuatro. Los
casos de la frontera son el precio real de OMIE del 30 sep y del 1 oct 2025
(`tests/fixtures/omie/frontera_15_min.csv`).

Regla 5 del proyecto: un día incompleto no se publica; si faltan horas reales, se
marca el hueco en vez de rellenarlo. `spot_price_hourly` marca la hora a la que le
falta algún cuarto (`complete = false`) y no se inventa la que no tiene ninguno.
`spot_price_day` (migrations/0007) lo sube al día de Madrid. Los días con huecos se
fabrican borrando filas de un fixture, dentro de la transacción del test.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import psycopg
import pytest
from test_dst_and_utc import DST_DAYS, DST_IDS, madrid_day_in_utc

MADRID = ZoneInfo("Europe/Madrid")
HOUR = timedelta(hours=1)
QUARTER = timedelta(minutes=15)

OMIE_1H, OMIE_15M = 6, 7  # migrations/0004
ESIOS_15M = 4  # migrations/0002

LAST_HOURLY_DAY = date(2025, 9, 30)
FIRST_QUARTER_DAY = date(2025, 10, 1)


@pytest.fixture
def frontier(load_omie: Callable[[str], None]) -> None:
    load_omie("frontera_15_min")


def delete_quarters(db: psycopg.Connection, indicator: int, *starts: datetime) -> None:
    """Borra los cuartos que empiezan en `starts`; falla si alguno no estaba."""
    cur = db.execute(
        "DELETE FROM observation WHERE indicator_id = %s AND period_start = ANY(%s)",
        (indicator, list(starts)),
    )
    assert cur.rowcount == len(starts)


def quarters_of_hour(hour: datetime) -> list[datetime]:
    return [hour + k * QUARTER for k in range(4)]


def spot_price_day(db: psycopg.Connection, day: date) -> tuple[int, int, int, bool]:
    row = db.execute(
        "SELECT hours, hours_present, hours_complete, complete"
        " FROM spot_price_day WHERE day = %s",
        (day,),
    ).fetchone()
    assert row is not None
    return row


# --- la frontera de 15 minutos -----------------------------------------------------


@pytest.mark.usefixtures("frontier")
@pytest.mark.parametrize(
    ("day", "indicator", "count"),
    [
        (LAST_HOURLY_DAY, OMIE_1H, 24),
        (LAST_HOURLY_DAY, OMIE_15M, 0),
        (FIRST_QUARTER_DAY, OMIE_1H, 0),
        (FIRST_QUARTER_DAY, OMIE_15M, 96),
    ],
    ids=["30-sep-horario", "30-sep-cuartos", "1-oct-horario", "1-oct-cuartos"],
)
def test_omie_switches_from_24_hours_to_96_quarters_on_1_oct_2025(
    db: psycopg.Connection, day: date, indicator: int, count: int
) -> None:
    start, end = madrid_day_in_utc(day)

    (n,) = db.execute(
        "SELECT count(*) FROM observation WHERE indicator_id = %s"
        " AND period_start >= %s AND period_start < %s",
        (indicator, start, end),
    ).fetchone()

    assert n == count


@pytest.mark.usefixtures("frontier")
@pytest.mark.parametrize(
    ("day", "resolution"),
    [(LAST_HOURLY_DAY, timedelta(hours=1)), (FIRST_QUARTER_DAY, QUARTER)],
    ids=["30-sep", "1-oct"],
)
def test_spot_price_hourly_has_24_complete_hours_either_side(
    db: psycopg.Connection, day: date, resolution: timedelta
) -> None:
    start, end = madrid_day_in_utc(day)

    rows = db.execute(
        "SELECT period_start, source_resolution, complete, source"
        " FROM spot_price_hourly"
        " WHERE period_start >= %s AND period_start < %s ORDER BY period_start",
        (start, end),
    ).fetchall()

    assert [r[0] for r in rows] == [start + k * HOUR for k in range(24)]
    assert all(r[1:] == (resolution, True, "omie") for r in rows)


@pytest.mark.usefixtures("frontier")
def test_quarter_hour_prices_average_to_the_hour(db: psycopg.Connection) -> None:
    """Cada hora del 1 oct es la media exacta de sus cuatro cuartos de OMIE."""
    start, end = madrid_day_in_utc(FIRST_QUARTER_DAY)
    quarters = db.execute(
        "SELECT period_start, value FROM observation WHERE indicator_id = %s"
        " AND period_start >= %s AND period_start < %s ORDER BY period_start",
        (OMIE_15M, start, end),
    ).fetchall()
    expected = [
        (start + k * HOUR, sum(v for _, v in quarters[4 * k : 4 * k + 4]) / 4)
        for k in range(24)
    ]

    rows = db.execute(
        "SELECT period_start, value FROM spot_price_hourly"
        " WHERE period_start >= %s AND period_start < %s ORDER BY period_start",
        (start, end),
    ).fetchall()

    assert rows == expected
    # las 00:00 de Madrid: (105.1 + 104.24 + 102.28 + 102) / 4
    assert rows[0][1] == Decimal("103.405")


@pytest.mark.usefixtures("frontier")
def test_hourly_prices_before_the_frontier_pass_through(
    db: psycopg.Connection,
) -> None:
    """El 30 sep, la vista da el precio horario de OMIE tal cual, sin promediar."""
    start, end = madrid_day_in_utc(LAST_HOURLY_DAY)

    hourly = db.execute(
        "SELECT period_start, value FROM observation WHERE indicator_id = %s"
        " AND period_start >= %s AND period_start < %s ORDER BY period_start",
        (OMIE_1H, start, end),
    ).fetchall()
    view = db.execute(
        "SELECT period_start, value FROM spot_price_hourly"
        " WHERE period_start >= %s AND period_start < %s ORDER BY period_start",
        (start, end),
    ).fetchall()

    assert view == hourly
    assert view[0] == (datetime(2025, 9, 29, 22, tzinfo=UTC), Decimal("95.46"))


@pytest.mark.usefixtures("frontier")
def test_frontier_days_are_complete(db: psycopg.Connection) -> None:
    assert spot_price_day(db, LAST_HOURLY_DAY) == (24, 24, 24, True)
    assert spot_price_day(db, FIRST_QUARTER_DAY) == (24, 24, 24, True)


# --- huecos dentro de una hora -----------------------------------------------------

# El 4 nov 2026 de ESIOS (sintético): cada cuarto vale 100 más su número en el día de
# Madrid. Las 20:00 de Madrid (19:00 UTC) son los cuartos 80 a 83: 180, 181, 182, 183.
NOV_4 = date(2026, 11, 4)
EIGHT_PM = datetime(2026, 11, 4, 19, tzinfo=UTC)


def test_hour_missing_a_quarter_is_marked_incomplete(
    db: psycopg.Connection, load_esios: Callable[[str, str], int]
) -> None:
    """Le falta el último cuarto: sale la media de los tres que hay, marcada."""
    load_esios("precio_spot", "2026-11-04")
    delete_quarters(db, ESIOS_15M, EIGHT_PM + 3 * QUARTER)

    rows = db.execute(
        "SELECT value, complete FROM spot_price_hourly WHERE period_start = %s",
        (EIGHT_PM,),
    ).fetchall()

    assert rows == [(Decimal("181"), False)]  # (180 + 181 + 182) / 3


def test_hour_with_no_quarters_is_left_out_not_filled(
    db: psycopg.Connection, load_esios: Callable[[str, str], int]
) -> None:
    """Sin ningún cuarto, la hora no sale: ni un cero, ni la de al lado ni una media."""
    load_esios("precio_spot", "2026-11-04")
    delete_quarters(db, ESIOS_15M, *quarters_of_hour(EIGHT_PM))
    start, end = madrid_day_in_utc(NOV_4)

    rows = db.execute(
        "SELECT period_start, complete FROM spot_price_hourly"
        " WHERE period_start >= %s AND period_start < %s ORDER BY period_start",
        (start, end),
    ).fetchall()

    hours = [start + k * HOUR for k in range(24)]
    hours.remove(EIGHT_PM)
    assert [p for p, _ in rows] == hours
    assert all(complete for _, complete in rows)


# --- regla 5: el día entero (migrations/0007) --------------------------------------

# Qué se borra del 4 nov y cómo queda el día: (horas, con precio, completas, completo)
GAPS = [
    ([], (24, 24, 24, True)),
    ([EIGHT_PM + 3 * QUARTER], (24, 24, 23, False)),
    (quarters_of_hour(EIGHT_PM), (24, 23, 23, False)),
    (
        [EIGHT_PM + QUARTER, *quarters_of_hour(EIGHT_PM + 2 * HOUR)],
        (24, 23, 22, False),
    ),
    (
        [madrid_day_in_utc(NOV_4)[0]],  # el primer cuarto del día: las 00:00
        (24, 24, 23, False),
    ),
    (
        [madrid_day_in_utc(NOV_4)[1] - QUARTER],  # el último: las 23:45
        (24, 24, 23, False),
    ),
]
GAP_IDS = [
    "sin-huecos",
    "un-cuarto",
    "una-hora",
    "un-cuarto-y-una-hora",
    "primer-cuarto",
    "ultimo-cuarto",
]


@pytest.mark.parametrize(("deleted", "expected"), GAPS, ids=GAP_IDS)
def test_day_with_any_gap_is_incomplete(
    db: psycopg.Connection,
    load_esios: Callable[[str, str], int],
    deleted: list[datetime],
    expected: tuple[int, int, int, bool],
) -> None:
    load_esios("precio_spot", "2026-11-04")
    if deleted:
        delete_quarters(db, ESIOS_15M, *deleted)

    assert spot_price_day(db, NOV_4) == expected


def test_day_without_any_price_is_incomplete(db: psycopg.Connection) -> None:
    """Un día sin precio sale igual, con cero horas: el hueco se ve, no desaparece."""
    assert spot_price_day(db, NOV_4) == (24, 0, 0, False)


def test_gap_does_not_spill_into_neighbouring_days(
    db: psycopg.Connection, load_esios: Callable[[str, str], int]
) -> None:
    """Las 00:00 de Madrid son las 23:00 UTC del día anterior: el hueco es del 4 nov."""
    load_esios("precio_spot", "2026-11-04")
    delete_quarters(db, ESIOS_15M, madrid_day_in_utc(NOV_4)[0])

    rows = db.execute(
        "SELECT day, hours_present, complete FROM spot_price_day"
        " WHERE day BETWEEN %s AND %s ORDER BY day",
        (NOV_4 - timedelta(days=1), NOV_4 + timedelta(days=1)),
    ).fetchall()

    assert rows == [
        (NOV_4 - timedelta(days=1), 0, False),
        (NOV_4, 24, False),
        (NOV_4 + timedelta(days=1), 0, False),
    ]


# --- regla 5 en los cambios de hora --------------------------------------------------


@pytest.mark.usefixtures("load_omie_dst")
@pytest.mark.parametrize(("day", "hours"), DST_DAYS, ids=DST_IDS)
def test_dst_days_are_complete_with_23_or_25_hours(
    db: psycopg.Connection, day: date, hours: int
) -> None:
    assert spot_price_day(db, day) == (hours, hours, hours, True)


@pytest.mark.usefixtures("load_omie_dst")
def test_25_hour_day_with_24_hours_is_incomplete(db: psycopg.Connection) -> None:
    """El fallo clásico: un 25 oct con 24 horas parece un día normal, y no lo es.

    Se borran las 02:00+01:00, la segunda vez que salen las 02:00 (01:00 UTC).
    """
    second_two_am = datetime(2026, 10, 25, 1, tzinfo=UTC)
    assert second_two_am.astimezone(MADRID).fold == 1
    delete_quarters(db, OMIE_15M, *quarters_of_hour(second_two_am))

    assert spot_price_day(db, date(2026, 10, 25)) == (25, 24, 24, False)


@pytest.mark.usefixtures("load_omie_dst")
def test_esios_covers_an_omie_gap_with_the_whole_hour(
    db: psycopg.Connection, load_esios: Callable[[str, str], int]
) -> None:
    """Si a OMIE le falta un cuarto y ESIOS tiene la hora entera, sale la de ESIOS.

    No es rellenar: es el mismo precio, publicado por otra fuente (migrations/0004).
    """
    load_esios("precio_spot", "2026-10-25")
    hour = datetime(2026, 10, 25, 12, tzinfo=UTC)
    delete_quarters(db, OMIE_15M, hour + 2 * QUARTER)

    rows = db.execute(
        "SELECT source, complete FROM spot_price_hourly WHERE period_start = %s",
        (hour,),
    ).fetchall()

    assert rows == [("esios", True)]
    assert spot_price_day(db, date(2026, 10, 25)) == (25, 25, 25, True)
