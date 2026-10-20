-- Gold : une ligne par station et par heure, au schéma attendu par l'entraînement.
-- La valeur à l'heure h est le dernier relevé connu dans ]h - 1 h, h] :
-- jamais une information postérieure à h (point-in-time correctness).
with obs as (
    select
        station_id,
        date_trunc('hour', reported_at - interval 1 microsecond) + interval 1 hour as hour_ts,
        reported_at,
        bikes_available
    from {{ ref('stg_station_status') }}
    where is_installed
),
last_in_hour as (
    select * from obs
    qualify row_number() over (partition by station_id, hour_ts order by reported_at desc) = 1
)
select
    l.station_id,
    l.hour_ts                  as "timestamp",
    i.capacity,
    l.bikes_available,
    w.temperature,
    w.precipitation > 0        as is_raining
from last_in_hour l
join {{ ref('stg_station_information') }} i using (station_id)
-- jointure interne : une heure dont la météo n'est pas encore publiée attend le prochain run
join {{ ref('stg_weather') }} w on w.hour_ts = l.hour_ts
-- relevés impossibles mis à l'écart (le test bikes_within_capacity les compte)
where l.bikes_available between 0 and i.capacity
