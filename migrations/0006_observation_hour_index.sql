-- Índice para la vista spot_price_hourly. La vista agrupa por
-- date_trunc('hour', period_start, 'UTC'), así que un filtro por fechas sobre la vista
-- llega a observation envuelto en esa expresión: la clave primaria, que empieza por
-- indicator_id y lleva period_start tal cual, no sirve, y cada consulta lee la tabla
-- entera. Con el histórico (151.446 filas), un día de precio pasa de 18,6 ms a 0,4 ms
-- y cuatro semanas, de 23 a 7 ms (docs/rendimiento.md). La versión de date_trunc con
-- zona horaria explícita es IMMUTABLE, y por eso se puede indexar.
--
-- No es un índice parcial (solo los indicadores de precio): la vista elige los
-- indicadores con un JOIN por indicator.code, no con una condición sobre indicator_id,
-- y el planificador solo usa un índice parcial si la consulta implica su WHERE.
CREATE INDEX observation_hour_utc_idx
    ON observation (date_trunc('hour', period_start, 'UTC'));

INSERT INTO schema_migration (version) VALUES ('0006');
