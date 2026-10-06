# spain-electricity-price-forecast
> Un sistema que cada día publica una previsión del precio horario del mercado eléctrico español para los días 2 a 7, con intervalo de incertidumbre y las seis horas más baratas de cada día, y que publica también su error real del día anterior. Solo usa información que existía antes del cierre de la subasta, y se valida con previsiones archivadas tal como se publicaron. Funciona si, en un periodo de prueba fijo, bate con claridad a la previsión ingenua, se compara contra LEAR con un test de Diebold-Mariano, y publica su error todos los días sin huecos.

## Estado

En construcción.

## Convención de ramas

- `main` siempre funciona: solo entra lo que está terminado.
- Una rama por trabajo, con el mismo prefijo que los commits: `feat/...`, `fix/...`, `docs/...`, `chore/...`.
- Cuando el trabajo está listo, se fusiona en `main` y se borra la rama.

## Licencia

MIT
