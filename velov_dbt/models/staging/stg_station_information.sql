-- Silver : le référentiel des stations, dans sa dernière version publiée.
select
    cast(s.station_id as integer) as station_id,
    s.name,
    s.lat,
    s.lon,
    -- le JSON donne un BIGINT ; le contrat de la table gold attend un INTEGER
    cast(s.capacity as integer)   as capacity
from (
    select unnest(data.stations) as s, last_updated
    from read_json('{{ var("bronze") }}/station_information/*/*.json')
)
qualify row_number() over (partition by s.station_id order by last_updated desc) = 1
