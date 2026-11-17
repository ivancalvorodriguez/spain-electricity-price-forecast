"""Genera los ficheros de ESIOS de los tests: sintéticos, con el formato del archivador.

Lo que guarda el archivador (el repo privado `archivador_luz`) no se publica: el
token de ESIOS es de uso personal y REE no ha confirmado las condiciones de
reutilización. Estos ficheros tienen la misma estructura que los archivados
(`<serie>/<día>.json.gz`, con `indicador`, `dia`, `publicado_en` y `valores` con los
campos de ESIOS), pero todos los valores son inventados: dicen qué periodo del día
de Madrid son, contando desde 0 a las 00:00.

- `demanda_prevista`, `eolica_prevista` y `solar_prevista`: horarios, base de la
  serie (20000, 5000 y 1000) + `n`, con `n` de 0 a 23 (a 24 el 25 oct).
- `precio_spot`: cuartos de hora, 100 + `n`, con `n` de 0 a 95 (a 99 el 25 oct).
  La media de una hora `h` es 100 + 4h + 1.5: las 20:00, 181.5.

`publicado_en`, como lo archivaría el bot: las previsiones a las 11:10 de Madrid del
día anterior y el precio a las 17:29. No lee ningún fichero ni la red, y sale igual
byte a byte cada vez (gzip sin fecha). Desde la raíz del repo:

    python tests/fixtures/esios/build.py
"""

import gzip
import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).parent
MADRID = ZoneInfo("Europe/Madrid")
DAYS = [date(2026, 10, 25), date(2026, 11, 4)]
HOUR = timedelta(hours=1)
QUARTER = timedelta(minutes=15)
# serie -> (indicador de ESIOS, base del valor inventado)
FORECASTS = {
    "demanda_prevista": (1775, 20000),
    "eolica_prevista": (1777, 5000),
    "solar_prevista": (1779, 1000),
}
PRICE = (600, 100)
PENINSULA = {"geo_id": 8741, "geo_name": "Península"}
SPAIN = {"geo_id": 3, "geo_name": "España"}


def madrid(day: date, hour: int = 0, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), MADRID)


def esios_value(value: float, start: datetime, geo: dict[str, object]) -> dict:
    """Un elemento de `valores`, con los mismos campos que devuelve ESIOS."""
    utc = start.astimezone(UTC)
    return {
        "value": value,
        "datetime": start.astimezone(MADRID).isoformat(timespec="milliseconds"),
        "datetime_utc": utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tz_time": utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        **geo,
    }


def series_values(
    start: datetime, end: datetime, step: timedelta, base: int, geo: dict[str, object]
) -> list[dict]:
    """Un valor por periodo de `start` a `end` (en UTC), base + número de periodo."""
    periods = int((end - start) / step)
    return [esios_value(float(base + n), start + n * step, geo) for n in range(periods)]


def write(
    series: str, indicator: int, day: date, published: datetime, values: list
) -> None:
    doc = {
        "indicador": indicator,
        "dia": day.isoformat(),
        "publicado_en": published.astimezone(UTC).isoformat(timespec="seconds"),
        "valores": values,
    }
    path = HERE / series / f"{day.isoformat()}.json.gz"
    path.parent.mkdir(exist_ok=True)
    data = json.dumps(doc, ensure_ascii=False).encode("utf-8")
    path.write_bytes(gzip.compress(data, mtime=0))
    print(f"{path.relative_to(HERE)}: {len(values)} valores")


def main() -> None:
    for day in DAYS:
        # En UTC, para que el 25 oct salgan 25 horas y no 24
        start = madrid(day).astimezone(UTC)
        end = madrid(day + timedelta(days=1)).astimezone(UTC)
        day_before = day - timedelta(days=1)

        for series, (indicator, base) in FORECASTS.items():
            values = series_values(start, end, HOUR, base, PENINSULA)
            write(series, indicator, day, madrid(day_before, 11, 10), values)

        indicator, base = PRICE
        values = series_values(start, end, QUARTER, base, SPAIN)
        write("precio_spot", indicator, day, madrid(day_before, 17, 29), values)


if __name__ == "__main__":
    main()
