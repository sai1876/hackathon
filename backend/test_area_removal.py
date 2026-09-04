import unittest
from copy import deepcopy
from unittest.mock import patch
import scenario_runtime as r
import test_shared_scenario as fixtures

class AreaRemovalTests(unittest.TestCase):
 def state(self):
  s=fixtures.Tests().state();s['seconds']=10;s['running']=False
  s['scenarios']=[fixtures.Tests().rain()]
  s['scenarios'][0].update(blocked=True,drainage_approved=True)
  return s
 def test_removal_cancels_pending_preserves_audit_and_unrelated_area(self):
  s=self.state();other=deepcopy(s['scenarios'][0]);other['id']='other';s['scenarios'].append(other)
  s['recommendations']=[dict(id='pending',scenario_id='rain',status='PENDING'),dict(id='done',scenario_id='rain',status='APPROVED'),dict(id='other-rec',scenario_id='other',status='PENDING')]
  command=r.Command(action='REMOVE',target_id='rain',request_id='remove-test-1')
  r.act(s,command)
  self.assertEqual([z['id'] for z in s['scenarios']],['other'])
  self.assertEqual([v['status'] for v in s['recommendations']],['CANCELLED','APPROVED','PENDING'])
  archived=next(e for e in s['events'] if e['kind']=='SCENARIO_REMOVED')
  self.assertTrue(archived['payload']['scenario']['blocked'])
  before=deepcopy(s);r.act(s,command);self.assertEqual(s,before)
 def test_removal_clears_future_road_power_station_effects_without_rewinding(self):
  s=self.state();s['queues']={'S':{'waiting':200}}
  electric=dict(id='T',kind='DISTRIBUTION_TRANSFORMER',longitude=78.45,latitude=17.42,zone_id='Z',spec=dict(capacity_kva=200))
  station=dict(id='S',kind='METRO_STATION',longitude=78.45,latitude=17.42,zone_id='Z',spec=dict(gtfs_stop_id='S'))
  with patch.object(r,'assets',[electric,station]),patch.object(r,'profiles',[]),patch.object(r,'seed_loads',{'T':100}):
   self.assertGreater(r.station_effects(s)['S']['factor'],1)
   self.assertGreater(r.electric_summary(s)['load_kva'],100)
   r.act(s,r.Command(action='REMOVE',target_id='rain',request_id='remove-test-2'))
   self.assertEqual(r.station_effects(s)['S']['factor'],1)
   self.assertEqual(r.electric_summary(s)['load_kva'],100)
   with patch('emergency_api.sync'),patch('weather_effects.shared_zones',[]),patch.object(r,'routing_signature',None):
    r.publish(s)
    import weather_effects
    self.assertEqual(weather_effects.shared_zones,[])
  self.assertEqual(s['seconds'],10);self.assertEqual(s['queues']['S']['waiting'],200);self.assertFalse(s['running'])
 def test_missing_area_is_rejected(self):
  s=self.state()
  with self.assertRaises(ValueError):r.act(s,r.Command(action='REMOVE',target_id='missing',request_id='remove-test-3'))

if __name__=='__main__':unittest.main()
