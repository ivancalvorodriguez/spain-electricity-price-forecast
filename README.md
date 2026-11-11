# spain-electricity-price-forecast
> Un sistema que cada día publica una previsión del precio horario del mercado eléctrico español para los días 2 a 7, con intervalo de incertidumbre y las seis horas más baratas de cada día, y que publica también su error real del día anterior. Solo usa información que existía antes del cierre de la subasta, y se valida con previsiones archivadas tal como se publicaron. Funciona si, en un periodo de prueba fijo, bate con claridad a la previsión ingenua, se compara contra LEAR con un test de Diebold-Mariano, y publica su error todos los días sin huecos.

## Estado

En construcción.

## Arranque local

Hace falta Docker con Compose (Docker Desktop en Windows y macOS).

1. Copia `.env.example` como `.env` y pon una contraseña en `POSTGRES_PASSWORD`.
   Vale cualquiera: es solo para la base local. Sin contraseña, Postgres no arranca.
2. Levanta todo: `docker compose up -d --build --wait`
3. Comprueba que responde: <http://127.0.0.1:8000/health> devuelve `{"status": "ok"}`.

Qué arranca:

- `db`: Postgres 18 con los datos en el volumen `pgdata`.
  Puerto 5432, solo en la máquina local.
- `web`: el servicio (FastAPI), en el puerto 8000. No arranca hasta que `db` está lista.

Para pararlo, `docker compose down`. Con `-v` se borran también los datos.

Sin Docker, solo el servicio web: `pip install -e .` y `epf-web`.

## Base de datos

Una tabla estrecha, `observation`: un valor, el inicio del periodo al que
se refiere (`period_start`) y cuándo se supo (`published_at`), las dos en
`timestamptz`. Con `published_at`, «la mejor previsión que existía antes
del cierre» es una consulta y no una reconstrucción. Cada serie es una fila
de `indicator` (fuente, código en la fuente, zona, unidad y resolución), y
cada fuente, una de `source`.

### Migraciones

Ficheros SQL numerados en [`migrations/`](migrations), aplicados en orden
con `psql`, cada uno en una sola transacción. Cada fichero termina
apuntándose en `schema_migration`: `TABLE schema_migration;` dice en qué
punto está una base. Si se aplica dos veces el mismo fichero, falla por
clave duplicada y no cambia nada.

- `0001_schema.sql`: `schema_migration`, `source`, `indicator` y
  `observation`.
- `0002_reference_data.sql`: las fuentes y los indicadores, con sus `id`.
  Los datos de referencia van en migraciones y no en la carga: la carga
  depende de esos `id`, y una base creada desde cero queda completa. Una
  serie nueva es una migración nueva.
- `0003_spot_price_hourly.sql`: la vista del precio horario.
- `0004_history_omie_mibgas.sql`: los indicadores del histórico (el precio
  de OMIE, horario y cuartohorario, y el índice diario de gas de MIBGAS) y
  la vista del precio horario con las dos fuentes.
- `0005_holiday_calendar.sql`: los festivos de España (por comunidad) y
  de Portugal de 2014 a 2027, y la vista `calendar_day`.
- `0006_observation_hour_index.sql`: el índice que usa la vista del
  precio horario al filtrar por fechas
  ([`docs/rendimiento.md`](docs/rendimiento.md)).

En Windows no hace falta instalar `psql`: se usa el del contenedor `db`.
Para aplicarlas desde cero en una base local:

```sh
docker compose cp migrations db:/tmp/
docker compose exec -T db sh -c 'for f in /tmp/migrations/*.sql; do echo == $f; psql -U $POSTGRES_USER -d $POSTGRES_DB -v ON_ERROR_STOP=1 --single-transaction -q -f $f || exit 1; done'
```

Las variables las expande el `sh` del contenedor, no tu terminal. En `cmd`,
que no entiende las comillas simples, cámbialas por dobles.

En Neon, igual pero con `psql $DATABASE_URL_DIRECT` en lugar de `-U … -d …`.
Las migraciones van por la **cadena directa** (el host sin `-pooler`),
que está solo en el `.env` local: el *pooler* de Neon va en modo
*transaction* y no conserva el estado de sesión. El servicio web usa el
*pooler*.

### El precio: de horario a cuartohorario

El mercado diario pasó a periodos de 15 minutos el 1 de octubre de 2025
(primer día de entrega; la subasta, el 30 de septiembre). El precio se
guarda tal como se publica, con un indicador por resolución
(`spot_price_1h` antes y `spot_price_15m` después), y la vista
`spot_price_hourly` da una serie horaria continua: la media de los cuatro
cuartos de cada hora y, antes de la frontera, el precio horario tal cual.
`source_resolution` dice de qué régimen sale cada hora, y `complete`
marca las horas a las que les falta algún cuarto. Se agrupa por hora UTC:
como Madrid está a horas enteras de UTC, los días de 23 y 25 horas salen
bien.

### El histórico: OMIE y MIBGAS

El precio desde el 1 de enero de 2014 sale de los ficheros públicos de
OMIE, sin token. No se pide a ESIOS: su token es de uso personal, y doce
años de precio pedidos a su API serían una descarga masiva. Es el mismo
número que el indicador 600 de ESIOS (coinciden cuarto a cuarto del 8 de
octubre al 10 de noviembre de 2026), pero va en indicadores propios,
`omie_spot_price_1h` y `omie_spot_price_15m`, con `source = omie`. De
2014 a 2017 llega en los ficheros `INT_PBC_EV_H`, y desde 2018, en
`marginalpdbc`. Si OMIE republicó un día (`.2`, `.3`), vale la versión
más alta.

La vista `spot_price_hourly` junta las dos fuentes: en cada hora, la
versión completa y, entre completas, la de OMIE. ESIOS cubre los días que
el histórico de OMIE todavía no tiene. La columna `source` dice de dónde
sale cada hora.

El gas es el **MIBGAS-ES Index** (en los ficheros de 2015-2017 y
2021-2022, «MIBGAS Index» con área ES): el precio medio de todo lo negociado para un día de gas en el
PVB, en EUR/MWh, en `gas_mibgas_es_index`. Es la única serie diaria sin
cortes desde que abrió el mercado; los índices *day-ahead* del PVB
empiezan en 2023.

**MIBGAS abrió el 16 de diciembre de 2015** (el primer día de gas con
índice es el 17). Antes no hay precio de gas ibérico, así que **2014 y
2015 solo sirven como rezagos del precio**: cualquier modelo con gas
empieza en 2016.

Nada del histórico tiene hora de descarga real, así que va con
`estimated = true` y una `published_at` nominal:

- **Precio:** D-1 a las 13:00 de Madrid, la hora de la casación.
- **Gas:** el final del día de gas, D+1 a las 00:00 de Madrid. MIBGAS
  calcula el índice con todas las sesiones ya cerradas para ese día y
  actualiza la tabla a las 21:30; se redondea hacia después para no usar
  nunca un valor antes de que existiera. Para la subasta de D+1, que se
  cierra a mediodía de D, el último índice disponible es el de D-1.

### Festivos y calendario

Lo único que se sabe de cada día antes de que llegue y que no se revisa
nunca: con el precio rezagado y el gas, es lo que puede entrar en el
backtest largo.

`holiday` tiene una fila por día y ámbito. El ámbito es el código ISO
3166-2 de cada comunidad (`ES-AN` … `ES-ML`, con Ceuta y Melilla) o `PT`
para Portugal: el mercado diario es ibérico. No hay fila «nacional»: un
festivo nacional es el que tienen todas las comunidades.

- **España**, de 2014 a 2027, de las resoluciones anuales del BOE con
  la relación de fiestas laborales, tal como se publicaron (el
  identificador de cada una está en la migración). Si una comunidad
  cambió después alguna fecha en su boletín, aquí no está. Las fiestas
  locales y las insulares de Canarias quedan fuera.
- **Portugal**, los feriados obligatorios del Código do Trabalho. De 2013
  a 2015 se suspendieron cuatro (Corpo de Deus, 5 de outubro, 1 de
  novembro y 1 de dezembro). El Carnaval no es feriado obligatorio.

La vista `calendar_day` da un día por fila, desde enero del primer año
con festivos hasta diciembre del último. Más allá no inventa nada: si un
año no tiene festivos cargados, no sale. Columnas: `isodow` (1, lunes),
`holiday_regions` (cuántas de las 15 comunidades peninsulares tienen
fiesta, porque las previsiones de ESIOS y el precio son del sistema
peninsular), `national_holiday` (fiesta en las 15), `pt_holiday` y
`hours` (23 o 25 el día del cambio de hora, en hora de Madrid).

**Cada año nuevo es una migración nueva**, en cuanto salga su BOE (hacia
octubre). La 2028 hace falta antes de que el modelo prevea días de 2028:
la última semana de diciembre de 2027 ya mira a D+7.

## Despliegue

Está en <https://epf-spain.onrender.com>, un Web Service gratuito de Render
en Frankfurt. La imagen es la del `Dockerfile` y la base de datos, Postgres
en Neon. Despliega la CI: cuando `main` pasa las comprobaciones, el workflow
llama al gancho de Render con ese commit.

El plan gratuito tiene 512 MB de memoria y 0,1 CPU, y se apaga a los 15
minutos sin tráfico: la primera visita después tarda alrededor de un minuto.
Para una página que lee ficheros precalculados es asumible.

Lo que se rompió en cada despliegue, y por qué, está en
[`docs/despliegues.md`](docs/despliegues.md).

## Test de fuga: ¿revisa ESIOS las previsiones D+1?

**Pregunta.** Cuando se consulta la API días después, ¿devuelve la previsión
D+1 tal como se publicó o una versión revisada? Si la revisa, un backtest
con previsiones históricas usaría información del futuro.

**Método.** Se compararon las previsiones que un archivador propio guarda
cada día en el momento de su publicación (hacia las 11:10, hora de Madrid,
del día anterior) con las mismas series descargadas de nuevo dos veces, el
14/10/2026 y el 28/10/2026: demanda (1775), eólica (1777) y solar (1779),
para los días del 11 al 14/10/2026. En cada descarga, 3 indicadores × 4 días
× 24 h = 288 valores horarios, emparejados por hora.

**Resultado.** Ninguno de los 288 valores cambia, ni el 14/10/2026 (de 1 a
4 días después de publicarse) ni el 28/10/2026 (de 15 a 18 días después).

**Conclusión.** Las previsiones D+1 no se revisan después de publicarse: el
histórico de ESIOS es honesto y el modelo se puede validar también hacia
atrás. La muestra son cuatro días de octubre de 2026: no dice si ESIOS
revisaba las previsiones en años anteriores.

## Convención de ramas

- `main` siempre funciona: solo entra lo que está terminado.
- Una rama por trabajo, con el mismo prefijo que los commits: `feat/...`, `fix/...`, `docs/...`, `chore/...`.
- Cuando el trabajo está listo, se fusiona en `main` y se borra la rama.

## Licencia

MIT
