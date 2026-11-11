# Rendimiento de las consultas

Las consultas del servicio, medidas con `EXPLAIN (ANALYZE, BUFFERS)` sobre
el histórico entero (151.446 filas en `observation`, 23 MB la base) en el
Postgres 18 del `compose`, después de `ANALYZE`. Se repiten cuando la
tabla crezca o cambie una vista.

## 11/11/2026 · con el histórico cargado (migraciones 0001-0006)

| Consulta | Antes de la 0006 | Después | Plan |
|---|---|---|---|
| Precio horario de un día (`spot_price_hourly`) | 18,6 ms | 0,34 ms | *Index Scan* en `observation_hour_utc_idx` |
| Precio horario de cuatro semanas | 23,0 ms | 7,0 ms | ídem |
| Serie horaria entera, 2014-2026 (backtest) | 268 ms | igual | *Seq Scan*, sin índice que valga |
| Eólica de mañana, la última publicada antes de las 12:00 | 1,1 ms | igual | *Index Scan* en la clave primaria |
| Último gas publicado antes de la subasta | 0,4 ms | igual | *Index Scan Backward* en la clave primaria |
| Precio de cuatro semanas con `calendar_day` | — | 13,4 ms | el índice, y la vista del calendario entera (5.113 días) |

### La consulta lenta: un día de la vista del precio

```sql
SELECT period_start, value, source FROM spot_price_hourly
WHERE period_start >= '2026-11-09 23:00+00' AND period_start < '2026-11-10 23:00+00';
```

**Antes.** La vista agrupa por `date_trunc('hour', period_start, 'UTC')`,
así que el filtro llega a `observation` envuelto en esa expresión. La
clave primaria `(indicator_id, period_start, published_at)` no sirve:
para 24 horas se lee la tabla entera.

```
->  Parallel Seq Scan on observation o  (actual time=12.222..12.824 rows=132.00 loops=2)
      Filter: ((date_trunc('hour'::text, period_start, 'UTC'::text) >= '2026-11-09 23:00:00+00')
           AND (date_trunc('hour'::text, period_start, 'UTC'::text) < '2026-11-10 23:00:00+00'))
      Rows Removed by Filter: 75591
      Buffers: shared hit=1115
Execution Time: 18.646 ms
```

La estimación también falla: el planificador esperaba 15 filas al final
y salieron 24; a la salida del *scan*, 445 por proceso frente a 132.

**El índice** (`migrations/0006_observation_hour_index.sql`), sobre la
misma expresión que usa la vista. Se puede indexar porque la versión de
`date_trunc` con zona explícita es `IMMUTABLE` (la de dos argumentos,
que depende de la zona de la sesión, es `STABLE` y no se puede):

```sql
CREATE INDEX observation_hour_utc_idx
    ON observation (date_trunc('hour', period_start, 'UTC'));
```

**Después.** Ocupa 2,8 MB y, con `ANALYZE`, Postgres guarda estadísticas
de la expresión: la estimación pasa a 226 filas para 264 reales.

```
->  Index Scan using observation_hour_utc_idx on observation o  (actual time=0.004..0.032 rows=264.00 loops=1)
      Index Cond: ((date_trunc('hour'::text, period_start, 'UTC'::text) >= '2026-11-09 23:00:00+00')
               AND (date_trunc('hour'::text, period_start, 'UTC'::text) < '2026-11-10 23:00:00+00'))
Execution Time: 0.344 ms
```

### Lo que no se ha tocado, y por qué

- **Un índice parcial solo con el precio** no lo usaría la vista: elige
  los indicadores con un `JOIN` por `indicator.code`, y el planificador
  solo usa un índice parcial si la consulta implica su `WHERE`.
- **La serie entera** se lee con un *Seq Scan* y ordena en disco
  (`external merge`, unos 6 MB) con el `work_mem` por defecto de 4 MB.
  Es la consulta del backtest, una vez por ejecución: si molesta, se sube
  `work_mem` en esa sesión, no en el servidor.
- **`calendar_day`** se calcula entera en cada consulta (5.113 días, unos
  5 ms), porque el filtro por fecha no le llega a través del `JOIN`. Para
  el tamaño que tiene, no compensa una tabla materializada.
- **Point-in-time y gas** ya van por la clave primaria. En el gas,
  `published_at` entra como condición dentro del índice, no como rango,
  pero solo hay unas 4.000 filas del indicador 8.
