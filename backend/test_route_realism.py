import os, unittest
from copy import deepcopy
from unittest.mock import patch, Mock
import networkx as nx
from shapely.geometry import LineString
from traffic.cost_engine import prepare_edge
from traffic.routing_config import DEFAULTS,validate
from traffic.turn_costs import prepare_bearings,classify,turn_cost
from traffic.route_search import alternatives,search
from core.api_usage_guard import UsageGuard
from providers.google.routes_provider import GoogleRoutesProvider
from traffic.route_calibration import compare,snapshots,read_snapshots
class CostTests(unittest.TestCase):
 def edge(self,kind='primary',**kwargs):
  return prepare_edge(dict(length_m=1000,free_flow_speed_kmph=36,current_cost=100,road_class=kind,**kwargs),deepcopy(DEFAULTS))
 def test_class_costs_preserve_drivability(self):
  a,b,c=[self.edge(k) for k in ['primary','residential','service']]
  self.assertLess(a['current_cost'],b['current_cost']);self.assertLess(b['current_cost'],c['current_cost']);self.assertEqual(c['modeled_eta_sec'],100)
 def test_old_shortcut_vs_new_residential_and_service_routes(self):
  for kind in ['residential','service']:
   g=nx.MultiDiGraph()
   for n,x in [('a',0),('b',.5),('z',1)]:g.add_node(n,x=x,y=0)
   for u,v,length,road in [('a','z',1000,kind),('a','b',550,'primary'),('b','z',550,'primary')]:
    d=prepare_edge(dict(length_m=length,free_flow_speed_kmph=36,current_cost=length/10,road_class=road),DEFAULTS)
    g.add_edge(u,v,geometry=LineString([(g.nodes[u]['x'],0),(g.nodes[v]['x'],0)]),base_travel_time_sec=length/10,**d)
   prepare_bearings(g)
   self.assertEqual(nx.shortest_path(g,'a','z',weight='base_travel_time_sec'),['a','z'])
   self.assertEqual(search(g,'a','z',DEFAULTS),[('a','b',0),('b','z',0)])
 def test_zero_speed_and_access_close(self):
  self.assertEqual(self.edge(traffic_speed_kph=0)['status'],'IMPASSABLE')
  self.assertEqual(self.edge(access='private')['status'],'IMPASSABLE')
 def test_weather_not_counted_twice(self):
  e=self.edge(synthetic_rain_delay_factor=2); self.assertEqual(e['travel_time_sec'],200)
 def test_turn_types(self):
  self.assertEqual([classify(a) for a in [0,25,-90,90,145,180]],['straight','slight','left','right','sharp','u_turn'])
  self.assertGreater(DEFAULTS['turn_sec']['u_turn'],DEFAULTS['turn_sec']['right'])
 def test_bounded_config(self):
  c=deepcopy(DEFAULTS);c['free_flow_multiplier']=10
  with self.assertRaises(ValueError):validate(c)
 def test_three_alternatives_and_turn_count(self):
  g=nx.MultiDiGraph(); points={'a':(0,0),'b':(1,0),'c':(1,1),'d':(1,-1),'z':(2,0)}
  for n,(x,y) in points.items():g.add_node(n,x=x,y=y)
  for u,v in [('a','b'),('b','z'),('a','c'),('c','z'),('a','d'),('d','z')]:
   g.add_edge(u,v,external_id=u+v,geometry=LineString([points[u],points[v]]),**self.edge())
  prepare_bearings(g);paths=alternatives(g,'a','z',DEFAULTS)
  self.assertEqual(len(paths),3);self.assertEqual(paths[0][0][1],'b')
  self.assertEqual(turn_cost(g,paths[1][0],paths[1][1],DEFAULTS)[1],'left')
 def test_calibration_diagnostics(self):
  result=compare(dict(distance_m=2000,eta_seconds=300,road_class_mix={'residential':60},turn_count=20),dict(distance_m=1000,duration_sec=100))
  self.assertEqual(result['status'],'HIGH_MISMATCH');self.assertTrue(result['diagnostics'])
class ProviderTests(unittest.TestCase):
 def guard(self,allowed):
  db=Mock();db.rpc.return_value.execute.return_value.data={'allowed':allowed,'used':1,'status':'SAFE' if allowed else 'STOPPED'}
  return UsageGuard(db),db
 @patch.dict(os.environ,{'GOOGLE_REFERENCE_ENABLED':'true','GOOGLE_MAPS_API_KEY':'TEST_ONLY'})
 def test_single_attempt_normalized_no_geometry(self):
  guard,db=self.guard(True);response=Mock();response.json.return_value={'routes':[{'distanceMeters':1000,'duration':'120s','staticDuration':'100s','polyline':{'encodedPolyline':'not persisted'}}]};transport=Mock(return_value=response)
  result=GoogleRoutesProvider(guard,transport).fetch({'lat':17.4,'lon':78.4},{'lat':17.41,'lon':78.41})
  self.assertEqual(result['duration_sec'],100);self.assertEqual(result['traffic_duration_sec'],120)
  transport.assert_called_once();db.rpc.assert_called_once();self.assertNotIn('polyline',str(result))
 @patch.dict(os.environ,{'GOOGLE_REFERENCE_ENABLED':'true','GOOGLE_MAPS_API_KEY':'TEST_ONLY'})
 def test_hard_limit_stops_transport(self):
  guard,db=self.guard(False);transport=Mock()
  result=GoogleRoutesProvider(guard,transport).fetch({'lat':0,'lon':0},{'lat':1,'lon':1})
  transport.assert_not_called();self.assertEqual(result['fallback'],'AEGIS')
 def test_database_failure_fails_closed(self):
  db=Mock();db.rpc.side_effect=RuntimeError();call=Mock()
  self.assertEqual(UsageGuard(db).attempt('ROUTES',call)['status'],'BLOCKED');call.assert_not_called()
 def test_snapshot_read_does_not_fetch(self):
  with patch('traffic.route_calibration.google_routes.fetch') as fetch:
   read_snapshots();fetch.assert_not_called()

class ApprovalTests(unittest.TestCase):
 @patch.dict(os.environ,{'AEGIS_OPERATOR_TOKEN':'test-operator-token'})
 def test_apply_needs_explicit_approval_and_token(self):
  from fastapi.testclient import TestClient
  from main import app
  c=TestClient(app);body=dict(approved=False,operator='Test operator',evidence='Synthetic unit-test evidence',version=0,parameters=DEFAULTS)
  self.assertEqual(c.post('/calibration/apply',json=body).status_code,403)
  self.assertEqual(c.post('/calibration/apply',json=body,headers={'X-Aegis-Operator-Token':'test-operator-token'}).status_code,422)
 def test_no_google_secret_name_in_frontend_sources(self):
  from pathlib import Path
  root=Path(__file__).parent.parent/'web/src'
  for p in root.rglob('*.tsx'):self.assertNotIn('GOOGLE_MAPS_API_KEY',p.read_text(encoding='utf-8'))
 def test_blocked_google_does_not_disable_aegis_search(self):
  blocked=Mock();blocked.budget.return_value={'allowed':False}
  db=Mock();db.rpc.return_value.execute.return_value.data={'allowed':False}
  self.assertEqual(UsageGuard(db).attempt('ROUTES',Mock())['fallback'],'AEGIS')
  g=nx.MultiDiGraph();g.add_node('a',x=0,y=0);g.add_node('b',x=1,y=0)
  g.add_edge('a','b',geometry=LineString([(0,0),(1,0)]),**prepare_edge(dict(length_m=100,free_flow_speed_kmph=36,current_cost=10,road_class='primary'),DEFAULTS))
  prepare_bearings(g);self.assertEqual(search(g,'a','b',DEFAULTS),[('a','b',0)])
