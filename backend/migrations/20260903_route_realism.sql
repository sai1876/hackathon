create table public.api_usage (
 provider text not null default 'GOOGLE', sku text not null,
 month_key text not null, usage_count bigint not null default 0 check(usage_count>=0),
 soft_limit bigint not null check(soft_limit>=0), hard_limit bigint not null check(hard_limit>=0),
 last_request_at timestamptz, status text not null default 'SAFE',
 primary key(provider,sku,month_key)
);
alter table public.api_usage enable row level security;
revoke all on public.api_usage from anon, authenticated;
grant select,insert,update on public.api_usage to service_role;
create or replace function public.aegis_google_budget(p_sku text,p_soft bigint,p_hard bigint,p_consume boolean default false)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare r public.api_usage; m text:=to_char(now() at time zone 'UTC','YYYY-MM'); permitted boolean;
begin
 if p_sku not in ('GOOGLE_ROUTES','GOOGLE_GEOCODING','GOOGLE_PLACES','GOOGLE_ROADS','GOOGLE_ELEVATION') or p_soft<0 or p_hard<0 then raise exception 'Invalid budget'; end if;
 insert into public.api_usage(provider,sku,month_key,soft_limit,hard_limit) values('GOOGLE',p_sku,m,p_soft,p_hard)
 on conflict(provider,sku,month_key) do nothing;
 select * into r from public.api_usage where provider='GOOGLE' and sku=p_sku and month_key=m for update;
 -- Mixed deployments cannot raise a limit during a budget period.
 r.hard_limit:=least(r.hard_limit,p_hard); r.soft_limit:=least(r.soft_limit,p_soft,r.hard_limit);
 permitted:=r.usage_count<r.hard_limit;
 if p_consume and permitted then r.usage_count:=r.usage_count+1; r.last_request_at:=clock_timestamp(); end if;
 r.status:=case when r.usage_count>=r.hard_limit then 'STOPPED' when r.usage_count>=r.hard_limit*.75 then 'WARNING' else 'SAFE' end;
 update public.api_usage set usage_count=r.usage_count,soft_limit=r.soft_limit,hard_limit=r.hard_limit,last_request_at=r.last_request_at,status=r.status where provider='GOOGLE' and sku=p_sku and month_key=m;
 return to_jsonb(r)||jsonb_build_object('allowed',permitted,'used',r.usage_count,'remaining',greatest(0,r.hard_limit-r.usage_count),'usage_percent',case when r.hard_limit=0 then 100 else round(r.usage_count*100.0/r.hard_limit,2) end);
end $$;
revoke all on function public.aegis_google_budget(text,bigint,bigint,boolean) from public,anon,authenticated;
grant execute on function public.aegis_google_budget(text,bigint,bigint,boolean) to service_role;

create table public.aegis_routing_config (id integer primary key check(id=1),version integer not null default 0,parameters jsonb not null default '{}');
insert into public.aegis_routing_config(id) values(1);
create table public.aegis_calibration_audit (id bigint generated always as identity primary key,created_at timestamptz not null default now(),operator text not null,evidence text not null,before_values jsonb not null,after_values jsonb not null,version integer not null,action text not null,provenance text not null default 'CALIBRATED');
alter table public.aegis_routing_config enable row level security;
alter table public.aegis_calibration_audit enable row level security;
revoke all on public.aegis_routing_config,public.aegis_calibration_audit from anon,authenticated;
grant select on public.aegis_routing_config,public.aegis_calibration_audit to service_role;
create or replace function public.aegis_apply_calibration(p_parameters jsonb,p_version integer,p_operator text,p_evidence text,p_revert boolean default false)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare r public.aegis_routing_config; next_values jsonb;
begin
 select * into r from public.aegis_routing_config where id=1 for update;
 if r.version<>p_version then raise exception 'Configuration changed; review again'; end if;
 if length(trim(p_operator))<2 or length(trim(p_evidence))<8 then raise exception 'Approval evidence required'; end if;
 if p_revert then
   select before_values into next_values from public.aegis_calibration_audit order by id desc limit 1;
   if next_values is null then raise exception 'No calibration to revert'; end if;
 else next_values:=p_parameters; end if;
 insert into public.aegis_calibration_audit(operator,evidence,before_values,after_values,version,action) values(p_operator,p_evidence,r.parameters,next_values,r.version+1,case when p_revert then 'REVERT' else 'APPLY' end);
 update public.aegis_routing_config set parameters=next_values,version=r.version+1 where id=1;
 return jsonb_build_object('version',r.version+1,'parameters',next_values,'provenance','CALIBRATED');
end $$;
revoke all on function public.aegis_apply_calibration(jsonb,integer,text,text,boolean) from public,anon,authenticated;
grant execute on function public.aegis_apply_calibration(jsonb,integer,text,text,boolean) to service_role;
