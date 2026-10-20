-- Silver : un enregistrement par station et par relevé, typé, en UTC, sans doublon.
with raw as (
    select last_updated, unnest(data.stations) as s
    from read_json(
        '{{ var("bronze") }}/station_status/*/*.json',
        columns = {
            'last_updated': 'BIGINT',
            'data': 'STRUCT(stations STRUCT(station_id VARCHAR, num_bikes_available INTEGER,
                     num_docks_available INTEGER, is_installed INTEGER, is_renting INTEGER,
                     is_returning INTEGER, last_reported BIGINT)[])'
        }
    )
)
select
    cast(s.station_id as integer)        as station_id,
    to_timestamp(s.last_reported)        as reported_at,
    to_timestamp(last_updated)           as feed_updated_at,
    s.num_bikes_available                as bikes_available,
    s.num_docks_available                as docks_available,
    s.is_installed = 1                   as is_installed
from raw
-- un même relevé apparaît dans plusieurs instantanés : on garde le premier vu
qualify row_number() over (
    partition by s.station_id, s.last_reported order by last_updated
) = 1
