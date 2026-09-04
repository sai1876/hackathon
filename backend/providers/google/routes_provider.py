"""Google reference metrics only: no polylines requested, logged or persisted."""

import os
from datetime import datetime, timezone
from time import perf_counter
import httpx
from core.api_usage_guard import usage_guard
class GoogleRoutesProvider:
    def __init__(self, guard=None, transport=None):
        self.guard=guard or usage_guard
        self.transport=transport or httpx.post
    def fetch(self, origin, destination):
        key=os.getenv('GOOGLE_MAPS_API_KEY','').strip()
        if os.getenv('GOOGLE_REFERENCE_ENABLED','false').lower()!='true' or not key:
            return dict(status='BLOCKED',reason='GOOGLE_NOT_CONFIGURED',fallback='AEGIS')
        def external():
            started=perf_counter()
            response=self.transport('https://routes.googleapis.com/directions/v2:computeRoutes',headers={'X-Goog-Api-Key':key,'X-Goog-FieldMask':'routes.distanceMeters,routes.duration,routes.staticDuration,routes.routeLabels','Content-Type':'application/json'},json={'origin':{'location':{'latLng':{'latitude':origin['lat'],'longitude':origin['lon']}}},'destination':{'location':{'latLng':{'latitude':destination['lat'],'longitude':destination['lon']}}},'travelMode':'DRIVE','routingPreference':'TRAFFIC_AWARE','computeAlternativeRoutes':False},timeout=15,follow_redirects=False)
            response.raise_for_status()
            rows=response.json().get('routes',[])
            if not rows: return dict(status='UNAVAILABLE',reason='NO_REFERENCE_ROUTE',fallback='AEGIS')
            row=rows[0]
            return dict(status='AVAILABLE',source='GOOGLE_ROUTES',provenance='REAL',measurement_kind='PROVIDER_ESTIMATE',observed_at=datetime.now(timezone.utc).isoformat(),distance_m=row['distanceMeters'],duration_sec=float(row['staticDuration'].removesuffix('s')),traffic_duration_sec=float(row['duration'].removesuffix('s')),route_labels=row.get('routeLabels',[]),google_reference_ms=round((perf_counter()-started)*1000,2))
        return self.guard.attempt('GOOGLE_ROUTES',external)
google_routes=GoogleRoutesProvider()
