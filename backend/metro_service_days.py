"""Persisted whole-world checkpoints and non-destructive service-day branches."""
from copy import deepcopy
from datetime import date
from time import time
from uuid import uuid4
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
import scenario_runtime as shared
import metro_simulation as sim
from metro_network import services_on

router=APIRouter(prefix='/metro/service-days',tags=['Shared service-day management'])

class Control(BaseModel):
    action:str=Field(pattern='^(CHECKPOINT|NEW_DAY|BRANCH|REPLAY)$')
    name:str=Field(min_length=3,max_length=100)
    actor:str=Field(min_length=1,max_length=80)
    source_id:str|None=None
    service_date:date|None=None
    request_id:str=Field(min_length=8,max_length=90)

@router.get('')
def list_days():
    shared.snapshot()
    rows=shared.db.table('aegis_sim_runs').select('id,name,status,sim_seconds,version,configuration->service_date,configuration->checkpoint_kind').order('name').limit(40).execute().data
    return dict(active_id=shared.RUN_ID,runs=rows,note='A branch restores the entire shared world, including rain, traffic, emergency trips and metro. Existing runs remain available.')

@router.post('')
def control(p:Control):
    if not p.actor.strip():raise HTTPException(422,'Operator identity required')
    with shared.lock:
        shared.snapshot()
        duplicate=shared.db.table('aegis_sim_runs').select('id').contains('configuration',{'control_request':p.request_id}).limit(1).execute().data
        if duplicate:return list_days()
        source=shared.db.table('aegis_sim_runs').select('*').eq('id',p.source_id or shared.RUN_ID).single().execute().data
        if p.action=='NEW_DAY':
            service_date=p.service_date.isoformat() if p.service_date else shared.current['state']['service_date']
            if not services_on(sim.network.data,service_date):raise HTTPException(422,'The imported calendar has no services on that date')
            state=shared.initial(dict(sim_seconds=0,configuration=dict(service_date=service_date)))
            state['metro_v3']=sim.create(state)
            state['metro_v3']['config']=deepcopy(shared.current['state']['metro_v3']['config'])
            state['metro_v3']['profiles']=sim.network.demand_profiles(state['metro_v3']['config'])
        else:
            state=sim.unpack_state(deepcopy(source['configuration'].get('runtime')))
            if state is None:raise HTTPException(422,'Selected run has no saved whole-world checkpoint')
        sim.ensure(state)
        state.update(running=False,last_wall=time(),outbox=[])
        identifier=str(uuid4());kind='CHECKPOINT' if p.action=='CHECKPOINT' else p.action
        config={**source['configuration'],'runtime':sim.pack_state(state),'service_date':state['service_date'],'checkpoint_kind':kind,
            'parent_run_id':source['id'],'control_request':p.request_id,'created_by':p.actor,'active_run_id':identifier}
        row=dict(id=identifier,name=p.name,seed=source['seed'],status='PAUSED',sim_seconds=state['seconds'],version=0,configuration=config)
        shared.db.table('aegis_sim_runs').insert(row).execute()
        if p.action!='CHECKPOINT':
            # Pointer lives in the original baseline and is preserved by normal CAS commits.
            anchor=shared.db.table('aegis_sim_runs').select('configuration,version').eq('id',shared.ROOT_RUN_ID).single().execute().data
            changed=shared.db.table('aegis_sim_runs').update(dict(configuration={**anchor['configuration'],'active_run_id':identifier},version=anchor['version']+1)).eq('id',shared.ROOT_RUN_ID).eq('version',anchor['version']).execute().data
            if not changed:raise HTTPException(409,'Run selection changed; checkpoint saved but not activated')
            shared.RUN_ID=identifier;shared.current=dict(state=state,version=0);shared.checked=time();shared.public_version=-1
            shared.publish(state)
        return list_days()
