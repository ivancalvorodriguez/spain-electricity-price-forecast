# Despliegues

Qué se rompió en cada despliegue público y por qué. Se relee antes del
siguiente.

## Antes de desplegar

- `main` despliega sola: cualquier push que pase las comprobaciones llama
  al gancho de Render, también si solo cambia el README (el `Dockerfile`
  lo copia, así que la imagen cambia igual).
- Si el despliegue falla en Render, la CI sigue en verde: el gancho solo
  pide el despliegue y no espera a que termine. Hay que mirar *Deploys* en
  Render y abrir `/health` a mano.
- Si `/health` no responde en 15 minutos, Render da el despliegue por
  fallido y deja la versión anterior. El error está en el log del
  despliegue, en *Deploys*; el del servicio en marcha, en *Logs* (duran
  7 días).
- Las variables de entorno de Render llegan también al build como
  argumentos de Docker. No declarar nunca un `ARG` con un secreto.
- Para cambiar `DATABASE_URL`: *Environment* → *Save and deploy*.
  *Save only* no la aplica hasta el siguiente despliegue.

## 27/10/2026 · primer despliegue (`6fd5433`, PR #4)

**Qué se hizo.** Web Service `epf-spain` en Render (Docker, Frankfurt,
plan gratuito), con `DATABASE_URL` del *pooler* de Neon, *Health Check
Path* `/health` y *Auto-Deploy* en *Off*. La URL del gancho, en los
secrets de Actions como `RENDER_DEPLOY_HOOK_URL`. Al fusionar el PR, los
dos trabajos en verde y el gancho llamado con el commit comprobado.

**Qué se rompió.** Nada: el primer despliegue salió a la primera.

**Lo que podía haberse roto:**

- *Auto-Deploy* viene en *On Commit* al crear el servicio. Si se queda
  así, cada push despliega dos veces: una por Render y otra por el gancho.
- En el primer despliegue no hay versión anterior. Si `/health` hubiera
  fallado, el servicio se habría quedado sin nada.
- Al fusionar un PR con *squash*, GitHub propone como título el nombre de
  la rama («Ci/deploy (#4)»). Se corrige a mano antes de fusionar.
- Render pone `PORT=10000` y pide escuchar en `0.0.0.0`. `web.py` ya lo
  hacía, y se probó en local el 26/10 con la imagen de producción.

## 28/10/2026 · la URL desde fuera

**Qué se comprobó.** `https://epf-spain.onrender.com/health` desde el
móvil, con datos: responde `{"status":"ok"}`, con el certificado válido.
Por HTTP redirige a HTTPS (301). Con el servicio dormido, la primera
respuesta tarda alrededor de un minuto.

**Qué se rompió.** Nada.

## 02/11/2026 · el gancho, al entorno `production`

**Qué se hizo.** Entorno `production` en GitHub, con *Deployment
branches* limitado a `main`. `RENDER_DEPLOY_HOOK_URL` pasa del
repositorio al entorno, y el trabajo `desplegar` lo declara con la URL
del servicio. El paso del gancho falla si la URL llega vacía, en vez de
saltarse en verde.

**Qué se rompió.** Nada.

**Lo que podía haberse roto:**

- Un secreto no se puede volver a leer en GitHub: la URL del gancho se
  copia otra vez de Render (*Settings* → *Deploy Hook*).
- Si el repo pasara a privado, el plan gratuito deja de aplicar los
  entornos: `desplegar` se quedaría sin el gancho y ahora saldría en rojo.

## 04/11/2026 · el esquema, en Neon (migraciones 0001-0003)

**Qué se hizo.** Las tres primeras migraciones (`schema_migration`,
`source`, `indicator` y `observation`; las fuentes y los indicadores; la
vista `spot_price_hourly`), aplicadas en la rama `production` de Neon,
que estaba vacía, con el `psql` del contenedor `db` y la cadena directa
(`DATABASE_URL_DIRECT`, solo en el `.env` local). Antes, probadas desde
cero en el Postgres 18 del `compose`, con los datos del archivador del 1
al 5 de noviembre.

**Qué se rompió.** Nada: las tres entraron a la primera. Se aplicaron
15 segundos después de fusionar el PR #7, no antes como estaba previsto.
No tuvo efecto porque el servicio todavía no lee la base, pero en
adelante la migración va antes de fusionar: cuando el código use una
tabla nueva, desplegarlo sin ella rompe el servicio.

**Lo que podía haberse roto:**

- Por el *pooler* (el host con `-pooler`), las migraciones pueden fallar
  o quedarse a medias: va en modo *transaction* y no conserva el estado
  de sesión. Van siempre por la cadena directa.
- Sin `--single-transaction`, un error a mitad de fichero deja la base a
  medio migrar. Con él, `TABLE schema_migration;` dice exactamente qué
  ficheros han entrado.
- El servicio web no lee todavía la base: si el esquema estuviera mal,
  `/health` seguiría en verde. La comprobación es `TABLE schema_migration;`
  y `\dt` en Neon, no el despliegue.

## 10/11/2026 · el histórico, en Neon (migración 0004 y carga)

**Qué se hizo.** La `0004_history_omie_mibgas.sql` (los indicadores 6 y 7,
el precio de OMIE horario y cuartohorario, y el 8, el MIBGAS-ES Index; y la
vista `spot_price_hourly` con las dos fuentes), aplicada en la rama
`production` de Neon por la cadena directa, con `--single-transaction`.
Después, la carga del histórico con `cargar_historico.sql` (fuera del repo):
145.943 filas en 3 segundos, del 1 de enero de 2014 al 10 de noviembre de
2026 en precio y del 17 de diciembre de 2015 al 8 de noviembre de 2026 en
gas. Antes, lo mismo en una base local desde cero (`historico`, en el
`compose`). Esta vez la migración va **antes** de fusionar, como se apuntó
el 04/11: el PR de `feat/historical-load` todavía no existe.

**Qué se rompió.** Nada. En Neon salen los mismos recuentos que en local,
112.728 horas seguidas sin ninguna incompleta, ningún día de gas de menos
y la misma suma de control de todos los valores (10.417.389,20). La base
ocupa 22 MB.

**Lo que podía haberse roto:**

- La 0004 rehace la vista con `CREATE OR REPLACE VIEW`, que solo deja
  añadir columnas por detrás. Si se hubiera cambiado el nombre o el tipo
  de una columna de la 0003, la migración habría fallado entera (y, por
  la transacción, sin dejar nada a medias).
- El CSV de la carga se genera fuera del repo y no está versionado. Para
  repetir la carga hay que regenerarlo con `cargar_historico.py` desde
  `historico/`; si OMIE republica un día, saldría una versión distinta.
- En Neon no hay todavía nada de lo archivado de ESIOS: la vista sale
  entera de OMIE. Cuando entre lo archivado, la vista usa ESIOS solo para
  las horas que OMIE no tenga.

## 11/11/2026 · festivos, calendario e índice, en Neon (migraciones 0005 y 0006)

**Qué se hizo.** La `0005_holiday_calendar.sql` (la tabla `holiday`, con
las fiestas laborales de cada comunidad de 2014 a 2027 según el BOE y los
feriados obligatorios de Portugal, y la vista `calendar_day`) y la
`0006_observation_hour_index.sql` (el índice sobre
`date_trunc('hour', period_start, 'UTC')` para la vista del precio),
aplicadas a las 13:50 en la rama `production` de Neon por la cadena
directa, cada una con `--single-transaction`. Antes de fusionar el PR de
`feat/holiday-calendar`, como se apuntó el 04/11. Antes, probadas desde
cero (0001-0006) en una base aparte del `compose` y encima de la base
local `historico`.

**Qué se rompió.** Nada. En Neon salen los mismos números que en local:
3.366 filas en `holiday` (3.192 de España y 174 de Portugal), y 5.113
días en `calendar_day`, con 28 cambios de hora y 121 festivos nacionales.
La consulta de un día de precio usa el índice nuevo y tarda 2 ms. Son 96
filas de OMIE: en Neon no hay nada archivado de ESIOS. La base ocupa
25 MB (22 MB antes).

**Lo que podía haberse roto:**

- En `cmd`, el `sh -c` va con comillas dobles. `$DATABASE_URL_DIRECT` va
  sin comillas dentro del `sh`: la cadena lleva `&` (`sslmode=require&…`),
  pero al expandir una variable `sh` no vuelve a interpretar el `&`.
- La 0005 no se puede aplicar dos veces: falla en el `CREATE TABLE
  holiday` y, por la transacción, no deja nada a medias.
- Los festivos de 2028 no están. Hace falta una migración nueva en cuanto
  salga su BOE (hacia octubre de 2027), antes de que D+7 caiga en 2028.
  `calendar_day` termina el 31/12/2027 y no inventa días.

**Qué se rompió al fusionar: el gancho de Render, 27 minutos colgado.**
Al fusionar el PR #10 (`fe228db`), `comprobaciones` pasó en 16 s, pero en
`desplegar` el paso *Llamar al gancho de Render* empezó a las 13:54 y
terminó en rojo a las 14:21 (intento 1 de la ejecución 43024319754). El
error: `Process completed with exit code 22`, el código de `curl --fail`
cuando el servidor responde con un error HTTP. La línea del log:
`curl: (22) The requested URL returned error: 520`. El 520 no lo da
Render, sino Cloudflare, que va delante: significa que el servidor de
detrás devolvió algo que Cloudflare no entendió o cortó la conexión. La
respuesta llegó a los 27 minutos. Mientras,
el panel de Render se quedaba en *Loading* y su página de estado decía
*All Systems Operational*. Hacia las 14:20 volvió el panel. Con *Re-run
failed jobs* (intento 2), el gancho respondió en 1 s a las 14:27, y
`/health` dio 200. La base no se vio afectada: las migraciones ya estaban
en Neon desde las 13:50.

**Lo que podía haberse roto:**

- Ni el `curl` tenía `--max-time` ni el trabajo `timeout-minutes`. Si
  Render no hubiera contestado nunca, `desplegar` habría esperado hasta
  6 horas (el límite de GitHub) y, por el `concurrency`, los despliegues
  de detrás se habrían quedado en cola todo ese tiempo. Arreglado el
  16/11 (entrada de abajo).
- La página de estado de Render no sirve para saber si el fallo es suyo:
  decía que todo iba bien con el panel caído.

## 16/11/2026 · la CI, como mucho 5 minutos

**Qué se hizo.** `timeout-minutes: 5` en los dos trabajos de `ci.yml`
(hoy tardan 16 y 4 s) y, en el `curl` del gancho, `--max-time 60
--retry 2 --retry-all-errors`: un minuto por intento y dos reintentos.
Los tres intentos, con sus esperas, caben en los 5 minutos.
`--retry-all-errors` hace falta por el 520 del 11/11: `--retry` solo
reintenta si no hay respuesta o con un 408, 429, 500, 502, 503 o 504, y
probado en local contra un servidor que da 520, hace un solo intento.
Con la opción, hace los tres. Si el gancho vuelve a colgarse, el trabajo sale en rojo en
unos 3 minutos y se relanza a mano con *Re-run failed jobs*, como el
11/11.

**Qué se rompió.** Nada.

**Lo que podía haberse roto:**

- Si Render recibe la petición pero la respuesta no llega, `curl`
  reintenta y Render encola dos despliegues del mismo commit. No hace
  daño: el segundo despliega la misma imagen.
- Con `--retry-all-errors` también se reintenta un error que no se va a
  arreglar solo, como un 404 si la URL del gancho está mal. Cuesta 3 s
  de más (las esperas de 1 y 2 s) y el trabajo sale en rojo igual.
- Con el tope, un `docker build` lento (sin caché, con una dependencia
  nueva pesada) podría pasar de 5 minutos y poner `comprobaciones` en
  rojo sin que haya nada mal. Si pasa, se sube el tope de ese trabajo,
  no se quita.

## 18/11/2026 · días completos, en Neon (migración 0007)

**Qué se hizo.** La `0007_spot_price_day.sql` (la vista `spot_price_day`:
una fila por día de Madrid con las horas que tiene, 23, 24 o 25, las que
tienen precio y las completas, y `complete` solo si lo están todas; es la
regla 5, un día incompleto no se publica), aplicada el 18/11 en la rama
`production` de Neon por la cadena directa, con `--single-transaction`.
Antes de fusionar el PR de `test/dst-utc`, como la 0005 y la 0006. Antes,
probada en el Postgres de usar y tirar de los tests (72 en verde) y
encima de la base local `historico`, dentro de una transacción deshecha:
5 ms por día y 160 ms los doce años, con el índice de la 0006.

**Qué se rompió.** Nada. `schema_migration` llega a `0007`. Antes de hoy
hay 7 días incompletos, del 11/11 al 17/11: el precio cargado en Neon
llega hasta el 10/11. Del 1/1/2014 al 10/11/2026 no hay ninguno, igual
que en local.

**Lo que podía haberse roto:**

- La 0007 no se puede aplicar dos veces: falla en el `CREATE VIEW` y, por
  la transacción, no deja nada a medias.
- `spot_price_day` depende de `spot_price_hourly` y de `calendar_day`.
  Una migración futura que cambie una de las dos con `CREATE OR REPLACE
  VIEW` solo puede añadir columnas por detrás; para quitar o renombrar
  una, Postgres obliga a borrar y volver a crear también esta.
- `calendar_day` termina el 31/12/2027, y esta vista también: un día de
  2028 no tendría fila y no saldría como hueco. Se arregla con la
  migración de festivos de 2028.
- Mientras no se cargue el precio desde el 11/11, esos días salen
  incompletos. Es lo correcto: no hay precio. El servicio todavía no
  publica nada a partir de esta vista.

## 23/11/2026 · los tests, en la CI

**Qué se hizo.** `comprobaciones` instala el grupo `dev` del
`pyproject.toml` (`pip install -e ".[dev]"`, con la caché de pip de
`setup-python`), baja `postgres:18` en su propio paso y pasa `pytest -ra`
entre ruff y la imagen. Los 72 tests corren contra el Postgres de usar y
tirar de `tests/conftest.py`, con el Docker que ya trae el runner. Antes,
en local, 72 en verde en 3,4 s, y también en un clon limpio con un
entorno nuevo. Un test en rojo para el despliegue: `desplegar` necesita
`comprobaciones`.

**Qué se rompió.** *(Por rellenar al fusionar: tiempo de `comprobaciones`,
CI y `/health`.)*

**Lo que podía haberse roto:**

- Los tests dependen de Docker Hub: si no se puede bajar `postgres:18`,
  `comprobaciones` sale en rojo y no se despliega, aunque el código esté
  bien. Se relanza con *Re-run failed jobs*.
- `postgres:18` es una etiqueta que se mueve: cada versión menor nueva
  entra sola en los tests, igual que en el `compose`. Si un test rompe sin
  haber cambiado nada, mirar primero qué versión bajó el paso.
- En la CI, `zoneinfo` usa la base de zonas de Ubuntu; en Windows, el
  paquete `tzdata`. Si algún año cambian las reglas de Europe/Madrid,
  pueden no coincidir hasta que se actualicen las dos.
- La descarga de la imagen y la instalación alargan el trabajo. Con el
  tope de 5 minutos, si un día pasa de ahí sin estar colgado, se sube el
  tope, no se quita.
