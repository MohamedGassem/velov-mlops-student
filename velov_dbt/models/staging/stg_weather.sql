-- Silver : météo horaire Open-Meteo, en UTC.
-- Température instantanée à l'heure h, pluie cumulée sur l'heure qui précède h :
-- les deux sont connues à h.
with hourly as (
    select
        filename,
        cast(strptime(unnest(hourly.time), '%Y-%m-%dT%H:%M') as timestamp) at time zone 'UTC' as hour_ts,
        unnest(hourly.temperature_2m) as temperature,
        unnest(hourly.precipitation)  as precipitation
    from read_json('{{ var("bronze") }}/weather/*/*.json', filename = true)
)
select hour_ts, temperature, precipitation
from hourly
-- plusieurs appels couvrent la même heure : on garde la réponse du fichier le plus récent
qualify row_number() over (partition by hour_ts order by filename desc) = 1
