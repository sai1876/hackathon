-- Existing reference project. Read-only export for simulation generation.
create or replace function public.aegis_export_road_index(p_after uuid default null,p_limit integer default 5000) returns jsonb language plpgsql stable security invoker set search_path=public,pg_temp as $$
declare result jsonb;
begin
 select coalesce(jsonb_agg(to_jsonb(r) order by r.id),'[]'::jsonb) into result
 from (select id,external_id,osm_u,osm_v,length_m,free_flow_speed_kmph,road_class
 from public.road_segments where id>coalesce(p_after,'00000000-0000-0000-0000-000000000000'::uuid)
 order by id limit least(greatest(p_limit,1),5000)) r;
 return result;
end $$;
revoke all on function public.aegis_export_road_index(uuid,integer) from public,anon,authenticated;
grant execute on function public.aegis_export_road_index(uuid,integer) to service_role;
