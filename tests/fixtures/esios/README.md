# Fixtures con el formato de ESIOS

**Sintéticos: todos los valores son inventados.** Lo que guarda el
archivador no se publica: el token de ESIOS es de uso personal y REE no ha
confirmado las condiciones de reutilización. Estos ficheros solo copian la
estructura de los archivados, `<serie>/<día>.json.gz`, con `indicador`,
`dia`, `publicado_en` (en UTC) y `valores` con los campos que devuelve ESIOS
(`value`, `datetime`, `datetime_utc`, `tz_time`, `geo_id` y `geo_name`).

Los genera [`build.py`](build.py), sin leer ningún fichero ni la red, e
iguales byte a byte cada vez:

```sh
python tests/fixtures/esios/build.py
```

| Día | Qué es | Previsiones | Precio |
| --- | --- | --- | --- |
| 2026-10-25 | Domingo del cambio de hora de octubre: **25 horas** | 25 valores horarios | 100 cuartos |
| 2026-11-04 | Miércoles normal | 24 valores horarios | 96 cuartos |

Cada valor dice qué periodo del día de Madrid es, contando desde 0 a las
00:00:

- **Previsiones (`demanda_prevista`, `eolica_prevista` y `solar_prevista`):**
  una base (20000, 5000 y 1000) más la hora, de 0 a 23 (a 24 el 25 oct). La
  eólica de las 00:00 del 4 nov es 5000.0.
- **Precio (`precio_spot`, indicador 600):** 100 más el cuarto, de 0 a 95 (a
  99 el 25 oct). La media de la hora `h` es 100 + 4h + 1,5: las 20:00 del
  4 nov, 181.5.
- **`publicado_en`:** como lo archivaría el bot, las previsiones a las 11:10
  de Madrid del día anterior y el precio a las 17:29.

**El 25 de octubre**, la hora de las 02:00 locales sale dos veces:
`02:00+02:00` (00:00 UTC) y `02:00+01:00` (01:00 UTC). En hora local se
repite; en UTC no hay ningún hueco ni ningún duplicado.

**Lo que no hay:** ningún día de 23 horas ni con huecos. Se fabrican a mano:
el de 23 horas, a partir del 29 mar 2026 de OMIE (`../omie/`); el de huecos,
quitando valores a uno de estos.
