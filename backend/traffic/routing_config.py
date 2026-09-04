"""Bounded, operator-calibrated assumptions; initial values are unvalidated priors."""
from copy import deepcopy
from threading import RLock
from time import monotonic
from math import isfinite
from database import supabase
DEFAULTS={'road_class_per_km':{'motorway':0,'trunk':1,'primary':3,'secondary':6,'tertiary':10,'residential':18,'service':35,'unclassified':12,'unknown':0},'turn_sec':{'straight':0,'slight':2,'left':5,'right':8,'sharp':15,'u_turn':60},'free_flow_multiplier':1.0,'service_transition_sec':4,'minor_transition_sec':2,'junction_branch_sec':0.5,'signal_delay_sec':15}
BOUNDS={'road_class_per_km':(0,120),'turn_sec':(0,120),'free_flow_multiplier':(.5,1.3),'service_transition_sec':(0,30),'minor_transition_sec':(0,20),'junction_branch_sec':(0,3),'signal_delay_sec':(0,90)}
def validate(parameters):
    if set(parameters)!=set(DEFAULTS): raise ValueError('Supply the complete configuration')
    for key,template in DEFAULTS.items():
        values=parameters[key]
        if isinstance(template,dict):
            if not isinstance(values,dict) or set(values)!=set(template): raise ValueError('Unknown/missing parameter')
            values=values.values()
        else: values=[values]
        lo,hi=BOUNDS[key]
        for value in values:
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not isfinite(value) or not lo<=value<=hi: raise ValueError(f'{key} outside allowed range {lo}–{hi}')
    return deepcopy(parameters)
class ConfigStore:
    def __init__(self): self.lock=RLock(); self.cached=None; self.at=0
    def snapshot(self):
        with self.lock:
            if self.cached and monotonic()-self.at<15: return deepcopy(self.cached)
            try:
                row=supabase.table('aegis_routing_config').select('*').eq('id',1).single().execute().data
                parameters=validate(row['parameters']) if row['parameters'] else deepcopy(DEFAULTS)
                self.cached=dict(parameters=parameters,version=row['version'],provenance='CALIBRATED',validation_status='OPERATOR_CALIBRATED' if row['version'] else 'INITIAL_UNVALIDATED_PRIORS',persistence='SUPABASE')
            except Exception:
                if not self.cached: self.cached=dict(parameters=deepcopy(DEFAULTS),version=0,provenance='CALIBRATED',validation_status='INITIAL_UNVALIDATED_PRIORS',persistence='UNAVAILABLE_DEFAULTS')
                else: self.cached['persistence']='UNAVAILABLE_LAST_KNOWN'
            self.at=monotonic()
            return deepcopy(self.cached)
    def change(self, parameters, version, operator, evidence, revert=False):
        if not revert: validate(parameters)
        result=supabase.rpc('aegis_apply_calibration',dict(p_parameters=parameters,p_version=version,p_operator=operator,p_evidence=evidence,p_revert=revert)).execute().data
        with self.lock: self.at=0
        return result
config_store=ConfigStore()
