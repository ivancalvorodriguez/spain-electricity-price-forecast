INSERT INTO source (id, code, name, url) VALUES
    (1, 'esios',  'ESIOS (Red Eléctrica)',        'https://www.esios.ree.es'),
    (2, 'entsoe', 'ENTSO-E Transparency Platform', 'https://transparency.entsoe.eu'),
    (3, 'omie',   'OMIE',                          'https://www.omie.es'),
    (4, 'mibgas', 'MIBGAS',                        'https://www.mibgas.es');

INSERT INTO indicator (id, code, source_id, source_code, zone, unit, resolution) VALUES
    (1, 'demand_forecast', 1, '1775', 'peninsula', 'MW',      '1 hour'),
    (2, 'wind_forecast',   1, '1777', 'peninsula', 'MW',      '1 hour'),
    (3, 'solar_forecast',  1, '1779', 'peninsula', 'MW',      '1 hour'),
    (4, 'spot_price_15m',  1, '600',  'spain',     'EUR/MWh', '15 minutes'),
    (5, 'spot_price_1h',   1, '600',  'spain',     'EUR/MWh', '1 hour');

INSERT INTO schema_migration (version) VALUES ('0002');
