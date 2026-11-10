-- Histórico de precio (OMIE, desde 2014) y de gas (MIBGAS, desde el 16 dic 2015).
--
-- El precio de OMIE es el mismo número que el indicador 600 de ESIOS (ESIOS lo copia
-- de OMIE), pero sale de otra fuente: va en indicadores propios, con source = omie.
-- 2014-2017 llega en los ficheros INT_PBC_EV_H y desde 2018 en marginalpdbc; es la
-- misma serie (el precio marginal del sistema español), así que source_code es
-- 'marginalpdbc' para las dos.
--
-- El gas es el MIBGAS-ES Index («MIBGAS Index» con área ES en algunos años): el precio
-- medio de todo lo negociado para un día de gas en el PVB. Es la única serie diaria
-- que va sin cortes desde la apertura; los índices day-ahead del PVB empiezan en 2023.
INSERT INTO indicator (id, code, source_id, source_code, zone, unit, resolution) VALUES
    (6, 'omie_spot_price_1h',  3, 'marginalpdbc',    'spain', 'EUR/MWh', '1 hour'),
    (7, 'omie_spot_price_15m', 3, 'marginalpdbc',    'spain', 'EUR/MWh', '15 minutes'),
    (8, 'gas_mibgas_es_index', 4, 'MIBGAS-ES Index', 'spain', 'EUR/MWh', '1 day');

-- La vista del precio horario, ahora con las dos fuentes. Para cada hora se queda con
-- la versión completa si la hay y, entre completas, con OMIE; ESIOS cubre los días que
-- el histórico de OMIE todavía no tiene. Las columnas de la 0003 no cambian; se añaden
-- source y estimated al final (CREATE OR REPLACE VIEW solo deja añadir por detrás).
CREATE OR REPLACE VIEW spot_price_hourly AS
WITH latest AS (           -- la última versión de cada periodo; el precio no se revisa
    SELECT DISTINCT ON (o.indicator_id, o.period_start)
           o.indicator_id, o.period_start, o.value, o.published_at, o.estimated
    FROM observation o
    JOIN indicator i ON i.id = o.indicator_id
    WHERE i.code IN ('spot_price_15m', 'spot_price_1h',
                     'omie_spot_price_15m', 'omie_spot_price_1h')
    ORDER BY o.indicator_id, o.period_start, o.published_at DESC
),
hourly AS (
    SELECT date_trunc('hour', l.period_start, 'UTC')      AS period_start,
           avg(l.value)                                    AS value,
           i.resolution                                    AS source_resolution,
           count(*) * i.resolution = interval '1 hour'     AS complete,
           max(l.published_at)                             AS published_at,
           s.code                                          AS source,
           bool_or(l.estimated)                            AS estimated
    FROM latest l
    JOIN indicator i ON i.id = l.indicator_id
    JOIN source s    ON s.id = i.source_id
    GROUP BY 1, i.resolution, s.code
)
SELECT DISTINCT ON (period_start)
       period_start, value, source_resolution, complete, published_at, source, estimated
FROM hourly
ORDER BY period_start, complete DESC, (source = 'omie') DESC;

INSERT INTO schema_migration (version) VALUES ('0004');
