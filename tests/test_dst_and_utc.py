"""Cambios de hora y UTC frente a hora local.

El último domingo de marzo, en Madrid, el día tiene 23 horas (de las 02:00 se
salta a las 03:00) y el último de octubre, 25 (las 02:00 salen dos veces). En UTC
no pasa nada: ni huecos ni duplicados. La base guarda todo en UTC y solo pasa a
hora de Madrid para decir a qué día pertenece cada hora.

Los casos son días reales: el precio de OMIE de los ocho cambios de hora de 2023
a 2026 (`tests/fixtures/omie/`). Lo de ESIOS (`tests/fixtures/esios/`) tiene el
formato del archivador, pero todos los valores son inventados: los datos de ESIOS
no se publican (ver `tests/fixtures/esios/build.py`).
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import psycopg
import pytest

MADRID = ZoneInfo("Europe/Madrid")
HOUR = timedelta(hours=1)

# Los ocho cambios de hora de 2023 a 2026, con las horas que tiene ese día en Madrid
DST_DAYS = [
    (date(2023, 3, 26), 23),
    (date(2023, 10, 29), 25),
    (date(2024, 3, 31), 23),
    (date(2024, 10, 27), 25),
    (date(2025, 3, 30), 23),
    (date(2025, 10, 26), 25),  # el primero de 25 horas con el precio en cuartos
    (date(2026, 3, 29), 23),  # el primero de 23 horas con el precio en cuartos
    (date(2026, 10, 25), 25),
]
DST_IDS = [f"{d}-{h}h" for d, h in DST_DAYS]


def madrid_day_in_utc(day: date) -> tuple[datetime, datetime]:
    """Las 00:00 de Madrid de `day` y del día siguiente, en UTC.

    Se pasan a UTC antes de restarlas. Dos `datetime` con la misma `tzinfo` se restan
    como si fueran horas de reloj, sin cambio de hora: con `MADRID` en los dos, el
    25 oct 2026 daría 24 h y no 25.
    """
    start = datetime.combine(day, time(0), MADRID).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time(0), MADRID).astimezone(UTC)
    return start, end


@pytest.mark.parametrize(("day", "hours"), DST_DAYS, ids=DST_IDS)
def test_madrid_day_length_in_python(day: date, hours: int) -> None:
    start, end = madrid_day_in_utc(day)

    assert end - start == hours * HOUR


# --- calendar_day (migrations/0005) -------------------------------------------------


@pytest.mark.parametrize(("day", "hours"), DST_DAYS, ids=DST_IDS)
def test_calendar_day_hours_around_dst_change(
    db: psycopg.Connection, day: date, hours: int
) -> None:
    rows = db.execute(
        "SELECT hours FROM calendar_day WHERE day BETWEEN %s AND %s ORDER BY day",
        (day - timedelta(days=1), day + timedelta(days=1)),
    ).fetchall()

    assert [h for (h,) in rows] == [24, hours, 24]


def test_calendar_has_two_dst_changes_a_year_on_last_sundays(
    db: psycopg.Connection,
) -> None:
    rows = db.execute(
        "SELECT day, hours FROM calendar_day WHERE hours <> 24 ORDER BY day"
    ).fetchall()

    assert len(rows) == 2 * (2027 - 2014 + 1)
    for day, hours in rows:
        assert day.isoweekday() == 7, day
        assert (day + timedelta(days=7)).month != day.month, day  # el último
        assert (day.month, hours) in {(3, 23), (10, 25)}, day


# --- precio horario de OMIE en los cambios de hora (migrations/0004) --------------


@pytest.mark.usefixtures("load_omie_dst")
@pytest.mark.parametrize(("day", "hours"), DST_DAYS, ids=DST_IDS)
def test_spot_price_hourly_covers_madrid_day(
    db: psycopg.Connection, day: date, hours: int
) -> None:
    """Todas las horas del día de Madrid, seguidas en UTC, completas y de OMIE."""
    start, end = madrid_day_in_utc(day)

    rows = db.execute(
        "SELECT period_start, complete, source FROM spot_price_hourly"
        " WHERE period_start >= %s AND period_start < %s ORDER BY period_start",
        (start, end),
    ).fetchall()

    assert [r[0] for r in rows] == [start + k * HOUR for k in range(hours)]
    assert all(complete and source == "omie" for _, complete, source in rows)


@pytest.mark.usefixtures("load_omie_dst")
@pytest.mark.parametrize(("day", "hours"), DST_DAYS, ids=DST_IDS)
def test_local_hours_skip_or_repeat_two_am(
    db: psycopg.Connection, day: date, hours: int
) -> None:
    """En hora de Madrid, el de 23 horas no tiene las 02:00 y el de 25 las repite."""
    start, end = madrid_day_in_utc(day)
    expected = [0, 1] + ([2, 2] if hours == 25 else []) + list(range(3, 24))

    rows = db.execute(
        "SELECT extract(hour FROM period_start AT TIME ZONE 'Europe/Madrid')::int"
        " FROM spot_price_hourly"
        " WHERE period_start >= %s AND period_start < %s ORDER BY period_start",
        (start, end),
    ).fetchall()

    assert [h for (h,) in rows] == expected


@pytest.mark.parametrize("session_tz", ["UTC", "Europe/Madrid", "Asia/Kolkata"])
@pytest.mark.usefixtures("load_omie_dst")
def test_spot_price_hourly_ignores_session_time_zone(
    db: psycopg.Connection, session_tz: str
) -> None:
    """La vista da lo mismo sea cual sea la zona horaria de la sesión.

    Neon, el `psql` del contenedor y psycopg pueden ir cada uno en una zona. Kolkata
    va a UTC+5:30: si la vista agrupara con `date_trunc('hour', period_start)` sin
    'UTC', truncaría a las medias horas de UTC y mezclaría cuartos de dos horas.

    psycopg devuelve los `timestamptz` en la zona de la sesión. Con Madrid, las
    02:00 repetidas llegan como `datetime(2026, 10, 25, 2, tzinfo=MADRID)`, y Python
    (PEP 495) dice que una hora repetida nunca es `==` a un `datetime` de otra zona,
    aunque sea el mismo instante. Por eso se pasan a UTC antes de comparar.
    """
    start, end = madrid_day_in_utc(date(2026, 10, 25))
    db.execute("SELECT set_config('TimeZone', %s, true)", (session_tz,))

    rows = db.execute(
        "SELECT period_start, value, complete FROM spot_price_hourly"
        " WHERE period_start >= %s AND period_start < %s ORDER BY period_start",
        (start, end),
    ).fetchall()

    assert [r[0].astimezone(UTC) for r in rows] == [start + k * HOUR for k in range(25)]
    assert all(complete for _, _, complete in rows)
    # 02:00+02:00 (00:00 UTC): la media de sus cuatro cuartos,
    # (154.94 + 154.68 + 154.00 + 142.45) / 4
    assert rows[2][1] == Decimal("151.5175")


# --- ESIOS: ficheros con el formato del archivador ---------------------------------


@pytest.mark.parametrize(
    "series", ["demanda_prevista", "eolica_prevista", "solar_prevista"]
)
def test_esios_forecasts_have_25_hours_on_25_oct(
    db: psycopg.Connection, load_esios: Callable[[str, str], int], series: str
) -> None:
    load_esios(series, "2026-10-25")
    start, end = madrid_day_in_utc(date(2026, 10, 25))

    rows = db.execute(
        "SELECT period_start FROM observation"
        " WHERE period_start >= %s AND period_start < %s ORDER BY period_start",
        (start, end),
    ).fetchall()

    assert [p for (p,) in rows] == [start + k * HOUR for k in range(25)]


@pytest.mark.usefixtures("load_omie_dst")
def test_esios_and_omie_agree_quarter_by_quarter_on_25_oct(
    db: psycopg.Connection, load_esios: Callable[[str, str], int]
) -> None:
    """Las dos cargas ponen los 100 cuartos del día en los mismos instantes UTC.

    OMIE (datos reales) y ESIOS (formato de ESIOS, valores inventados) llegan con
    las horas escritas de forma distinta. Si la carga de ESIOS tomara la hora local
    en vez de `datetime_utc`, a partir de las 02:00 repetidas sus cuartos quedarían
    desplazados una hora.
    """
    load_esios("precio_spot", "2026-10-25")
    start, end = madrid_day_in_utc(date(2026, 10, 25))
    query = (
        "SELECT period_start FROM observation WHERE indicator_id = %s"
        " AND period_start >= %s AND period_start < %s ORDER BY period_start"
    )

    esios = db.execute(query, (4, start, end)).fetchall()
    omie = db.execute(query, (7, start, end)).fetchall()

    assert len(esios) == 100
    assert esios == omie


def test_spot_price_hourly_from_esios_alone_on_25_oct(
    db: psycopg.Connection, load_esios: Callable[[str, str], int]
) -> None:
    """Sin OMIE, la vista sale de los 100 cuartos de ESIOS: 25 horas completas."""
    load_esios("precio_spot", "2026-10-25")
    start, end = madrid_day_in_utc(date(2026, 10, 25))

    rows = db.execute(
        "SELECT complete, source FROM spot_price_hourly"
        " WHERE period_start >= %s AND period_start < %s",
        (start, end),
    ).fetchall()

    assert len(rows) == 25
    assert all(complete and source == "esios" for complete, source in rows)


def test_midnight_in_madrid_is_23_utc_the_day_before(
    db: psycopg.Connection, load_esios: Callable[[str, str], int]
) -> None:
    """La primera previsión del 4 nov en Madrid está guardada a las 23:00 UTC del 3.

    En la eólica sintética, el valor es 5000 más la hora del día de Madrid: 5000.0
    es la de las 00:00.
    """
    load_esios("eolica_prevista", "2026-11-04")

    rows = db.execute(
        "SELECT period_start, value FROM observation"
        " WHERE indicator_id = 2 AND period_start = %s",
        (datetime(2026, 11, 4, 0, tzinfo=MADRID),),
    ).fetchall()

    assert rows == [(datetime(2026, 11, 3, 23, tzinfo=UTC), Decimal("5000.0"))]


def test_eight_pm_in_madrid_is_seven_pm_utc(
    db: psycopg.Connection, load_esios: Callable[[str, str], int]
) -> None:
    """El precio de las 20:00 del 4 nov, la media de sus cuatro cuartos.

    En el precio sintético, cada cuarto vale 100 más su número en el día de Madrid:
    los de las 20:00 son el 80, 81, 82 y 83, y su media, 181.5.
    """
    load_esios("precio_spot", "2026-11-04")

    rows = db.execute(
        "SELECT period_start, value FROM spot_price_hourly WHERE period_start = %s",
        (datetime(2026, 11, 4, 20, tzinfo=MADRID),),
    ).fetchall()

    assert rows == [(datetime(2026, 11, 4, 19, tzinfo=UTC), Decimal("181.5"))]
