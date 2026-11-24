"""Carga en `observation` lo que guarda el archivador de ESIOS.

El archivador (el repo privado `archivador_luz`) deja un fichero por serie y día,
`<serie>/<día>.json.gz`, con `indicador`, `dia`, `publicado_en` (la hora a la que lo
descargó, en UTC) y `valores`, tal como los devuelve ESIOS. Cada valor entra como
una fila de `observation`:

- `indicator_id`: el `id` de `indicator` que corresponde al indicador de ESIOS
  (`migrations/0002_reference_data.sql`). Un indicador que no está en el mapa es
  un error: una serie nueva es antes una migración nueva.
- `period_start`: el `datetime_utc` de ESIOS, nunca la hora local.
- `published_at`: el `publicado_en` del archivador. Una descarga posterior del
  mismo día es otra versión y entra como filas nuevas; la misma descarga dos
  veces no entra dos veces (`ON CONFLICT DO NOTHING` sobre la clave primaria).
- `value`: en `Decimal`, exacto desde el JSON (decisión 5 del esquema).

Cada fichero va en su propia transacción: o entra entero o no entra nada.

Desde la terminal, con la cadena de conexión en `DATABASE_URL`:

    epf-ingest datos/                       # todo lo que haya debajo
    epf-ingest datos/precio_spot/2026-11-24.json.gz

Si un fichero falla, sigue con los demás y termina con código 1.
"""

import argparse
import gzip
import json
import os
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import psycopg

# indicador de ESIOS -> indicator.id (migrations/0002_reference_data.sql).
# El 600 va al cuartohorario: el archivador empezó en octubre de 2026, un año
# después del paso del precio a cuartos de hora.
ESIOS_INDICATOR = {1775: 1, 1777: 2, 1779: 3, 600: 4}
CONNECT_TIMEOUT = 30  # segundos

INSERT = (
    "INSERT INTO observation (indicator_id, period_start, published_at, value)"
    " VALUES (%s, %s, %s, %s)"
    " ON CONFLICT DO NOTHING"
)


class IngestError(Exception):
    """Un fichero que no se puede cargar: no tiene el formato del archivador."""


@dataclass(frozen=True)
class Archived:
    """Un fichero del archivador, ya leído y listo para `observation`."""

    indicator_id: int
    published_at: datetime
    values: list[tuple[datetime, Decimal]]  # (period_start, value)


def _aware(text: str, what: str) -> datetime:
    """Una fecha con su desfase. Sin él, Postgres la leería en la zona de la sesión."""
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        raise ValueError(f"{what} sin zona horaria: {text!r}")
    return moment


def read_archived(path: Path) -> Archived:
    """Lee un `.json.gz` del archivador. No toca la base."""
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            data = json.load(f, parse_float=Decimal)
        indicator = data["indicador"]
        if indicator not in ESIOS_INDICATOR:
            raise IngestError(f"{path}: indicador de ESIOS desconocido: {indicator!r}")
        return Archived(
            indicator_id=ESIOS_INDICATOR[indicator],
            published_at=_aware(data["publicado_en"], "publicado_en"),
            values=[
                (_aware(v["datetime_utc"], "datetime_utc"), v["value"])
                for v in data["valores"]
            ],
        )
    except IngestError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise IngestError(f"{path}: no tiene el formato del archivador: {e!r}") from e


def load_file(conn: psycopg.Connection, path: Path) -> tuple[int, int]:
    """Carga un fichero en `observation`, en una sola transacción.

    Si la conexión ya está dentro de una transacción (la de un test, por ejemplo),
    va en un *savepoint*: un fallo deshace solo este fichero. Devuelve cuántas
    filas eran nuevas y cuántas traía el fichero.
    """
    archived = read_archived(path)
    rows = [
        (archived.indicator_id, start, archived.published_at, value)
        for start, value in archived.values
    ]
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(INSERT, rows)
        new = cur.rowcount if rows else 0
    return new, len(rows)


def find_files(paths: Iterable[Path]) -> list[Path]:
    """Los `.json.gz` de cada ruta: el fichero mismo o todos los de la carpeta."""
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.rglob("*.json.gz")))
        elif path.is_file():
            files.append(path)
        else:
            raise IngestError(f"{path}: no existe")
    return files


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="epf-ingest",
        description="Carga en observation los .json.gz del archivador de ESIOS. "
        "La base, la de la variable de entorno DATABASE_URL.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        metavar="RUTA",
        help="ficheros .json.gz o carpetas, que se recorren enteras",
    )
    args = parser.parse_args(argv)

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("epf-ingest: falta la variable de entorno DATABASE_URL", file=sys.stderr)
        return 2
    try:
        files = find_files(args.paths)
    except IngestError as e:
        print(f"epf-ingest: {e}", file=sys.stderr)
        return 2
    if not files:
        # una ruta equivocada no debe pasar por una carga vacía que salió bien
        print("epf-ingest: ningún fichero .json.gz en esas rutas", file=sys.stderr)
        return 2

    try:
        # Neon dormido tarda unos segundos en despertar; sin tope, una URL mal
        # escrita espera minutos
        conn = psycopg.connect(url, connect_timeout=CONNECT_TIMEOUT)
    except psycopg.OperationalError as e:
        print(f"epf-ingest: no se puede conectar a la base: {e}", file=sys.stderr)
        return 2

    failed = 0
    total_new = 0
    with conn:
        for path in files:
            try:
                new, read = load_file(conn, path)
            except IngestError as e:  # el mensaje ya lleva la ruta
                failed += 1
                print(f"ERROR {e}", file=sys.stderr)
                continue
            except psycopg.Error as e:
                failed += 1
                print(f"ERROR {path}: {e}", file=sys.stderr)
                continue
            total_new += new
            print(f"{path}: {new} filas nuevas de {read}")

    print(
        f"{len(files)} ficheros, {total_new} filas nuevas"
        + (f", {failed} con error" if failed else "")
    )
    return 1 if failed else 0
