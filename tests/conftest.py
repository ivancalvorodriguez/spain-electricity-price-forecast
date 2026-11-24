"""Un Postgres de usar y tirar para los tests, con las migraciones aplicadas.

Lo caro se hace una vez y lo que los tests ensucian se limpia en cada uno:

- `postgres_url` (sesión): levanta un contenedor de Postgres 18, la misma imagen
  que el `compose.yaml`, aplica `migrations/*.sql` con el `psql` del contenedor,
  como dice el README, y lo borra al terminar. Los datos van en memoria (`tmpfs`):
  no queda nada en disco y no toca ni la base del `compose` ni Neon.
- `connection` (sesión): una sola conexión para toda la sesión.
- `db` (función): esa conexión, dentro de una transacción que se deshace al acabar
  cada test. Lo que inserta un test no lo ve el siguiente, sin vaciar tablas. Un
  `with db.transaction()` dentro del test (el de `epf_spain.ingest.load_file`, por
  ejemplo) es un *savepoint*: no confirma nada. `db.commit()` y `db.rollback()`
  fallan dentro de la transacción del test: ningún test debe llamarlos.
- `load_esios`, `load_omie` y `load_omie_dst` (función): cargan los ficheros de
  `tests/fixtures/` en `observation`, dentro de la transacción del test.
- `committed_db_url` (función): para lo que abre su propia conexión y confirma,
  como el comando `epf-ingest`. La misma base; al acabar, vacía `observation`.

Hace falta Docker en marcha. La primera vez baja la imagen `postgres:18`.
"""

import subprocess
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import psycopg
import pytest

from epf_spain.ingest import load_file

ROOT = Path(__file__).parent.parent
MIGRATIONS = sorted((ROOT / "migrations").glob("*.sql"))
FIXTURES = Path(__file__).parent / "fixtures"
IMAGE = "postgres:18"  # la del compose.yaml


def docker(*args: str, stdin: bytes | None = None) -> str:
    """Lanza `docker` y devuelve lo que escribe; si falla, el error de Docker."""
    r = subprocess.run(["docker", *args], input=stdin, capture_output=True)
    if r.returncode != 0:
        error = r.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"docker {args[0]}: {error}")
    return r.stdout.decode().strip()


def wait_for(url: str, seconds: float = 60) -> None:
    """Espera a que Postgres acepte conexiones por TCP.

    Al arrancar por primera vez, la imagen crea la base con un servidor temporal que
    solo escucha por socket local, y luego lo reinicia. Por TCP solo se entra cuando
    ya está el definitivo, así que basta con reintentar la conexión.
    """
    limit = time.monotonic() + seconds
    while True:
        try:
            psycopg.connect(url, connect_timeout=2).close()
            return
        except psycopg.OperationalError:
            if time.monotonic() > limit:
                raise
            time.sleep(0.2)


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    try:
        docker("version")
    except (FileNotFoundError, RuntimeError) as e:
        pytest.fail(f"Hace falta Docker en marcha: {e}", pytrace=False)

    container = docker(
        "run",
        "--detach",
        "--rm",
        "--env=POSTGRES_PASSWORD=test",
        "--env=POSTGRES_DB=test",
        "--publish=127.0.0.1::5432",  # un puerto libre cualquiera, solo en local
        "--tmpfs=/var/lib/postgresql",
        IMAGE,
    )
    try:
        port = docker("port", container, "5432/tcp").splitlines()[0].rsplit(":", 1)[1]
        url = f"postgresql://postgres:test@127.0.0.1:{port}/test"
        wait_for(url)
        for migration in MIGRATIONS:
            docker(
                "exec",
                "--interactive",
                container,
                *("psql", "-U", "postgres", "-d", "test", "-q"),
                *("-v", "ON_ERROR_STOP=1", "--single-transaction", "-f", "-"),
                stdin=migration.read_bytes(),
            )
        yield url
    finally:
        docker("rm", "--force", container)


@pytest.fixture(scope="session")
def connection(postgres_url: str) -> Iterator[psycopg.Connection]:
    conn = psycopg.connect(postgres_url)
    yield conn
    conn.close()


@pytest.fixture
def db(connection: psycopg.Connection) -> Iterator[psycopg.Connection]:
    # Abierta aquí y no con la primera consulta del test: si lo primero fuera un
    # `with transaction()`, psycopg lo tomaría por la transacción de fuera y la
    # confirmaría al salir
    with connection.transaction(force_rollback=True):
        yield connection


@pytest.fixture
def committed_db_url(
    postgres_url: str, connection: psycopg.Connection
) -> Iterator[str]:
    def count() -> int:
        return connection.execute("SELECT count(*) FROM observation").fetchone()[0]

    # ninguna migración carga observation, y los demás tests no confirman nada
    assert count() == 0
    connection.rollback()
    try:
        yield postgres_url
    finally:
        connection.rollback()
        connection.execute("DELETE FROM observation")
        connection.commit()


@pytest.fixture
def load_esios(db: psycopg.Connection) -> Callable[[str, str], int]:
    """Fábrica: `load_esios("eolica_prevista", "2026-10-25")` carga ese fichero.

    Con la misma función que el comando `epf-ingest` (`epf_spain.ingest.load_file`):
    `period_start` es el `datetime_utc` de ESIOS, `published_at` la hora a la que lo
    archivó el bot, y los valores, en `Decimal`. Devuelve cuántas filas eran nuevas.
    """

    def load(series: str, day: str) -> int:
        new, _ = load_file(db, FIXTURES / "esios" / series / f"{day}.json.gz")
        return new

    return load


@pytest.fixture
def load_omie(db: psycopg.Connection) -> Callable[[str], None]:
    """Fábrica: `load_omie("frontera_15_min")` carga `tests/fixtures/omie/<nombre>.csv`.

    Los CSV de OMIE ya vienen con las columnas de `observation`, en UTC.
    """

    def load(name: str) -> None:
        path = FIXTURES / "omie" / f"{name}.csv"
        with (
            db.cursor() as cur,
            cur.copy(
                "COPY observation"
                " (indicator_id, period_start, published_at, value, estimated)"
                " FROM STDIN WITH (FORMAT csv, HEADER true)"
            ) as copy,
        ):
            copy.write(path.read_bytes())

    return load


@pytest.fixture
def load_omie_dst(load_omie: Callable[[str], None]) -> None:
    """Carga el precio de OMIE de los días de cambio de hora de 2023 a 2026."""
    load_omie("cambios_de_hora")
