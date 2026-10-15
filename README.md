# spain-electricity-price-forecast
> Un sistema que cada día publica una previsión del precio horario del mercado eléctrico español para los días 2 a 7, con intervalo de incertidumbre y las seis horas más baratas de cada día, y que publica también su error real del día anterior. Solo usa información que existía antes del cierre de la subasta, y se valida con previsiones archivadas tal como se publicaron. Funciona si, en un periodo de prueba fijo, bate con claridad a la previsión ingenua, se compara contra LEAR con un test de Diebold-Mariano, y publica su error todos los días sin huecos.

## Estado

En construcción.

## Test de fuga: ¿revisa ESIOS las previsiones D+1?

**Pregunta.** Cuando se consulta la API días después, ¿devuelve la previsión
D+1 tal como se publicó o una versión revisada? Si la revisa, un backtest
con previsiones históricas usaría información del futuro.

**Método.** Se compararon las previsiones que un archivador propio guarda
cada día en el momento de su publicación (hacia las 11:10, hora de Madrid,
del día anterior) con las mismas series descargadas de nuevo el 14/10/2026:
demanda (1775), eólica (1777) y solar (1779), para los días del 11 al
14/10/2026. En total, 3 indicadores × 4 días × 24 h = 288 valores
horarios, emparejados por hora.

**Resultado (14/10/2026).** Ninguno de los 288 valores cambia.

**Conclusión (provisional).** Las previsiones D+1 no se revisan, al menos
durante los primeros 1 a 4 días. Si se confirma, el histórico de ESIOS es
honesto y el modelo se puede validar también hacia atrás. Cuatro días es
una muestra pequeña: se repetirá hacia el 28/10/2026 para descartar
revisiones más tardías.

## Convención de ramas

- `main` siempre funciona: solo entra lo que está terminado.
- Una rama por trabajo, con el mismo prefijo que los commits: `feat/...`, `fix/...`, `docs/...`, `chore/...`.
- Cuando el trabajo está listo, se fusiona en `main` y se borra la rama.

## Licencia

MIT
