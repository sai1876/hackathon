import unittest
from copy import deepcopy
from unittest.mock import patch
import scenario_runtime as r
from test_shared_scenario import Tests

class CommandEffectsTests(unittest.TestCase):
 def test_timing_plans_are_distinct_and_stable(self):
  s=Tests().state();offsets=[r.signal_plan(s,{'id':f'J-{i}'})['offset_seconds'] for i in range(20)]
  self.assertGreater(len(set(offsets)),10)
  saved=deepcopy(s)
  self.assertEqual(r.signal_plan(saved,{'id':'J-2'}),r.signal_plan(s,{'id':'J-2'}))
 def test_rain_effect_includes_modal_shift_once(self):
  s=Tests().state();z=Tests().rain();z.update(water_mm=20);s['scenarios']=[z]
  e=r.effect(z,1);self.assertLess(e['traffic_factor'],1);self.assertGreater(e['metro_factor'],1);self.assertLess(e['electric_factor'],1)
  a=dict(id='S',kind='METRO_STATION',longitude=78.45,latitude=17.42,spec=dict(gtfs_stop_id='S'))
  with patch.object(r,'assets',[a]):self.assertAlmostEqual(r.station_effects(s)['S']['factor'],e['metro_factor'])
 def test_area_electric_delta_and_approved_pumps(self):
  s=Tests().state();s['seconds']=1;z=Tests().rain();s['scenarios']=[z]
  a=dict(id='T',kind='DISTRIBUTION_TRANSFORMER',longitude=78.45,latitude=17.42,zone_id='Z',spec=dict(capacity_kva=200))
  with patch.object(r,'assets',[a]),patch.object(r,'profiles',[]),patch.object(r,'seed_loads',{'T':100}):
   before=r.electric_summary(s);self.assertEqual(before['affected_transformers'],1);self.assertLess(before['areas']['rain']['delta_kva'],0)
   z['drainage_approved']=True;after=r.electric_summary(s);self.assertGreater(after['areas']['rain']['delta_kva'],0)
 def test_no_metro_station_no_fabricated_effect(self):
  s=Tests().state();s['scenarios']=[Tests().rain()]
  a=dict(id='S',kind='METRO_STATION',longitude=78.6,latitude=17.6,spec=dict(gtfs_stop_id='S'))
  with patch.object(r,'assets',[a]):self.assertEqual(r.station_effects(s)['S']['factor'],1)

if __name__=='__main__':unittest.main()
