-- Regla 5: un día incompleto no se publica. Si faltan horas reales, se marca el hueco
-- en vez de rellenarlo.
--
-- spot_price_hourly ya marca las horas (complete = false si le falta algún cuarto) y
-- no se inventa las que no tienen ningún dato: esas no salen. Esta vista lo sube al
-- día de Madrid: cuántas horas tiene el día según calendar_day (23, 24 o 25), cuántas
-- tienen algún precio y cuántas están completas. Un día está completo solo si tiene
-- completas todas las suyas; un día de 25 horas con 24 está incompleto.
--
-- Hay una fila por cada día de calendar_day, también los que no tienen ningún precio
-- (hours_present = 0): los huecos se buscan con WHERE NOT complete. Los límites del día
-- se calculan con AT TIME ZONE 'Europe/Madrid', que no depende de la zona de la sesión.
-- El LATERAL hace que cada día lea solo sus horas, con el índice de la 0006, en vez de
-- calcular la vista horaria entera.
CREATE VIEW spot_price_day AS
SELECT c.day,
       c.hours,
       p.hours_present,
       p.hours_complete,
       p.hours_complete = c.hours AS complete
FROM calendar_day c
CROSS JOIN LATERAL (
    SELECT count(*)                          AS hours_present,
           count(*) FILTER (WHERE h.complete) AS hours_complete
    FROM spot_price_hourly h
    WHERE h.period_start >= c.day::timestamp AT TIME ZONE 'Europe/Madrid'
      AND h.period_start < (c.day + 1)::timestamp AT TIME ZONE 'Europe/Madrid'
) p;

INSERT INTO schema_migration (version) VALUES ('0007');
