"""One atomic reservation immediately before each non-retried external attempt."""
import os
from datetime import datetime, timezone
from database import supabase
SKUS = ('ROUTES','GEOCODING','PLACES','ROADS','ELEVATION','WEATHER')
DEFAULTS = {'WEATHER':(800,1000),'ROUTES':(24000,28000),'GEOCODING':(40000,50000),'PLACES':(24000,28000),'ROADS':(20000,24000),'ELEVATION':(20000,24000)}
class UsageGuard:
    def __init__(self, db=None): self.db = db or supabase
    def budget(self, sku, consume=False):
        name=sku.removeprefix('GOOGLE_')
        if name not in SKUS: raise ValueError('Unsupported Google API')
        try:
            soft=max(0,int(os.getenv(f'GOOGLE_{name}_SOFT_LIMIT',DEFAULTS[name][0])))
            hard=max(0,int(os.getenv(f'GOOGLE_{name}_HARD_LIMIT',DEFAULTS[name][1])))
            return self.db.rpc('aegis_google_budget',dict(p_sku='GOOGLE_'+name,p_soft=soft,p_hard=hard,p_consume=consume)).execute().data
        except Exception:
            return dict(provider='GOOGLE',sku='GOOGLE_'+name,used=None,soft_limit=None,hard_limit=None,remaining=None,usage_percent=None,status='STOPPED',allowed=False,last_request_at=None,reason='USAGE_STORE_UNAVAILABLE')
    def attempt(self, sku, call):
        reservation=self.budget(sku,True)
        if not reservation.get('allowed'): return dict(status='BLOCKED',reason=reservation.get('reason','HARD_LIMIT'),fallback='AEGIS',budget=reservation)
        try: return call()
        except Exception: return dict(status='FAILED',reason='GOOGLE_REQUEST_FAILED',fallback='AEGIS')
    def snapshot(self):
        rows=[self.budget(sku) for sku in SKUS]
        return dict(apis=rows,billing_guard='PERSISTENT_ATOMIC_FAIL_CLOSED',fallback_status='AEGIS AVAILABLE',last_google_fetch=max((r['last_request_at'] for r in rows if r.get('last_request_at')),default=None),checked_at=datetime.now(timezone.utc).isoformat(),google_enabled=os.getenv('GOOGLE_REFERENCE_ENABLED','false').lower()=='true',note='Application request caps; not a guarantee of free provider billing. Reservations can conservatively overcount after a process crash.')
usage_guard=UsageGuard()

