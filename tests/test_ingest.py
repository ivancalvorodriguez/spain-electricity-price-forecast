"""La carga del archivador en `observation`: `epf_spain.ingest` y `epf-ingest`.

Solo con los ficheros sintéticos de `tests/fixtures/esios/`: nada de ESIOS real en
el repo, que es público. Los ficheros rotos se fabrican en `tmp_path` a partir de
ellos.
"""

import gzip
import json
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest

from epf_spain import ingest
from epf_spain.ingest import IngestError, load_file, main

ESIOS = Path(__file__).parent / "fixtures" / "esios"
NOV_4 = "2026-11-04"
# serie -> (indicator.id, valores del 4 nov)
SERIES = {
    "demanda_prevista": (1, 24),
    "eolica_prevista": (2, 24),
    "solar_prevista": (3, 24),
    "precio_spot": (4, 96),
}


def fixture(series: str, day: str = NOV_4) -> Path:
    return ESIOS / series / f"{day}.json.gz"


def read_json(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f, parse_float=Decimal)


def broken_copy(
    tmp_path: Path, series: str, change: Callable[[dict], None], name: str = "roto"
) -> Path:
    """Copia el fichero del 4 nov de `series` en `tmp_path`, cambiado por `change`."""
    data = read_json(fixture(series))
    change(data)
    path = tmp_path / series / f"{name}.json.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps(data, default=str).encode("utf-8")))
    return path


def observation_rows(conn: psycopg.Connection) -> set[tuple]:
    return set(
        conn.execute(
            "SELECT indicator_id, period_start, published_at, value FROM observation"
        ).fetchall()
    )


def count(conn: psycopg.Connection) -> int:
    return conn.execute("SELECT count(*) FROM observation").fetchone()[0]


@pytest.mark.parametrize("series", SERIES)
def test_4_nov_loads_one_row_per_value(db: psycopg.Connection, series: str) -> None:
    indicator, values = SERIES[series]
    assert load_file(db, fixture(series)) == (values, values)
    rows = db.execute(
        "SELECT indicator_id, count(*), min(published_at), max(published_at)"
        " FROM observation GROUP BY indicator_id"
    ).fetchall()
    published = datetime.fromisoformat(read_json(fixture(series))["publicado_en"])
    assert rows == [(indicator, values, published, published)]


def test_values_are_exact_decimals_in_utc(db: psycopg.Connection) -> None:
    load_file(db, fixture("eolica_prevista"))
    # 00:00 del 4 nov en Madrid = 23:00 UTC del 3; el fichero dice 5000.0
    value = db.execute(
        "SELECT value FROM observation"
        " WHERE indicator_id = 2 AND period_start = '2026-11-03T23:00:00Z'"
    ).fetchone()[0]
    assert value == Decimal("5000.0")
    assert isinstance(value, Decimal)


def test_loading_twice_adds_nothing(db: psycopg.Connection) -> None:
    assert load_file(db, fixture("precio_spot")) == (96, 96)
    assert load_file(db, fixture("precio_spot")) == (0, 96)
    assert count(db) == 96


def test_later_download_is_a_new_version(
    db: psycopg.Connection, tmp_path: Path
) -> None:
    def republish(data: dict) -> None:
        data["publicado_en"] = "2026-11-03T10:35:00+00:00"  # el repaso de las 11:35

    load_file(db, fixture("eolica_prevista"))
    assert load_file(db, broken_copy(tmp_path, "eolica_prevista", republish)) == (
        24,
        24,
    )
    assert count(db) == 48


def test_unknown_indicator_fails_and_loads_nothing(
    db: psycopg.Connection, tmp_path: Path
) -> None:
    def unknown(data: dict) -> None:
        data["indicador"] = 9999

    with pytest.raises(IngestError, match="desconocido: 9999"):
        load_file(db, broken_copy(tmp_path, "precio_spot", unknown))
    assert count(db) == 0


def test_bad_value_halfway_leaves_nothing_from_that_file(
    db: psycopg.Connection, tmp_path: Path
) -> None:
    def null_at_50(data: dict) -> None:
        data["valores"][50]["value"] = None

    load_file(db, fixture("eolica_prevista"))
    # las 50 primeras filas sí entran en la base antes de que falle la 51
    with pytest.raises(psycopg.errors.NotNullViolation):
        load_file(db, broken_copy(tmp_path, "precio_spot", null_at_50))
    # solo se deshace ese fichero, no lo cargado antes
    assert count(db) == 24


def test_time_without_offset_is_rejected(
    db: psycopg.Connection, tmp_path: Path
) -> None:
    def local_time(data: dict) -> None:
        # sin la Z, Postgres la leería en la zona horaria de la sesión
        data["valores"][0]["datetime_utc"] = "2026-11-03T23:00:00"

    with pytest.raises(IngestError, match="sin zona horaria"):
        load_file(db, broken_copy(tmp_path, "eolica_prevista", local_time))
    assert count(db) == 0


def test_not_an_archived_file_is_an_ingest_error(
    db: psycopg.Connection, tmp_path: Path
) -> None:
    path = tmp_path / "no_es.json.gz"
    path.write_bytes(b"esto no es gzip")
    with pytest.raises(IngestError, match="formato del archivador"):
        load_file(db, path)


def test_command_loads_what_the_files_say(
    committed_db_url: str,
    connection: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Toda la carpeta de fixtures, comparada con los JSON leídos aquí aparte."""
    monkeypatch.setenv("DATABASE_URL", committed_db_url)
    assert main([str(ESIOS)]) == 0

    ids = {1775: 1, 1777: 2, 1779: 3, 600: 4}
    expected = set()
    for path in ESIOS.rglob("*.json.gz"):
        data = read_json(path)
        published = datetime.fromisoformat(data["publicado_en"])
        expected |= {
            (
                ids[data["indicador"]],
                datetime.fromisoformat(v["datetime_utc"]),
                published,
                v["value"],
            )
            for v in data["valores"]
        }
    # 25 oct: 3 × 25 + 100; 4 nov: 3 × 24 + 96
    assert len(expected) == 343
    assert observation_rows(connection) == expected
    connection.rollback()
    assert capsys.readouterr().out.endswith("8 ficheros, 343 filas nuevas\n")

    # otra vez: nada nuevo y sin error
    assert main([str(ESIOS)]) == 0
    assert capsys.readouterr().out.endswith("8 ficheros, 0 filas nuevas\n")


def test_command_loads_the_good_files_and_fails_on_the_bad_one(
    committed_db_url: str,
    connection: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    def unknown(data: dict) -> None:
        data["indicador"] = 9999

    bad = broken_copy(tmp_path, "precio_spot", unknown)
    monkeypatch.setenv("DATABASE_URL", committed_db_url)
    assert main([str(fixture("eolica_prevista")), str(bad)]) == 1
    assert count(connection) == 24
    connection.rollback()
    out, err = capsys.readouterr()
    assert "desconocido: 9999" in err
    assert out.endswith("2 ficheros, 24 filas nuevas, 1 con error\n")


def test_command_without_database_url_does_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert main([str(ESIOS)]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err


@pytest.mark.parametrize("where", ["no_existe", "vacia"])
def test_command_with_no_files_is_an_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    where: str,
) -> None:
    # la URL no se usa: falla antes de conectar
    monkeypatch.setenv("DATABASE_URL", "postgresql://nadie@127.0.0.1:1/nada")
    path = tmp_path / where
    if where == "vacia":
        path.mkdir()
    assert main([str(path)]) == 2
    assert capsys.readouterr().err.startswith("epf-ingest: ")


def test_command_that_cannot_connect_says_so(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # El puerto 1 no escucha. Linux rechaza la conexión al momento, pero Windows
    # la reintenta y llegaría al tope de 30 s: aquí, 1 s
    monkeypatch.setattr(ingest, "CONNECT_TIMEOUT", 1)
    monkeypatch.setenv("DATABASE_URL", "postgresql://nadie@127.0.0.1:1/nada")
    assert main([str(ESIOS)]) == 2
    assert "no se puede conectar a la base" in capsys.readouterr().err
