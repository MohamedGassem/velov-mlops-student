{{ config(warn_if='>0', error_if='>10') }}
-- Échoue s'il existe un relevé avec plus de vélos que de bornettes.
-- Seuil : jusqu'à 10 relevés aberrants, on alerte ; au-delà, on bloque.
select s.station_id, s.reported_at, s.bikes_available, i.capacity
from {{ ref('stg_station_status') }} s
join {{ ref('stg_station_information') }} i using (station_id)
where s.bikes_available < 0 or s.bikes_available > i.capacity
