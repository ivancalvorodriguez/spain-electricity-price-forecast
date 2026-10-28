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
