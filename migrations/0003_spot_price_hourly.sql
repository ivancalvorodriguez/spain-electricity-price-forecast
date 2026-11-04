-- Precio horario: la media de los cuartos de hora desde que el mercado diario pasó
-- a 15 min (primer día de entrega, 1 oct 2025; subasta del 30 sep), y el horario
-- tal cual antes. source_resolution marca de qué régimen sale cada hora.
CREATE VIEW spot_price_hourly AS
WITH latest AS (           -- la última versión de cada periodo; el precio no se revisa
    SELECT DISTINCT ON (o.indicator_id, o.period_start)
           o.indicator_id, o.period_start, o.value, o.published_at
    FROM observation o
    JOIN indicator i ON i.id = o.indicator_id
    WHERE i.code IN ('spot_price_15m', 'spot_price_1h')
    ORDER BY o.indicator_id, o.period_start, o.published_at DESC
)
SELECT date_trunc('hour', l.period_start, 'UTC')      AS period_start,
       avg(l.value)                                    AS value,
       i.resolution                                    AS source_resolution,
       count(*) * i.resolution = interval '1 hour'     AS complete,
       max(l.published_at)                             AS published_at
FROM latest l
JOIN indicator i ON i.id = l.indicator_id
GROUP BY 1, i.resolution;

INSERT INTO schema_migration (version) VALUES ('0003');
