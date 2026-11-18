# Fixtures de OMIE

**Fuente: OMIE ([omie.es](https://www.omie.es)), precio marginal del
mercado diario en el sistema español.** Su aviso legal permite usar
libremente la información pública, respetando su contenido original y
citando la fuente. Los valores van sin tocar; solo cambia el formato de la
hora, pasada a UTC.

`cambios_de_hora.csv`: el precio de OMIE de los ocho días de cambio de hora
de 2023 a 2026, tal como está en `observation` después de cargar el
histórico (indicadores 6 y 7, `estimated = true`). Sacado de la base local
`historico` el 17 nov 2026, con las horas en UTC:

| Día | Horas en Madrid | Filas |
| --- | --- | --- |
| 2023-03-26 | 23 | 23 horas |
| 2023-10-29 | 25 | 25 horas |
| 2024-03-31 | 23 | 23 horas |
| 2024-10-27 | 25 | 25 horas |
| 2025-03-30 | 23 | 23 horas |
| 2025-10-26 | 25 | 100 cuartos |
| 2026-03-29 | 23 | 92 cuartos |
| 2026-10-25 | 25 | 100 cuartos |

Para volver a sacarlo, desde la raíz del repo y con el `compose` en marcha:

```sh
docker compose exec -T db sh -c 'psql -U $POSTGRES_USER -d historico -q' > tests/fixtures/omie/cambios_de_hora.csv <<'EOF'
\copy (SELECT o.indicator_id, to_char(o.period_start AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS period_start, to_char(o.published_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS published_at, o.value, o.estimated FROM calendar_day c JOIN observation o ON o.indicator_id IN (6, 7) AND o.period_start >= c.day::timestamp AT TIME ZONE 'Europe/Madrid' AND o.period_start < (c.day + 1)::timestamp AT TIME ZONE 'Europe/Madrid' WHERE c.hours <> 24 AND c.day BETWEEN '2023-01-01' AND '2026-12-31' ORDER BY o.period_start) TO STDOUT WITH (FORMAT csv, HEADER true)
EOF
```

`frontera_15_min.csv`: el precio de OMIE del 30 sep y del 1 oct 2025, los dos
días de Madrid a cada lado del paso a 15 minutos. El 30 sep, 24 horas
(indicador 6); el 1 oct, el primer día de entrega en cuartos, 96 cuartos
(indicador 7). Sacado de la misma base el 18 nov 2026:

```sh
docker compose exec -T db sh -c 'psql -U $POSTGRES_USER -d historico -q' > tests/fixtures/omie/frontera_15_min.csv <<'EOF'
\copy (SELECT o.indicator_id, to_char(o.period_start AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS period_start, to_char(o.published_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS published_at, o.value, o.estimated FROM observation o WHERE o.indicator_id IN (6, 7) AND o.period_start >= '2025-09-30'::timestamp AT TIME ZONE 'Europe/Madrid' AND o.period_start < '2025-10-02'::timestamp AT TIME ZONE 'Europe/Madrid' ORDER BY o.period_start) TO STDOUT WITH (FORMAT csv, HEADER true)
EOF
```
