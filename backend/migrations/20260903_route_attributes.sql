create function public.get_aegis_routing_roads(min_lon double precision,min_lat double precision,max_lon double precision,max_lat double precision,p_limit integer default 1000,p_offset integer default 0)
returns table(external_id text,osm_u text,osm_v text,osm_key integer,road_name text,road_class text,length_m numeric,free_flow_speed_kmph numeric,base_travel_time_sec numeric,oneway boolean,geometry_wkt text,lanes integer,access text,provenance text,signalized boolean)
language sql stable set search_path=public,pg_temp as $$
select r.external_id,r.osm_u,r.osm_v,r.osm_key,r.road_name,r.road_class,r.length_m,r.free_flow_speed_kmph,r.base_travel_time_sec,r.oneway,ST_AsText(r.geometry::geometry),r.lanes_forward,r.metadata->>'access',r.provenance::text,
exists(select 1 from public.junctions j where j.external_id='OSM:signal:'||r.osm_v and j.junction_type='TRAFFIC_SIGNAL')
from public.road_segments r where r.geometry::geometry && ST_MakeEnvelope(min_lon,min_lat,max_lon,max_lat,4326)
order by r.external_id limit least(p_limit,1000) offset p_offset;
$$;
revoke all on function public.get_aegis_routing_roads(double precision,double precision,double precision,double precision,integer,integer) from public,anon,authenticated;
grant execute on function public.get_aegis_routing_roads(double precision,double precision,double precision,double precision,integer,integer) to service_role;
