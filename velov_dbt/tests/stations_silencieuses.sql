{{ config(severity='warn') }}
-- Une station dont le dernier relevé date de plus d'une heure avant le dernier instantané.
select station_id, max(reported_at) as dernier_releve
from {{ ref('stg_station_status') }}
group by station_id
having max(reported_at) < (select max(feed_updated_at) from {{ ref('stg_station_status') }}) - interval 1 hour
